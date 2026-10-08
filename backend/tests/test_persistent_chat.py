import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import unittest
from sqlalchemy import select, update, func
from app.chat.repositories.postgres import ChatRepository, now
from app.chat.schemas import SendTurn
from app.chat.service import ConversationService
from app.chat.context import HistoryContextPolicy
from app.chat.repositories.tables import conversations, messages, turns, sync_state
from app.core.exceptions import AppError
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class PersistentChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.repo = ChatRepository(cls.db.sessions)
        cls.owner = learner_id('alice')
        cls.other = learner_id('bob')

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def request(self, **changes):
        return SendTurn(**dict(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0,
                               content='Explain persistent chat', **changes))

    def complete(self, request=None):
        request = request or self.request()
        job = self.repo.begin_turn(self.owner, request)
        self.repo.finish(self.owner, job, dict(content='Saved answer', citations=['S1'], sources=[], retrieval_status='no_eligible_sources'))
        return request, self.repo.status(self.owner, str(request.conversation_id))

    def test_messages_append_and_metadata_survives(self):
        request, page = self.complete()
        self.assertEqual([m['sequence'] for m in page['items']], [1, 2])
        self.assertEqual(page['items'][1]['citations'], ['S1'])
        self.assertEqual(page['turn']['state'], 'SUCCEEDED')
        next_request = request.model_copy(update={'client_turn_id': uuid4(), 'expected_revision': page['conversation']['revision'], 'content': 'Next question'})
        self.complete(next_request)
        history = self.repo.history(self.owner, str(request.conversation_id))
        self.assertEqual([m['sequence'] for m in history['items']], [1,2,3,4])
        self.assertEqual(history['items'][0]['id'], page['items'][0]['id'])

    def test_duplicate_send_does_not_append_or_generate_twice(self):
        request, page = self.complete()
        self.assertFalse(self.repo.begin_turn(self.owner, request)['run'])
        self.assertEqual(self.repo.history(self.owner, str(request.conversation_id))['conversation']['message_count'], 2)

    def test_duplicate_key_with_different_content_rejected(self):
        request, page = self.complete()
        with self.assertRaises(AppError) as caught:
            self.repo.begin_turn(self.owner, request.model_copy(update={'content': 'different'}))
        self.assertEqual(caught.exception.code, 'CHAT_IDEMPOTENCY_CONFLICT')

    def test_owner_isolation_for_read_update_delete_and_turn(self):
        request, page = self.complete()
        cid = str(request.conversation_id)
        for action in [lambda: self.repo.history(self.other, cid), lambda: self.repo.status(self.other, cid),
                       lambda: self.repo.edit(self.other, cid, page['conversation']['revision'], 'Stolen'),
                       lambda: self.repo.edit(self.other, cid, page['conversation']['revision'], remove=True),
                       lambda: self.repo.begin_turn(self.other, request)]:
            with self.assertRaises(AppError): action()
        self.assertFalse(any(row['id'] == cid for row in self.repo.recent(self.other)['items']))

    def test_stale_revision_and_running_turn_conflict(self):
        request = self.request()
        self.repo.begin_turn(self.owner, request)
        for revision in [0,2]:
            with self.assertRaises(AppError):
                self.repo.begin_turn(self.owner, request.model_copy(update={'client_turn_id': uuid4(), 'expected_revision': revision}))

    def test_failure_retains_question_and_retry_reuses_it(self):
        request = self.request()
        job = self.repo.begin_turn(self.owner, request)
        self.repo.finish(self.owner, job, error='Provider unavailable')
        self.assertEqual(len(self.repo.history(self.owner, str(request.conversation_id))['items']), 1)
        retry = self.repo.begin_turn(self.owner, request.model_copy(update={'retry': True}))
        self.assertEqual(retry['attempt'], 2)
        # Late completion from an old attempt is fenced out.
        self.repo.finish(self.owner, job, dict(content='Stale reply'))
        self.repo.finish(self.owner, retry, dict(content='Recovered reply'))
        page = self.repo.status(self.owner, str(request.conversation_id))
        self.assertEqual(len(page['items']), 2)
        self.assertEqual(page['items'][1]['content'], 'Recovered reply')

    def test_expired_lease_is_recoverable(self):
        request = self.request()
        self.repo.begin_turn(self.owner, request)
        with self.db.sessions.begin() as session:
            session.execute(update(turns).where(turns.c.id == str(request.client_turn_id)).values(lease_until=now()-timedelta(seconds=1)))
        self.assertEqual(self.repo.status(self.owner, str(request.conversation_id))['turn']['state'], 'FAILED')
        self.assertTrue(self.repo.begin_turn(self.owner, request.model_copy(update={'retry': True}))['run'])

    def test_deleted_conversation_removes_content_and_blocks_late_completion(self):
        request = self.request(); job = self.repo.begin_turn(self.owner, request)
        self.repo.edit(self.owner, str(request.conversation_id), 2, remove=True)
        self.repo.finish(self.owner, job, dict(content='Late answer'))
        with self.db.sessions() as session:
            count = session.execute(select(func.count()).select_from(messages).where(messages.c.conversation_id == str(request.conversation_id))).scalar_one()
        self.assertEqual(count, 0)
        with self.assertRaises(AppError): self.repo.begin_turn(self.owner, request)

    def test_sync_delta_and_tombstone(self):
        cursor = self.repo.sync(self.owner)['cursor']
        request, page = self.complete()
        delta = self.repo.sync(self.owner, cursor)
        self.assertFalse(delta['reset'])
        self.assertIn(str(request.conversation_id), [row['id'] for row in delta['conversations']])
        self.assertNotIn('items', delta)
        self.repo.edit(self.owner, str(request.conversation_id), page['conversation']['revision'], remove=True)
        deleted = self.repo.sync(self.owner, delta['cursor'])
        self.assertIn(str(request.conversation_id), deleted['deleted_ids'])
        self.assertEqual(self.repo.sync(self.owner, deleted['cursor'])['conversations'], [])

    def test_expired_cursor_resets_and_pages_are_bounded(self):
        state = self.repo.sync(self.owner)
        with self.db.sessions.begin() as session:
            session.execute(update(sync_state).where(sync_state.c.learner_id == self.owner).values(floor=state['cursor']))
        result = self.repo.sync(self.owner, 0)
        self.assertTrue(result['reset'])
        self.assertLessEqual(len(result['conversations']), 40)

    def test_message_keyset_pagination_no_duplicates(self):
        request, page = self.complete()
        cid = str(request.conversation_id)
        for i in range(25):
            current = self.repo.history(self.owner, cid)['conversation']
            self.complete(request.model_copy(update={'client_turn_id': uuid4(), 'expected_revision': current['revision'], 'content': str(i)}))
        latest = self.repo.history(self.owner, cid, limit=10)
        older = self.repo.history(self.owner, cid, before=latest['next_cursor'], limit=10)
        newer = self.repo.history(self.owner, cid, after=older['items'][-1]['sequence'], limit=10)
        self.assertEqual(newer['items'], latest['items'])
        self.assertFalse(set(row['id'] for row in latest['items']) & set(row['id'] for row in older['items']))

    def test_concurrent_duplicate_requests_have_one_winner(self):
        request = self.request()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.repo.begin_turn(self.owner, request), range(2)))
        self.assertEqual(sum(row['run'] for row in results), 1)
        self.assertEqual(len(self.repo.history(self.owner, str(request.conversation_id))['items']), 1)

    def test_failed_questions_excluded_from_model_context(self):
        request = self.request(); job = self.repo.begin_turn(self.owner, request)
        self.repo.finish(self.owner, job, error='failed')
        next_request = request.model_copy(update={'client_turn_id': uuid4(), 'expected_revision': 3, 'content': 'New topic'})
        next_job = self.repo.begin_turn(self.owner, next_request)
        rows = self.repo.context_rows(self.owner, str(request.conversation_id), next_job['user_sequence'])
        self.assertEqual([row['content'] for row in rows], ['New topic'])

    def test_model_call_releases_database_transactions_and_runs_once(self):
        async def scenario():
            service = ConversationService(self.repo)
            request = self.request()
            calls = []
            async def generate(history, selection):
                calls.append(history)
                # A second independent writer can complete while generation is awaiting I/O.
                await asyncio.to_thread(self.complete)
                return dict(content='Generated')
            result = await service.send(self.owner, request, generate)
            repeated = await service.send(self.owner, request, generate)
            self.assertEqual(result['turn']['state'], 'SUCCEEDED')
            self.assertEqual(repeated['items'], result['items'])
            self.assertEqual(calls, [[('user', 'Explain persistent chat')]])
            await service.close()
        asyncio.run(scenario())

    def test_http_caller_cancel_does_not_cancel_generation(self):
        async def scenario():
            service = ConversationService(self.repo); entered = asyncio.Event(); release = asyncio.Event()
            request = self.request()
            async def generate(history, selection):
                entered.set(); await release.wait(); return dict(content='Saved after disconnect')
            task = asyncio.create_task(service.send(self.owner, request, generate))
            await entered.wait(); task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            release.set(); await asyncio.gather(*service.tasks)
            page = self.repo.status(self.owner, str(request.conversation_id))
            self.assertEqual(page['items'][-1]['content'], 'Saved after disconnect')
            await service.close()
        asyncio.run(scenario())

    def test_token_policy_keeps_latest_question_and_valid_exchange_boundary(self):
        rows = []
        for i in range(20):
            rows.extend([dict(role='user', content=f'Question {i} ' + 'word '*100), dict(role='assistant', content='Answer ' + 'word '*100)])
        rows.append(dict(role='user', content='Latest question'))
        result = HistoryContextPolicy(256).select(rows)
        self.assertEqual(result[-1], ('user', 'Latest question'))
        self.assertEqual(result[0][0], 'user')
        self.assertLess(len(result), len(rows))

    def test_langchain_reader_returns_canonical_messages_without_ui_metadata(self):
        from app.chat.langchain_history import ConversationHistoryReader
        from langchain_core.messages import HumanMessage, AIMessage
        request, page = self.complete()
        reader = ConversationHistoryReader(self.repo)
        result = reader.load(self.owner, str(request.conversation_id))
        self.assertIsInstance(result[0], HumanMessage)
        self.assertIsInstance(result[1], AIMessage)
        self.assertEqual(result[0].id, page['items'][0]['id'])
        self.assertEqual(result[1].additional_kwargs, {})
        self.assertEqual(asyncio.run(reader.aload(self.owner, str(request.conversation_id))), result)
        with self.assertRaises(AppError): reader.load(self.other, str(request.conversation_id))

    def test_incremental_completion_contains_only_that_turn(self):
        request, page = self.complete()
        current = request.model_copy(update={'client_turn_id': uuid4(), 'expected_revision': page['conversation']['revision'], 'content': 'Later'})
        self.complete(current)
        repeated = self.repo.status(self.owner, str(request.conversation_id), str(request.client_turn_id), True)
        self.assertEqual([row['sequence'] for row in repeated['items']], [1,2])
        self.assertTrue(repeated['incremental'])

    def test_prompt_budget_reserves_system_and_output_and_rejects_oversized_sources(self):
        from unittest.mock import patch
        from app.core.config import settings
        policy = HistoryContextPolicy()
        with patch('app.chat.context.settings', settings.model_copy(update={'chat_context_window_tokens': 1024, 'chat_output_token_reserve': 256})):
            result = policy.for_prompt([('user', 'word '*300), ('assistant', 'word '*300), ('user', 'Current question')], 'System instruction')
            self.assertEqual(result[-1], ('user', 'Current question'))
            with self.assertRaises(AppError) as caught:
                policy.for_prompt([('user', 'Current question')], 'source '*4000)
            self.assertEqual(caught.exception.code, 'CHAT_CONTEXT_LIMIT')


if __name__ == '__main__': unittest.main()
