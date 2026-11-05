"""An owned handoff is complete and fresh without transferring attempt history."""
import unittest
from uuid import uuid4
from sqlalchemy import update
from app.assessments.schemas import StartAttempt, AssessmentIntent
from app.assessments.repositories.tables import attempts, generation_jobs
from app.core.exceptions import AppError
from tests import test_assessments as fixtures, test_chat_assessments as chat_fixtures


class AssessmentHandoffTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.AssessmentTests.setUp
    conversation = chat_fixtures.ChatAssessmentTests.conversation

    async def card(self):
        conversation = self.conversation()
        card = await self.service.generate_chat(self.owner, conversation, self.request)
        return conversation, self.service.chat.publish(self.owner, card['id'])

    async def test_owned_detail_is_complete_without_keys_or_history(self):
        _, card = await self.card()
        value = self.service.chat.detail(self.owner, card['id'])
        self.assertEqual(value['hydration'], dict(version=1, attempt=None))
        self.assertNotIn('model_answer', str(value))
        self.assertNotIn('rubric', str(value))
        with self.assertRaises(AppError):
            self.service.chat.detail(self.other, card['id'])

    async def test_current_meaningful_attempt_wins_over_unused_retry(self):
        _, card = await self.card()
        attempt = self.service.repository.start(self.owner, card['assessment_id'], StartAttempt(client_request_id=uuid4()))
        with self.db.sessions.begin() as session:
            session.execute(update(attempts).where(attempts.c.id == str(attempt.id)).values(
                state='graded', grades=[], evidence_status='applied', revision=2))
        unused = self.service.repository.start(self.owner, card['assessment_id'], StartAttempt(client_request_id=uuid4()))
        self.assertNotEqual(attempt.id, unused.id)
        value = self.service.chat.detail(self.owner, card['id'])['hydration']['attempt']
        self.assertEqual(value['id'], str(attempt.id))
        self.assertEqual(value['state'], 'graded')

    async def test_completed_job_refreshes_attempt_state_in_one_handoff(self):
        conversation, card = await self.card()
        job = self.service.generation_jobs.enqueue(self.owner, AssessmentIntent.model_validate(
            self.request.model_copy(update={'client_request_id': uuid4()}).model_dump()), conversation)
        with self.db.sessions.begin() as session:
            session.execute(update(generation_jobs).where(generation_jobs.c.id == job['id']).values(
                state='completed', result=card))
        first = self.service.generation_jobs.get(self.owner, job['id'])
        self.assertIsNone(first['hydration']['attempt'])
        attempt = self.service.repository.start(self.owner, card['assessment_id'], StartAttempt(client_request_id=uuid4()))
        latest = self.service.generation_jobs.get(self.owner, job['id'])
        self.assertEqual(latest['hydration']['attempt']['id'], str(attempt.id))
        with self.assertRaises(AppError):
            self.service.generation_jobs.get(self.other, job['id'])
        self.service.repository.remove(self.owner, card['assessment_id'])
        deleted = self.service.generation_jobs.get(self.owner, job['id'])
        self.assertTrue(deleted['result']['deleted'])
        self.assertIsNone(deleted['hydration']['attempt'])
