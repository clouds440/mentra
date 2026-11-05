import unittest
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select, update
from app.learner.maintenance_worker import LearnerMaintenanceWorker
from app.learner.repositories.tables.maintenance import maintenance_jobs as jobs
from app.learner.repositories.tables.topics import topic_skill
from app.assessments.schemas import GenerationRequest
from app.langchain.concept_identity import ConceptIdentityResolver
from tests import test_assessment_flexibility as fixtures


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixtures.FlexibleEngineTests.setUp(self)
        self.learner.generated_concepts.resolver = ConceptIdentityResolver(self.service.workflows.llm)

    async def generate(self):
        return await self.service.generate(self.owner, GenerationRequest(client_request_id=uuid4(),
            context_id=self.context.context_id, topic='Reasoning', question_format='mcq', count=2))

    async def test_publication_atomically_queues_grouping_and_worker_preserves_skill_ids(self):
        result = await self.generate()
        ids = result.questions[0].concept_ids
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.state)), 'queued')
            self.assertIsNone(session.scalar(select(topic_skill.c.topic_id).where(topic_skill.c.concept_id==ids[0])))
        self.assertTrue(await LearnerMaintenanceWorker(self.learner).run_once())
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.state)), 'completed')
            self.assertIsNotNone(session.scalar(select(topic_skill.c.topic_id).where(topic_skill.c.concept_id==ids[0])))
        self.assertEqual(self.service.repository.detail(self.owner,str(result.id)).questions[0].concept_ids, ids)

    async def test_claim_recovery_stale_finish_fence_and_overlapping_publication(self):
        await self.generate()
        repository = self.learner.repository
        old = repository.claim_maintenance()
        self.assertIsNone(repository.claim_maintenance())
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).values(claim_until=self.learner.clock()-timedelta(seconds=1)))
        current = repository.claim_maintenance()
        self.assertFalse(repository.finish_maintenance(old))
        repository.enqueue_maintenance(self.owner,self.context.context_id)
        self.assertTrue(repository.finish_maintenance(current))
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.state)), 'queued')

    async def test_failed_publication_does_not_queue_grouping(self):
        from unittest.mock import patch
        with patch.object(self.service.repository,'save',side_effect=RuntimeError('publication interrupted')):
            with self.assertRaises(RuntimeError): await self.generate()
        with self.db.sessions() as session:
            self.assertEqual(list(session.scalars(select(jobs.c.state))), [])
