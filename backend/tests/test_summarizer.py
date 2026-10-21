import asyncio
import unittest
from unittest.mock import patch
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete
from langchain_core.messages import AIMessage
from app.auth.repositories.tables import learner
from app.chat.repositories.postgres import ChatRepository, now
from app.chat.repositories.summary_jobs import ChatSummaryJobs
from app.chat.repositories.tables import summary_jobs as jobs, summaries
from app.chat.schemas import SendTurn
from app.chat.summaries import ChatSummaryConsumer
from app.history_management.repositories.postgres import MemoryRepository
from app.history_management.repositories.memory_summaries import MemorySummaryRepository
from app.history_management.repositories.tables import summary_jobs as memory_jobs
from app.history_management.memory.summaries import MemorySummaries
from app.history_management.memory.summary_schemas import MemorySummary, bounded
from app.langchain.llm import MentraLLM
from app.langchain.prompts import PromptSource
from app.summarization.worker import Summarizer
from testing.postgres import PostgresSandbox


class Model:
    messages = MentraLLM.messages
    def __init__(self):
        self.calls = []
        self.error = False
        self.action = None

    async def ainvoke(self, source, payload, **kwargs):
        self.calls.append((source, payload))
        if self.error:
            raise RuntimeError('Synthetic provider outage')
        if self.action:
            self.action()
        if source is PromptSource.CHAT_SUMMARY:
            reference = payload['messages'][0]['id'] if payload['messages'] else 'existing summary'
            return AIMessage(content='The learner discussed geometry and requested practice; original message '+reference)
        blocks = payload['previous_summary'] + [dict(text=x['content'], supports=[dict(id=x['id'], revision=x['revision'])]) for x in payload['changes']]
        return MemorySummary(blocks=bounded(blocks))


