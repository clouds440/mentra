import asyncio
import unittest
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from sqlalchemy import select, update, delete
from app.auth.repositories.tables import learner
from app.history_management.repositories.postgres import MemoryRepository
from app.history_management.repositories.memory_summaries import MemorySummaryRepository, capture, now
from app.history_management.repositories.tables import summary_state as s, summary_changes as c, summary_jobs as j, memories as m
from app.history_management.memory.summaries import MemorySummaries
from app.history_management.memory.summary_schemas import MemorySummary, fits, bounded
from app.history_management.schemas import MemoryEdit
from app.langchain.llm import MentraLLM
from app.langchain.prompts import PromptSource, get_system_prompt, get_prompt_version
from app.core.config import settings
from testing.postgres import PostgresSandbox


class SummaryModel:
    def __init__(self):
        self.calls = []
        self.action = None
        self.invalid = False

    messages = MentraLLM.messages

    async def ainvoke(self, source, payload, **kwargs):
        self.calls.append(payload)
        if self.action:
            self.action()
        if self.invalid:
            return MemorySummary(blocks=[dict(text='Invented fact', supports=[dict(id=str(uuid4()), revision=1)])])
        changed = {x['id'] for x in payload['changes']} | set(payload['removed'])
        blocks = [b for b in payload['previous_summary'] if not any(x['id'] in changed for x in b['supports'])]
        blocks += [dict(text=x['content'], supports=[dict(id=x['id'], revision=x['revision'])]) for x in payload['changes']]
        return MemorySummary(blocks=bounded(blocks))


