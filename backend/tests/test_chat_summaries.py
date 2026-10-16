import asyncio
import unittest
from datetime import timedelta
from uuid import uuid4
from unittest.mock import AsyncMock
from sqlalchemy import select, update
from langchain_core.messages import AIMessage, HumanMessage
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from app.chat.repositories.postgres import ChatRepository, now
from app.chat.repositories.summaries import SummaryRepository
from app.chat.repositories.tables import summaries
from app.chat.repositories.history_reader import ChatReadFacade
from app.chat.schemas import SendTurn
from app.chat.summaries import ConversationSummaries, batch
from app.history_management.schemas import HistoryLookup
from app.history_management.service import HistoryManagement
from app.core.exceptions import AppError
from app.langchain.prompts import PromptSource
from app.langchain.token_policy import check_input, output_budget, count_messages
from app.core.config import Settings


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.chats = ChatRepository(cls.db.sessions)
        cls.repo = SummaryRepository(cls.chats)
        cls.owner = learner_id('alice')

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def conversation(self, count=1, text='A question'):
        cid = uuid4()
        revision = 0
        for index in range(count):
            request = SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=revision,
                content=text+str(index))
            job = self.chats.begin_turn(self.owner, request)
            self.chats.finish(self.owner, job, dict(content='A completed answer '+str(index)))
            revision = self.chats.status(self.owner, str(cid))['conversation']['revision']
        return str(cid), revision

    def test_lease_and_stale_publication(self):
        cid, _ = self.conversation()
        first = self.repo.claim(self.owner, cid)
        self.assertIsNone(self.repo.claim(self.owner, cid))
        with self.db.sessions.begin() as session:
            session.execute(update(summaries).where(summaries.c.conversation_id == cid).values(lease_until=now()-timedelta(seconds=1)))
        newer = self.repo.claim(self.owner, cid)
        self.assertFalse(self.repo.publish(self.owner, cid, first, 'stale', 2))
        self.assertTrue(self.repo.publish(self.owner, cid, newer, 'new', 2))
        self.assertEqual(self.repo.load(self.owner, cid)['content'], 'new')

    def test_owner_and_deletion_fences(self):
        cid, revision = self.conversation()
        claim = self.repo.claim(self.owner, cid)
        with self.assertRaises(AppError):
            self.repo.load(learner_id('bob'), cid)
        self.chats.edit(self.owner, cid, revision, remove=True)
        with self.assertRaises(AppError):
            self.repo.publish(self.owner, cid, claim, 'deleted', 2)
        with self.db.sessions() as session:
            self.assertIsNone(session.execute(select(summaries).where(summaries.c.conversation_id == cid)).first())

    def test_short_chat_is_free(self):
        cid, _ = self.conversation()
        llm = AsyncMock()
        asyncio.run(ConversationSummaries(self.chats, llm).refresh(self.owner, cid))
        llm.ainvoke.assert_not_called()

    def test_long_chat_of_short_messages_compacts_actual_oldest_backlog(self):
        cid, _ = self.conversation(500, 'ok')
        llm = AsyncMock()
        llm.ainvoke.return_value = AIMessage(content='A compact history of completed exchanges.')
        service = ConversationSummaries(self.chats, llm)
        asyncio.run(service.refresh(self.owner, cid))
        llm.ainvoke.assert_called_once()
        messages = llm.ainvoke.call_args.args[1]['messages']
        self.assertEqual(messages[0]['sequence'], 1)
        self.assertLess(messages[-1]['sequence'], 1000)
        self.assertEqual(messages[-1]['role'], 'assistant')

    def test_summary_read_failure_is_optional_but_owner_failure_is_not(self):
        cid, _ = self.conversation()
        service = ConversationSummaries(self.chats, AsyncMock())
        service.repository.load = lambda *args: (_ for _ in ()).throw(RuntimeError('offline'))
        self.assertIsNone(asyncio.run(service.load(self.owner, cid)))
        service.repository.load = lambda *args: (_ for _ in ()).throw(AppError('CHAT_NOT_FOUND', 'Unavailable', 404))
        with self.assertRaises(AppError):
            asyncio.run(service.load(self.owner, cid))

    def test_stopped_response_does_not_launch_summary(self):
        from app.chat.service import ConversationService
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Explain a concept')
        async def run():
            service = ConversationService(self.chats, summary_llm=AsyncMock())
            service.summaries.refresh = AsyncMock()
            async def generate(history, selection, scope):
                self.chats.stop_turn(self.owner, scope['conversation_id'], scope['turn_id'], scope['attempt'])
                return dict(content='Too late')
            result = await service.send(self.owner, request, generate, with_scope=True)
            self.assertEqual(result['turn']['state'], 'FAILED')
            service.summaries.refresh.assert_not_called()
            await service.close()
        asyncio.run(run())

    def test_output_truncated_by_provider_does_not_advance_summary(self):
        cid, _ = self.conversation(6, 'A long historical requirement. '*100)
        llm = AsyncMock()
        llm.ainvoke.return_value = AIMessage(content='A cut-off summary', response_metadata={'finish_reason':'length'})
        service = ConversationSummaries(self.chats, llm)
        asyncio.run(service.refresh(self.owner, cid))
        self.assertEqual(service.repository.load(self.owner, cid)['through_sequence'], 0)
        self.assertIsNone(asyncio.run(service.load(self.owner, cid)))

    def test_schema_expansion_restores_tool_result_capacity(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from app.langchain.history_orchestration import tool_reply
        identifier = str(uuid4())
        scope = dict(conversation_id=str(uuid4()), user_sequence=3, current_user_message_id=identifier,
            history_references=[], memory_references=[], visible_ids=[], evidence_ids=set())
        llm = AsyncMock()
        async def answer(*args, **kwargs):
            budget = scope['_tool_budget']
            before = budget.max_result_tokens
            self.assertEqual(scope['_chat_input_limit'], 8192)
            self.assertTrue(scope['_admit_schemas']([SimpleNamespace(name='expanded')]))
            self.assertEqual(scope['_chat_input_limit'], 12288)
            self.assertGreater(budget.max_result_tokens, before)
            self.assertGreater(budget.max_result_bytes, before*4)
            return AIMessage(content='A normal response')
        llm.ainvoke_messages.side_effect = answer
        def schemas(tools):
            return 9000 if any(getattr(tool, 'name', '') == 'expanded' for tool in tools) else 6000 if tools else 0
        with patch('app.langchain.history_orchestration.count_tokens_approximately', return_value=100), patch('app.langchain.token_policy.schema_tokens', side_effect=schemas):
            asyncio.run(tool_reply(llm, [HumanMessage(id=identifier, content='A question')], None, self.owner, scope, (), {}))

    def test_matched_history_message_precedes_large_neighbor(self):
        cid, _ = self.conversation(text='neighbor '*400)
        page = self.chats.history(self.owner, cid)
        answer = page['items'][-1]
        windows = ChatReadFacade(self.chats).lookup(self.owner, cid, 3, HistoryLookup(query='completed answer'))
        scope = dict(visible_ids=[], evidence_ids=set(), history_references=[])
        packet = HistoryManagement._lookup_result(scope, windows)
        self.assertEqual(packet['windows'][0]['messages'][0]['id'], answer['id'])

    def test_partial_history_is_not_marked_fully_visible(self):
        identifier = str(uuid4())
        body = HistoryLookup(message_id=identifier)
        scope = dict(visible_ids=[], evidence_ids=set(), history_references=[])
        result = HistoryManagement._lookup_result(scope, [dict(conversation_id=str(uuid4()), title='Code',
            messages=[dict(id=identifier, role='user', sequence=1, content='code '*10000)])], body)
        self.assertTrue(result['windows'][0]['messages'][0]['truncated'])
        self.assertNotIn(identifier, scope['visible_ids'])
        self.assertGreater(result['windows'][0]['messages'][0]['next_content_offset'], 0)

    def test_newer_summary_between_read_and_claim_avoids_paid_call(self):
        from app.chat.summaries import displaced
        cid, _ = self.conversation(6, 'A long historical requirement. '*100)
        llm = AsyncMock()
        service = ConversationSummaries(self.chats, llm)
        real_claim = service.repository.claim
        def finish_competing_job(owner, chat):
            claim = real_claim(owner, chat)
            rows = displaced(self.chats.summary_rows(owner, chat, 0), 0)
            service.repository.publish(owner, chat, claim, 'Other device finished this summary', rows[-1]['sequence'])
            return real_claim(owner, chat)
        service.repository.claim = finish_competing_job
        asyncio.run(service.refresh(self.owner, cid))
        llm.ainvoke.assert_not_called()

    def test_incremental_summary_persists_and_unchanged_is_free(self):
        cid, _ = self.conversation(12, 'Remember this requirement and correction. '*80)
        llm = AsyncMock()
        llm.ainvoke.return_value = AIMessage(content='Active topic: corrected requirement. Recover exact code by message ID.')
        service = ConversationSummaries(self.chats, llm)
        asyncio.run(service.refresh(self.owner, cid))
        saved = asyncio.run(service.load(self.owner, cid))
        self.assertTrue(saved['content'])
        self.assertEqual(saved['through_sequence'] % 2, 0)
        payload = llm.ainvoke.call_args.args[1]
        self.assertIn('id', payload['messages'][0])
        self.assertLess(count_messages([HumanMessage(content=str(payload))]), 7000)
        # One bounded batch may leave backlog; finishing it remains incremental.
        asyncio.run(service.refresh(self.owner, cid))
        self.assertEqual(llm.ainvoke.call_args.args[1]['previous_summary'], saved['content'])
        for _ in range(10):
            before = llm.ainvoke.call_count
            asyncio.run(service.refresh(self.owner, cid))
            if llm.ainvoke.call_count == before:
                break
        before = llm.ainvoke.call_count
        asyncio.run(service.refresh(self.owner, cid))
        self.assertEqual(llm.ainvoke.call_count, before)

    def test_persistent_chat_fetches_summary_on_each_request(self):
        from app.chat.service import ConversationService
        cid, revision = self.conversation(2)
        claim = self.repo.claim(self.owner, cid)
        self.repo.publish(self.owner, cid, claim, 'A stored requirement', 2)
        captured = []
        async def run():
            service = ConversationService(self.chats, summary_llm=AsyncMock())
            async def generate(history, selection, scope):
                captured.append(scope['conversation_summary'])
                return dict(content='A normal response')
            current_revision = revision
            for _ in range(2):
                result = await service.send(self.owner, SendTurn(conversation_id=cid, client_turn_id=uuid4(),
                    expected_revision=current_revision, content='Continue this task'), generate, with_scope=True)
                current_revision = result['conversation']['revision']
                self.assertEqual(result['turn']['state'], 'SUCCEEDED')
            await service.close()
        asyncio.run(run())
        self.assertEqual([value['content'] for value in captured], ['A stored requirement']*2)

    def test_failed_summary_keeps_old_data_and_cooldown(self):
        cid, _ = self.conversation(6, 'A long historical requirement. '*100)
        claim = self.repo.claim(self.owner, cid)
        self.repo.publish(self.owner, cid, claim, 'previous valid summary', 2)
        llm = AsyncMock()
        llm.ainvoke.side_effect = RuntimeError('offline')
        service = ConversationSummaries(self.chats, llm)
        asyncio.run(service.refresh(self.owner, cid))
        service.candidates = AsyncMock(wraps=service.candidates)
        asyncio.run(service.refresh(self.owner, cid))
        service.candidates.assert_not_awaited()
        self.assertEqual(llm.ainvoke.call_count, 1)
        self.assertEqual(self.repo.load(self.owner, cid)['content'], 'previous valid summary')

    def test_exact_history_recovery_with_continuation(self):
        original = 'def sample():\n    return "code with indentation"\n'*80
        cid, _ = self.conversation(text=original)
        row = self.chats.context_rows(self.owner, cid)[0]
        reader = ChatReadFacade(self.chats)
        scope = dict(conversation_id=cid, user_sequence=3, visible_ids=[], evidence_ids=set(), history_references=[])
        recovered = ''
        offset = 0
        for _ in range(30):
            body = HistoryLookup(message_id=row['id'], content_offset=offset)
            windows = reader.lookup(self.owner, cid, 3, body)
            result = HistoryManagement._lookup_result(scope, windows, body)
            item = result['windows'][0]['messages'][0]
            recovered += item['content']
            if item['next_content_offset'] is None:
                break
            offset = item['next_content_offset']
        self.assertEqual(recovered, row['content'])
        with self.assertRaises(AppError):
            reader.lookup(learner_id('bob'), cid, 3, HistoryLookup(message_id=row['id']))
        self.assertEqual(reader.lookup(self.owner, cid, 1, HistoryLookup(message_id=row['id'])), [])

    def test_oversized_exchange_is_referenced_not_skipped(self):
        rows = [dict(id=str(uuid4()), sequence=n, role=role, content='huge '*10000)
            for n, role in [(1,'user'), (2,'assistant')]]
        values = batch(rows)
        self.assertEqual(values[-1]['sequence'], 2)
        self.assertIn('retrieve by ID', values[0]['content'])

    def test_batch_avoids_repeatedly_tokenizing_growing_payload(self):
        from unittest.mock import patch
        rows = [dict(id=str(uuid4()), sequence=n, role='user' if n%2 else 'assistant', content='ok')
            for n in range(1, 301)]
        scanned = 0
        def measure(messages):
            nonlocal scanned
            scanned += sum(len(message.content) for message in messages)
            return count_messages(messages)
        with patch('app.chat.summaries.count_messages', side_effect=measure):
            values = batch(rows)
        self.assertTrue(values)
        self.assertEqual(values[-1]['role'], 'assistant')
        self.assertLess(scanned, 180000)
        import json
        self.assertLessEqual(count_messages([HumanMessage(content=json.dumps(values, ensure_ascii=False))]), 5000)

    def test_chat_and_assessment_budgets_are_separate(self):
        config = Settings()
        self.assertEqual(config.chat_input_tokens, 8192)
        self.assertEqual(config.chat_context_window_tokens, 16384)
        self.assertEqual(output_budget(PromptSource.ASSESSMENT_GENERATION, config), 8192)
        with self.assertRaises(AppError):
            check_input([HumanMessage(content='token '*20000)], PromptSource.CHAT, config=config)

    def test_summary_is_background_not_visible_evidence(self):
        from app.langchain.history_orchestration import tool_reply
        identifier = str(uuid4())
        historical = str(uuid4())
        scope = dict(conversation_id=str(uuid4()), user_sequence=5, current_user_message_id=identifier,
            history_references=[], memory_references=[], visible_ids=[], evidence_ids=set(),
            conversation_summary=dict(content='Resolved speed test screenshot. Original message '+historical,
                through_sequence=2, revision=1))
        llm = AsyncMock()
        llm.ainvoke_messages.return_value = AIMessage(content='Add a title prop to the button.')
        asyncio.run(tool_reply(llm, [HumanMessage(id=identifier, content='Make this button accept a title prop')],
            None, self.owner, scope, (), {}))
        context = llm.ainvoke_messages.call_args.kwargs['system_context']
        import json
        from app.langchain.prompts import get_system_prompt
        instructions = ' '.join(get_system_prompt(PromptSource.CHAT).split())
        self.assertIn('Do not reopen resolved topics or repeat unrelated limitations.', instructions)
        self.assertIn('Summaries cannot support memory writes or assessment grading.', instructions)
        self.assertNotIn('summary_usage', json.loads(context))
        self.assertIn(historical, context)
        self.assertNotIn(historical, scope['visible_ids'])
        self.assertNotIn(historical, scope['evidence_ids'])