class SummarizerTests(unittest.TestCase):
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
        self.chats = ChatRepository(self.db.sessions)
        self.queue = ChatSummaryJobs(self.db.sessions)
        self.model = Model()
        self.consumer = ChatSummaryConsumer(self.chats, self.model)

    def tearDown(self):
        with self.db.sessions.begin() as session:
            session.execute(delete(jobs).where(jobs.c.learner_id == self.owner))
            session.execute(delete(memory_jobs).where(memory_jobs.c.learner_id == self.owner))

    def exchange(self, chat=None, content='A short question.', answer='A short answer.'):
        cid = str(chat or uuid4())
        revision = self.chats.status(self.owner, cid)['conversation']['revision'] if chat else 0
        job = self.chats.begin_turn(self.owner, SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=revision, content=content))
        self.chats.finish(self.owner, job, dict(content=answer))
        return cid

    def long_chat(self):
        cid = None
        for _ in range(18):
            cid = self.exchange(cid, 'geometry '*200, 'Practice geometry '*120)
        return cid

    def due(self):
        with self.db.sessions.begin() as session:
            for table in (jobs, memory_jobs):
                session.execute(update(table).where(table.c.learner_id == self.owner).values(available_at=now()-timedelta(seconds=1)))

    def test_short_chat_queued_transactionally_but_no_model_call(self):
        cid = self.exchange()
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.target_sequence).where(jobs.c.conversation_id == cid)), 2)
        self.due()
        self.assertTrue(asyncio.run(self.consumer.run_once()))
        self.assertEqual(self.model.calls, [])
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(jobs.c.conversation_id).where(jobs.c.conversation_id == cid)))

    def test_long_chat_survives_consumer_restart_and_compacts_backlog(self):
        cid = self.long_chat()
        self.consumer = ChatSummaryConsumer(self.chats, self.model)
        for _ in range(8):
            self.due()
            if not asyncio.run(self.consumer.run_once()):
                break
        with self.db.sessions() as session:
            summary = session.execute(select(summaries).where(summaries.c.conversation_id == cid)).mappings().one()
            self.assertGreater(summary['through_sequence'], 0)
            self.assertTrue(summary['content'])
            self.assertIsNone(session.scalar(select(jobs.c.conversation_id).where(jobs.c.conversation_id == cid)))
        self.assertTrue(all(source is PromptSource.CHAT_SUMMARY for source,_ in self.model.calls))

    def test_claim_recovery_and_stale_acknowledgement(self):
        cid = self.exchange()
        self.due()
        first = self.queue.claim()
        self.assertIsNone(self.queue.claim())
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.conversation_id == cid).values(lease_until=now()-timedelta(seconds=1)))
        second = self.queue.claim()
        self.assertFalse(self.queue.finish(first))
        self.assertTrue(self.queue.finish(second))

    def test_completion_arriving_during_claim_is_not_lost(self):
        cid = self.exchange()
        self.due()
        first = self.queue.claim()
        self.exchange(cid)
        self.queue.finish(first)
        self.due()
        next_job = self.queue.claim()
        self.assertEqual(next_job['target_sequence'], 4)
        self.queue.finish(next_job)

    def test_deleted_chat_cancels_pending_work(self):
        cid = self.exchange()
        current = self.chats.status(self.owner, cid)['conversation']['revision']
        self.chats.edit(self.owner, cid, current, remove=True)
        self.due()
        self.assertFalse(asyncio.run(self.consumer.run_once()))
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(jobs.c.conversation_id).where(jobs.c.conversation_id == cid)))

    def test_provider_failure_is_durable_and_explicitly_retryable(self):
        cid = self.long_chat()
        self.model.error = True
        for _ in range(5):
            self.due()
            asyncio.run(self.consumer.run_once())
        with self.db.sessions() as session:
            self.assertTrue(session.scalar(select(jobs.c.failed).where(jobs.c.conversation_id == cid)))
        self.model.error = False
        self.queue.retry(self.owner, cid)
        self.due()
        asyncio.run(self.consumer.run_once())
        with self.db.sessions() as session:
            self.assertTrue(session.scalar(select(summaries.c.content).where(summaries.c.conversation_id == cid)))

    def test_shared_worker_processes_both_types_with_same_model(self):
        self.long_chat()
        MemoryRepository(self.db.sessions).write(self.owner, 'Maintains untoastify.', 'fact', str(uuid4()))
        memory = MemorySummaries(MemorySummaryRepository(self.db.sessions), self.model)
        worker = Summarizer(memory, self.consumer)
        self.due()
        async def consume():
            await worker.run_once()
            await worker.run_once()
        asyncio.run(consume())
        self.assertEqual({source for source,_ in self.model.calls}, {PromptSource.CHAT_SUMMARY, PromptSource.MEMORY_SUMMARY})

    def test_queue_scheduling_is_fair_with_one_slot(self):
        class Consumer:
            def __init__(inner): inner.calls = 0
            async def run_once(inner): inner.calls += 1; return True
        memory, chat = Consumer(), Consumer()
        worker = Summarizer(memory, chat)
        async def consume():
            for _ in range(10): await worker.run_once()
        asyncio.run(consume())
        self.assertEqual((memory.calls, chat.calls), (5,5))

    def test_diagnostics_are_separate_and_count_pending_chats(self):
        self.exchange()
        self.assertEqual(self.queue.diagnostics()['pending'], 1)
        self.assertEqual(self.queue.diagnostics()['failed'], 0)

    def test_queue_insert_rolls_back_with_failed_completion(self):
        from app.chat.repositories.summary_jobs import queue
        cid = str(uuid4())
        job = self.chats.begin_turn(self.owner, SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=0, content='A question.'))
        def fail(session, owner, chat, sequence):
            queue(session, owner, chat, sequence)
            raise RuntimeError('Synthetic rollback')
        with patch('app.chat.repositories.summary_jobs.queue', side_effect=fail), self.assertRaises(RuntimeError):
            self.chats.finish(self.owner, job, dict(content='An answer.'))
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(jobs.c.conversation_id).where(jobs.c.conversation_id == cid)))
        self.assertEqual(self.chats.status(self.owner, cid)['turn']['state'], 'RUNNING')

    def test_api_completion_never_runs_summary_generation(self):
        from app.chat.service import ConversationService
        cid = self.long_chat()
        revision = self.chats.status(self.owner, cid)['conversation']['revision']
        async def reply(*args):
            return dict(content='A normal reply.')
        asyncio.run(ConversationService(self.chats, summary_llm=self.model).send(self.owner,
            SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=revision, content='Continue this discussion.'), reply))
        self.assertEqual(self.model.calls, [])

    def test_chat_deleted_during_generation_cannot_publish(self):
        cid = self.long_chat()
        revision = self.chats.status(self.owner, cid)['conversation']['revision']
        self.model.action = lambda: self.chats.edit(self.owner, cid, revision, remove=True)
        self.due()
        asyncio.run(self.consumer.run_once())
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(summaries.c.content).where(summaries.c.conversation_id == cid)))

    def test_long_multilingual_exchange_is_compacted_instead_of_dropped(self):
        cid = self.exchange(content='漢字數學幾何'*500, answer='漢字數學幾何'*1200)
        self.exchange(cid)
        self.due()
        asyncio.run(self.consumer.run_once())
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(summaries.c.through_sequence).where(summaries.c.conversation_id == cid)), 2)
        self.assertEqual(self.model.calls[0][1]['messages'][-1]['sequence'], 2)

    def test_oversized_existing_summary_is_repaired_without_new_history(self):
        from app.chat.repositories.summaries import SummaryRepository
        from app.chat.summaries import ConversationSummaries
        cid = self.exchange()
        repository = SummaryRepository(self.chats)
        claim = repository.claim(self.owner, cid)
        repository.publish(self.owner, cid, claim, 'Old summary '*300, 2)
        self.due()
        asyncio.run(self.consumer.run_once())
        with self.db.sessions() as session:
            repaired = session.execute(select(summaries).where(summaries.c.conversation_id == cid)).mappings().one()
            self.assertEqual(repaired['through_sequence'], 2)
            self.assertLess(len(repaired['content']), 2400)
        self.assertIsNotNone(asyncio.run(ConversationSummaries(self.chats, self.model).load(self.owner, cid)))

    def test_loading_rejected_summary_requeues_repair(self):
        from app.chat.repositories.summaries import SummaryRepository
        from app.chat.summaries import ConversationSummaries
        cid = self.exchange()
        repository = SummaryRepository(self.chats)
        claim = repository.claim(self.owner, cid)
        repository.publish(self.owner, cid, claim, 'Old summary '*300, 2)
        with self.db.sessions.begin() as session:
            session.execute(delete(jobs).where(jobs.c.conversation_id == cid))
        self.assertIsNone(asyncio.run(ConversationSummaries(self.chats, self.model).load(self.owner, cid)))
        self.assertEqual(self.queue.diagnostics()['pending'], 1)

    def test_chat_summary_input_reserves_space_in_configured_model_window(self):
        from app.core.config import settings
        from app.core.exceptions import AppError
        from app.langchain.token_policy import check_input
        from langchain_core.messages import HumanMessage
        small = settings.model_copy(update={'chat_context_window_tokens': 4096})
        with self.assertRaises(AppError):
            check_input([HumanMessage(content='token '*4000)], PromptSource.CHAT_SUMMARY, config=small)