class MemorySummaryTests(unittest.TestCase):
    def test_unchanged_summary_is_a_single_read_and_external_edits_invalidate_it(self):
        from sqlalchemy import event
        memory = self.add('Prefers short examples.')
        self.run_worker()
        original = self.context()
        statements = []
        def observe(connection, cursor, statement, parameters, context, many):
            statements.append(statement)
        event.listen(self.db.engine, 'before_cursor_execute', observe)
        try:
            self.assertEqual(self.context(), original)
        finally:
            event.remove(self.db.engine, 'before_cursor_execute', observe)
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0].lstrip().startswith('SELECT'))
        other_process = MemoryRepository(self.db.sessions)
        other_process.edit(self.owner, memory['id'], MemoryEdit(expected_revision=memory['revision'], content='Prefers detailed examples.'))
        refreshed = self.context()
        self.assertIn('detailed examples', refreshed['content'])
        self.assertNotIn('short examples', refreshed['content'])

    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.owner = str(uuid4())
        with self.db.sessions.begin() as session:
            session.execute(learner.insert().values(id=self.owner))
        self.memories = MemoryRepository(self.db.sessions)
        self.repository = MemorySummaryRepository(self.db.sessions)
        self.model = SummaryModel()
        self.worker = MemorySummaries(self.repository, self.model)

    def tearDown(self):
        with self.db.sessions.begin() as session:
            session.execute(delete(j).where(j.c.learner_id == self.owner))

    def add(self, content='Maintains the open source untoastify project.', **kwargs):
        return self.memories.write(self.owner, content, 'fact', str(uuid4()), **kwargs)['memory']

    def ready(self):
        with self.db.sessions.begin() as session:
            session.execute(update(j).where(j.c.learner_id == self.owner).values(available_at=now()-timedelta(seconds=1)))

    def run_worker(self):
        self.ready()
        return asyncio.run(self.worker.run_once())

    def context(self):
        return self.repository.context(self.owner)[0]

    def test_new_memory_available_before_worker_and_persists_after_worker(self):
        self.add()
        self.assertIn('untoastify', self.context()['content'])
        self.assertEqual(self.context()['state'], 'updating')
        self.assertTrue(self.run_worker())
        self.assertEqual(self.context()['state'], 'ready')
        self.assertIn('untoastify', MemorySummaryRepository(self.db.sessions).context(self.owner)[0]['content'])

    def test_incremental_update_sends_only_changed_records(self):
        a = self.add()
        self.add('Prefers concise explanations.')
        self.run_worker()
        self.memories.edit(self.owner, a['id'], MemoryEdit(expected_revision=a['revision'], content='Maintains accessible React tools.'))
        self.run_worker()
        packet = self.model.calls[-1]
        self.assertEqual(len(packet['changes']), 1)
        self.assertEqual(packet['changes'][0]['content'], 'Maintains accessible React tools.')
        self.assertIn('concise', self.context()['content'])
        self.assertNotIn('untoastify', self.context()['content'])

    def test_delete_immediately_removes_stored_text_and_pending_delta_copies(self):
        a = self.add()
        self.add('Likes algebra.')
        self.run_worker()
        self.memories.remove(self.owner, a['id'], a['revision'])
        self.assertNotIn('untoastify', self.context()['content'])
        with self.db.sessions() as session:
            state = dict(session.execute(select(s).where(s.c.learner_id == self.owner)).mappings().one())
            self.assertNotIn('untoastify', str(state['blocks']))
            changes = list(session.execute(select(c).where(c.c.learner_id == self.owner)).mappings())
            self.assertNotIn('untoastify', str(changes))
        self.run_worker()
        self.assertIn('algebra', self.context()['content'])

    def test_last_deletion_clears_without_model_call(self):
        a = self.add()
        self.run_worker()
        self.memories.remove(self.owner, a['id'], a['revision'])
        self.assertEqual(self.context()['content'], '')
        self.assertFalse(self.run_worker())
        self.assertEqual(len(self.model.calls), 1)

    def test_pending_and_conflict_are_excluded_until_confirmation(self):
        a = self.add(status='pending', origin='ai')
        self.assertEqual(self.context()['content'], '')
        self.memories.edit(self.owner, a['id'], MemoryEdit(expected_revision=a['revision'], confirm=True))
        self.assertIn('untoastify', self.context()['content'])
        self.run_worker()
        self.assertEqual(self.context()['state'], 'ready')

    def test_idempotent_and_revision_only_writes_do_not_generate_again(self):
        a = self.add()
        self.run_worker()
        self.add()
        self.assertFalse(self.run_worker())
        self.assertEqual(len(self.model.calls), 1)
        self.assertIn('untoastify', self.context()['content'])

    def test_change_during_generation_cannot_publish_old_output(self):
        a = self.add()
        self.model.action = lambda: self.memories.edit(self.owner, a['id'], MemoryEdit(expected_revision=a['revision'], content='Studies geometry.'))
        self.run_worker()
        self.assertNotIn('untoastify', self.context()['content'])
        self.assertIn('geometry', self.context()['content'])
        self.model.action = None
        self.run_worker()
        self.assertEqual(self.context()['state'], 'ready')

    def test_leases_single_flight_and_stale_claim_fenced(self):
        self.add()
        self.ready()
        first = self.repository.claim()
        self.assertIsNone(self.repository.claim())
        with self.db.sessions.begin() as session:
            session.execute(update(j).where(j.c.learner_id == self.owner).values(lease_until=now()-timedelta(seconds=1)))
        second = self.repository.claim()
        self.assertNotEqual(first['token'], second['token'])
        packet = self.repository.packet(first)
        self.assertFalse(self.repository.publish(first, packet, []))
        self.repository.release(second)

    def test_rollback_does_not_leave_job(self):
        with self.assertRaises(RuntimeError):
            with self.db.sessions.begin() as session:
                from app.db.owner_transactions import lock_owner
                lock_owner(session, self.owner)
                capture(session, self.owner, None, dict(id=str(uuid4()), revision=1, content='Rollback fact', category='fact', pinned=False, status='active', expires_at=None))
                raise RuntimeError()
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(j.c.learner_id).where(j.c.learner_id == self.owner)))

    def test_expiry_is_filtered_even_with_worker_down(self):
        self.add(expires_at=now()+timedelta(seconds=10))
        self.run_worker()
        with self.db.sessions.begin() as session:
            session.execute(update(m).where(m.c.learner_id == self.owner).values(expires_at=now()-timedelta(seconds=1)))
            session.execute(update(s).where(s.c.learner_id == self.owner).values(next_expiry_at=now()-timedelta(seconds=1)))
        self.assertEqual(self.context()['content'], '')
        self.repository.sweep()
        self.run_worker()
        self.assertEqual(self.context()['state'], 'empty')

    def test_source_fence_rejects_concurrent_edits(self):
        a = self.add()
        _, fence = self.repository.context(self.owner)
        self.memories.edit(self.owner, a['id'], MemoryEdit(expected_revision=a['revision'], content='New durable fact.'))
        with self.db.sessions() as session:
            self.assertFalse(self.repository.current(session, self.owner, fence))

    def test_support_validation_retries_without_marking_current(self):
        self.add()
        self.model.invalid = True
        for _ in range(5):
            self.run_worker()
        with self.db.sessions() as session:
            job = session.execute(select(j).where(j.c.learner_id == self.owner)).mappings().one()
            self.assertTrue(job['failed'])
        self.assertEqual(self.context()['state'], 'updating')
        self.model.invalid = False
        self.repository.retry(self.owner)
        self.run_worker()
        self.assertEqual(self.context()['state'], 'ready')

    def test_bootstrap_checkpoints_across_pages_and_restart(self):
        for index in range(28):
            self.add(f'Project number {index} is important.')
        self.run_worker()
        with self.db.sessions() as session:
            job = session.execute(select(j).where(j.c.learner_id == self.owner)).mappings().one()
            self.assertTrue(job['checkpoint']['cursor'])
        self.worker = MemorySummaries(MemorySummaryRepository(self.db.sessions), self.model)
        for _ in range(4):
            self.run_worker()
        self.assertEqual(self.context()['state'], 'ready')
        self.assertTrue(all(len(x['changes']) <= 12 for x in self.model.calls))
        self.assertTrue(fits(self.model.calls[-1]['previous_summary']))

    def test_owner_isolation_and_independent_limits(self):
        self.add()
        other = str(uuid4())
        with self.db.sessions.begin() as session:
            session.execute(learner.insert().values(id=other))
        self.assertEqual(self.repository.context(other)[0]['content'], '')
        self.assertEqual(self.context()['state'], 'updating')
        small = settings.model_copy(update={'memory_summary_max_characters': 256, 'chat_summary_max_characters': 8000})
        self.assertFalse(fits([dict(text='x'*300, supports=[])], small))

    def test_prompt_relevance_and_registry(self):
        self.assertEqual(get_prompt_version(PromptSource.MEMORY_SUMMARY), 'memory-summary-v1')
        for source in (PromptSource.CHAT, PromptSource.HISTORY_MANAGEMENT):
            prompt = get_system_prompt(source)
            self.assertIn('unrelated', prompt)
            self.assertIn('retriev', prompt)

    def test_every_turn_includes_memory_and_chat_envelopes_separately(self):
        import json
        from langchain_core.messages import AIMessage
        from app.langchain.chat_service import ChatService
        from app.langchain.orchestration_service import OrchestrationService
        from app.history_management.service import HistoryManagement
        from app.chat.repositories.history_reader import ChatReadFacade
        from app.chat.repositories.postgres import ChatRepository
        class Capture:
            def get_model(inner):
                return inner
            def bind_tools(inner, tools, **kwargs):
                return inner
            async def ainvoke(inner, messages):
                inner.context = json.loads(messages[0].content.rsplit('\n\n', 1)[-1])
                return AIMessage(content='A relevant response.')
        self.add()
        self.run_worker()
        llm = Capture()
        history = HistoryManagement(self.memories, ChatReadFacade(ChatRepository(self.db.sessions)), None)
        service = OrchestrationService(ChatService(llm), history=history)
        for index in (0, 1):
            identifier = str(uuid4())
            text = 'Tell me about my projects.'
            scope = dict(conversation_id=str(uuid4()), turn_id=str(uuid4()), user_sequence=3, current_user_message_id=identifier,
                context_rows=[dict(id=identifier, sequence=3, role='user', content=text)], history_references=[], memory_references=[])
            if index:
                scope['conversation_summary'] = dict(content='Only the second chat covered geometry.', through_sequence=2, revision=1)
            asyncio.run(service.chat_reply([('user', text)], None, self.owner, history_scope=scope))
            self.assertIn('untoastify', llm.context['memories_summary']['content'])
            self.assertEqual(llm.context['conversation_summary']['state'], 'ready' if index else 'empty')
            self.assertTrue(scope['_memory_summary_fence'])

    def test_conflict_resolution_removes_predecessor_from_overview(self):
        old = self.add('Prefers tea.')
        candidate = self.add('Prefers coffee.', origin='ai', status='conflict', conflict_ids=[old['id']])
        self.run_worker()
        self.memories.edit(self.owner, candidate['id'], MemoryEdit(expected_revision=candidate['revision'], confirm=True,
            resolve_conflict=True, conflict_revisions={old['id']:old['revision']}))
        self.assertNotIn('tea', self.context()['content'])
        self.assertIn('coffee', self.context()['content'])

    def test_deleting_mixed_block_recovers_unaffected_support(self):
        a = self.add()
        b = self.add('Prefers geometry.')
        self.run_worker()
        with self.db.sessions.begin() as session:
            session.execute(update(s).where(s.c.learner_id == self.owner).values(blocks=[dict(text='Maintains untoastify and prefers geometry.',
                supports=[dict(id=a['id'], revision=a['revision']), dict(id=b['id'], revision=b['revision'])])]))
        self.memories.remove(self.owner, a['id'], a['revision'])
        self.assertIn('geometry', self.context()['content'])
        self.assertNotIn('untoastify', self.context()['content'])

    def test_completion_rejects_summary_invalidated_mid_turn(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        a = self.add()
        _, fence = self.repository.context(self.owner)
        chats = ChatRepository(self.db.sessions)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Tell me about my project.')
        job = chats.begin_turn(self.owner, request)
        self.memories.remove(self.owner, a['id'], a['revision'])
        self.assertTrue(chats.finish(self.owner, job, dict(content='Old project answer.', _memory_summary_fence=fence)))
        from app.chat.repositories.tables import messages
        with self.db.sessions() as session:
            answer = session.execute(select(messages).where(messages.c.learner_id == self.owner, messages.c.role == 'assistant')).mappings().one()
            self.assertIn('changed while I was answering', answer['content'])
            self.assertNotIn('_memory_summary_fence', answer['metadata'])

    def test_watch_cancels_stream_on_memory_change(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        from app.chat.service import ConversationService
        from app.langchain.activity import ActivityPublisher
        a = self.add()
        _, fence = self.repository.context(self.owner)
        chats = ChatRepository(self.db.sessions)
        job = chats.begin_turn(self.owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Discuss my project.'))
        self.memories.remove(self.owner, a['id'], a['revision'])
        scope = dict(_memory_summary_fence=fence, activity=ActivityPublisher())
        async def check():
            generation = asyncio.create_task(asyncio.sleep(5))
            await ConversationService(chats)._watch_active(self.owner, job, generation, scope)
            await asyncio.gather(generation, return_exceptions=True)
            self.assertTrue(generation.cancelled())
        asyncio.run(check())
        self.assertTrue(scope['_memory_context_changed'])

    def test_multilingual_backlog_shrinks_generation_packets_to_fit_input(self):
        for index in range(12):
            self.add(('漢字で学ぶ数学。'*45)[:475]+str(index))
        with patch.object(settings, 'memory_summary_input_tokens', 3000):
            for _ in range(16):
                self.run_worker()
                if self.context()['state'] == 'ready':
                    break
        self.assertEqual(self.context()['state'], 'ready')
        self.assertTrue(all(len(x['changes']) < 12 for x in self.model.calls))

    def test_pinned_priority_is_retained_in_later_incremental_packets(self):
        pinned = self.add(pinned=True)
        self.run_worker()
        self.add('Studies geometry.')
        self.run_worker()
        self.assertIn(pinned['id'], self.model.calls[-1]['pinned_supports'])

    def test_corrupt_derived_context_is_suppressed_and_rebuilt(self):
        self.add()
        self.run_worker()
        with self.db.sessions.begin() as session:
            session.execute(update(s).where(s.c.learner_id == self.owner).values(blocks=[dict(text='Corrupt unsupported prose')]))
        self.assertNotIn('Corrupt', self.context()['content'])
        self.assertEqual(self.context()['state'], 'updating')
        self.run_worker()
        self.assertIn('untoastify', self.context()['content'])

    def test_missing_delta_backlog_triggers_rebuild(self):
        self.add()
        self.run_worker()
        self.add('Studies algebra.')
        with self.db.sessions.begin() as session:
            session.execute(delete(c).where(c.c.learner_id == self.owner))
        self.run_worker()
        self.assertIn('algebra', self.context()['content'])
        self.assertEqual(self.context()['state'], 'ready')

    def test_oversized_output_gets_one_bounded_compression_repair(self):
        a = self.add()
        support = [dict(id=a['id'], revision=a['revision'])]
        self.model.ainvoke = AsyncMock(side_effect=[
            MemorySummary(blocks=[dict(text='漢字'*700, supports=support)]),
            MemorySummary(blocks=[dict(text='Maintains untoastify.', supports=support)])])
        self.run_worker()
        self.assertEqual(self.model.ainvoke.await_count, 2)
        self.assertEqual(self.context()['state'], 'ready')

    def scoped_turn(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        chats = ChatRepository(self.db.sessions)
        job = chats.begin_turn(self.owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Remember a durable project.'))
        return dict(job, _memory_summary_fence=self.repository.context(self.owner)[1])

    def test_own_write_fence_is_published_only_after_commit(self):
        from copy import deepcopy
        scope = self.scoped_turn()
        original_fence = scope['_memory_summary_fence']
        expected = deepcopy(original_fence)
        original_receipt = self.memories._receipt
        def receipt(*args, **kwargs):
            original_receipt(*args, **kwargs)
            self.assertGreater(scope['_memory_writes_pending'], 0)
            self.assertEqual(scope['_memory_summary_fence'], expected)
            self.assertTrue(self.repository.fence_current(self.owner, original_fence))
        with patch.object(self.memories, '_receipt', side_effect=receipt):
            self.memories.write(self.owner, 'Maintains untoastify.', 'fact', str(uuid4()), scope=scope)
        self.assertIsNot(scope['_memory_summary_fence'], original_fence)
        self.assertEqual(scope['_memory_writes_pending'], 0)
        self.assertTrue(self.repository.fence_current(self.owner, scope['_memory_summary_fence']))

    def test_rolled_back_write_never_advances_turn_fence(self):
        scope = self.scoped_turn()
        original_fence = scope['_memory_summary_fence']
        original_receipt = self.memories._receipt
        def receipt(*args, **kwargs):
            original_receipt(*args, **kwargs)
            raise RuntimeError('Synthetic transaction rollback')
        with patch.object(self.memories, '_receipt', side_effect=receipt), self.assertRaises(RuntimeError):
            self.memories.write(self.owner, 'Rolled back project.', 'fact', str(uuid4()), scope=scope)
        self.assertIs(scope['_memory_summary_fence'], original_fence)
        self.assertEqual(scope['_memory_writes_pending'], 0)
        self.assertTrue(self.repository.fence_current(self.owner, original_fence))

    def test_watch_ignores_old_fence_read_when_own_write_committed(self):
        from app.chat.service import ConversationService
        from app.chat.repositories.postgres import ChatRepository
        from app.langchain.activity import ActivityPublisher
        scope = self.scoped_turn()
        scope['activity'] = ActivityPublisher()
        checks = 0
        def read(owner, fence):
            nonlocal checks
            checks += 1
            if checks == 1:
                self.memories.write(owner, 'Maintains untoastify.', 'fact', str(uuid4()), scope=scope)
                return False  # Read began using the old snapshot before our commit.
            return True
        async def check():
            generation = asyncio.create_task(asyncio.sleep(.8))
            with patch.object(MemorySummaryRepository, 'fence_current', side_effect=read):
                await ConversationService(ChatRepository(self.db.sessions))._watch_active(self.owner, scope, generation, scope)
            await generation
            self.assertFalse(generation.cancelled())
        asyncio.run(check())
        self.assertNotIn('_memory_context_changed', scope)

    def test_corrupt_summary_does_not_block_canonical_edit(self):
        a = self.add()
        self.run_worker()
        with self.db.sessions.begin() as session:
            session.execute(update(s).where(s.c.learner_id == self.owner).values(blocks=[dict(text='Corrupt')]))
        self.memories.edit(self.owner, a['id'], MemoryEdit(expected_revision=a['revision'], content='Studies geometry.'))
        self.run_worker()
        self.assertIn('geometry', self.context()['content'])

    def test_corrupt_rebuild_checkpoint_is_restartable(self):
        self.add()
        with self.db.sessions.begin() as session:
            session.execute(update(j).where(j.c.learner_id == self.owner).values(rebuild=True, checkpoint=['Invalid checkpoint']))
        self.run_worker()
        self.assertEqual(self.context()['state'], 'ready')

    def test_checkpoint_from_old_prompt_is_rebuilt_from_canonical_facts(self):
        a = self.add()
        with self.db.sessions.begin() as session:
            revision = session.scalar(select(s.c.source_revision).where(s.c.learner_id == self.owner))
            checkpoint = dict(source_revision=revision, prompt_version='obsolete-prompt', cursor=a['id'], blocks=[dict(
                text='Outdated checkpoint prose.', supports=[dict(id=a['id'], revision=a['revision'])])])
            session.execute(update(j).where(j.c.learner_id == self.owner).values(rebuild=True, checkpoint=checkpoint))
        self.run_worker()
        self.assertIn('untoastify', self.context()['content'])
        self.assertNotIn('Outdated', self.context()['content'])

    def test_pending_fallback_keeps_pinned_context_before_unpinned_additions(self):
        self.add('Important pinned fact '+'.'*80, pinned=True)
        self.run_worker()
        self.add('Unpinned new fact '+'.'*150)
        with patch.object(settings, 'memory_summary_max_characters', 256):
            context = self.context()
        self.assertIn('Important pinned fact', context['content'])
