import asyncio
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import select, update
from app.assessments.generation_worker import AssessmentGenerationWorker
from app.assessments.repositories.tables import generation_jobs, assessments
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.core.exceptions import AppError
from tests import test_assessment_flexibility as flexible


class GenerationStopTests(unittest.IsolatedAsyncioTestCase):
    setUp = flexible.FlexibleEngineTests.setUp
    request = flexible.FlexibleEngineTests.request

    async def test_stop_cancels_selection_before_question_generation(self):
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def select(*args):
            started.set()
            try: await asyncio.sleep(30)
            finally: cancelled.set()
        job = await self.service.queue_generation(self.owner, self.request(count=12))
        with patch('app.langchain.assessment_selection.resolve_assessment_intent', side_effect=select):
            work = asyncio.create_task(AssessmentGenerationWorker(self.service).run_once())
            await asyncio.wait_for(started.wait(), 3)
            with self.assertRaises(AppError): self.service.generation_jobs.stop(self.other, job['id'], 1)
            paused = self.service.generation_jobs.stop(self.owner, job['id'], 1)
            self.assertEqual(paused['state'], 'stopped')
            await asyncio.wait_for(cancelled.wait(), 3)
            await asyncio.wait_for(work, 3)
        self.assertEqual(self.service.generation_jobs.get(self.owner, job['id'])['state'], 'stopped')

    async def test_checkpoint_preserved_resume_fenced_expiry_private_and_publication_wins(self):
        job = await self.service.queue_generation(self.owner, self.request(count=12))
        claimed = self.service.generation_jobs.claim()
        self.service.generation_jobs.update(claimed, progress={'resolved_request':claimed['request'], 'questions':[{'model_answer':'private unfinished answer'}]})
        paused = self.service.generation_jobs.stop(self.owner, job['id'], 1)
        self.assertTrue(paused['can_resume'])
        self.assertNotIn('model_answer', str(paused))
        self.assertEqual(self.service.generation_jobs.stop(self.owner, job['id'], 1)['state'], 'stopped')
        with self.assertRaises(AppError): self.service.generation_jobs.update(claimed, state='completed')
        self.service.generation_jobs.retry(self.owner, job['id'])
        with self.assertRaises(AppError): self.service.generation_jobs.stop(self.owner, job['id'], 1)
        newer = self.service.generation_jobs.claim()
        self.assertIn('questions', newer['progress'])
        self.service.generation_jobs.stop(self.owner, job['id'], 2)
        with self.db.sessions.begin() as session:
            session.execute(update(generation_jobs).where(generation_jobs.c.id == job['id']).values(resume_until=self.service.repository.clock()-timedelta(seconds=1)))
        self.assertFalse(self.service.generation_jobs.get(self.owner, job['id'])['can_resume'])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(generation_jobs.c.progress).where(generation_jobs.c.id == job['id'])), {})
        # A late Stop must return the already-published result, even before the
        # worker has updated its job status.
        request = self.request(count=1)
        queued = await self.service.queue_generation(self.owner, request)
        saved = await self.service.generate(self.owner, request)
        late = self.service.generation_jobs.stop(self.owner, queued['id'], 1)
        self.assertEqual(late['state'], 'completed')
        self.assertEqual(late['result']['id'], str(saved.id))
        with self.db.sessions() as session: self.assertIsNotNone(session.scalar(select(assessments.c.id).where(assessments.c.id == str(saved.id))))

    async def test_composer_stop_reaches_background_generation_after_reply_finished(self):
        chat = ChatRepository(self.db.sessions)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Give me an assessment')
        turn = chat.begin_turn(self.owner, request)
        job = await self.service.queue_generation(self.owner, self.request(count=12), turn['conversation_id'], turn['turn_id'])
        chat.finish(self.owner, turn, dict(content='Building your assessment', assessment_cards=[dict(id=job['id'],generation_job_id=job['id'],title='Science')]))
        self.assertTrue(chat.status(self.owner, turn['conversation_id'])['turn']['can_stop'])
        chat.stop_turn(self.owner, turn['conversation_id'], turn['turn_id'], 1)
        self.assertEqual(self.service.generation_jobs.get(self.owner, job['id'])['state'], 'stopped')
        page = chat.status(self.owner, turn['conversation_id'])
        self.assertTrue(page['turn']['can_resume'])
        self.assertEqual(len(page['items']), 2)
        chat.resume_turn(self.owner, turn['conversation_id'], turn['turn_id'], 1, page['conversation']['revision'])
        self.assertEqual(self.service.generation_jobs.get(self.owner, job['id'])['state'], 'queued')

    async def test_repaused_job_and_older_source_preserve_newer_messages(self):
        chat = ChatRepository(self.db.sessions)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Give me an assessment')
        turn = chat.begin_turn(self.owner, request)
        job = await self.service.queue_generation(self.owner, self.request(count=12), turn['conversation_id'], turn['turn_id'])
        chat.finish(self.owner, turn, dict(content='Building your assessment'))
        page = chat.status(self.owner, turn['conversation_id'])
        newer_request = request.model_copy(update={'client_turn_id':uuid4(), 'content':'A different question', 'expected_revision':page['conversation']['revision']})
        newer = chat.begin_turn(self.owner, newer_request)
        chat.finish(self.owner, newer, dict(content='The newer answer'))
        self.assertTrue(chat.stop_turn(self.owner, turn['conversation_id'], turn['turn_id'], 1))
        page = chat.status(self.owner, turn['conversation_id'])
        self.assertEqual(page['conversation']['message_count'], 4)
        self.assertEqual([item['sequence'] for item in page['items']], [1,2,3,4])
        self.service.generation_jobs.retry(self.owner, job['id'])  # Native card resume leaves the old source paused.
        with self.assertRaises(AppError):
            chat.stop_turn(self.owner, turn['conversation_id'], turn['turn_id'], 1, stopped_job=(job['id'], 1))
        self.assertEqual(self.service.generation_jobs.get(self.owner, job['id'])['state'], 'queued')
        self.assertTrue(chat.stop_turn(self.owner, turn['conversation_id'], turn['turn_id'], 1))
        self.assertEqual(self.service.generation_jobs.get(self.owner, job['id'])['state'], 'stopped')
        page = chat.status(self.owner, turn['conversation_id'])
        self.assertEqual(page['conversation']['message_count'], 4)
        self.assertEqual(page['turn']['id'], newer['turn_id'])
        next_request = request.model_copy(update={'client_turn_id':uuid4(), 'content':'One more', 'expected_revision':page['conversation']['revision']})
        self.assertEqual(chat.begin_turn(self.owner, next_request)['user_sequence'], 5)

    async def test_response_resume_honors_owner_queue_capacity(self):
        chat = ChatRepository(self.db.sessions)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Make a paper')
        turn = chat.begin_turn(self.owner, request)
        paused_job = await self.service.queue_generation(self.owner, self.request(count=12), turn['conversation_id'], turn['turn_id'])
        chat.stop_turn(self.owner, turn['conversation_id'], turn['turn_id'], 1)
        await self.service.queue_generation(self.owner, self.request(count=12))
        await self.service.queue_generation(self.owner, self.request(count=12))
        page = chat.status(self.owner, turn['conversation_id'])
        with self.assertRaises(AppError) as caught:
            chat.resume_turn(self.owner, turn['conversation_id'], turn['turn_id'], 1, page['conversation']['revision'])
        self.assertEqual(caught.exception.code, 'ASSESSMENT_GENERATION_BUSY')
        self.assertEqual(self.service.generation_jobs.get(self.owner, paused_job['id'])['state'], 'stopped')
