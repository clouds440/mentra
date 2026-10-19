import os
import unittest
from uuid import uuid4
from sqlalchemy import select, update
from app.assessments.schemas import RevisionPracticeRequest, StartAttempt
from app.assessments.repositories.revision_practice import list_mistakes, enqueue_revision
from app.assessments.repositories.tables import attempts, generation_jobs
from app.assessments.generation_worker import AssessmentGenerationWorker
from app.core.exceptions import AppError
from tests.test_assessments import AssessmentTests
from tests.test_product_followups import ProductFollowupTests


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated PostgreSQL')
class RevisionPracticeTests(unittest.IsolatedAsyncioTestCase):
    setUp = AssessmentTests.setUp
    graded = ProductFollowupTests.graded

    async def test_catalog_owner_filters_priority_and_private_keys(self):
        source, result = await self.graded()
        page = list_mistakes(self.service.repository, self.owner)
        self.assertEqual(page['total'], 5)
        self.assertEqual(page['active_count'], 5)
        self.assertEqual(page['items'][0]['score'], 0)
        self.assertEqual(page['items'][0]['attempt_id'], str(result.id))
        self.assertNotIn('model_answer', str(page))
        self.assertNotIn('rubric', str(page))
        self.assertEqual(list_mistakes(self.service.repository, self.other)['total'], 0)
        self.assertEqual(list_mistakes(self.service.repository, self.owner, [str(uuid4())])['total'], 0)
        self.assertEqual(list_mistakes(self.service.repository, self.owner, [], ['unknown'])['total'], 0)
        self.assertEqual(list_mistakes(self.service.repository, self.owner, [str(source.id)])['total'], 5)

    async def test_queued_variations_have_server_tags_sources_and_exposure(self):
        source, result = await self.graded()
        body = RevisionPracticeRequest(client_request_id=uuid4(), count=3)
        job = enqueue_revision(self.service, self.owner, body)
        self.assertEqual(enqueue_revision(self.service, self.owner, body)['id'], job['id'])
        with self.db.sessions() as session:
            snapshot = session.execute(select(generation_jobs.c.progress).where(generation_jobs.c.id == job['id'])).scalar_one()['mistake_revision']
        self.assertEqual({q['question_id'] for q in snapshot['sources']}, {str(q.id) for q in source.questions[:3]})
        await AssessmentGenerationWorker(self.service).run_once()
        finished = self.service.generation_jobs.get(self.owner, job['id'])
        self.assertEqual(finished['state'], 'completed', finished)
        child = self.service.repository.detail(self.owner, finished['result']['id'])
        self.assertEqual(child.tags, ['revision assessment'])
        self.assertEqual(list(map(str, child.source_assessment_ids)), [str(source.id)])
        self.assertEqual(len(child.questions), 3)
        self.assertTrue(all(q.prompt not in {x.prompt for x in source.questions} for q in child.questions))
        start = self.service.repository.start(self.owner, str(child.id), StartAttempt(client_request_id=uuid4()))
        self.assertEqual(start.assistance, 'assisted')
        self.assertEqual(self.service.repository.detail(self.owner, str(source.id)), source)
        with self.assertRaises(AppError):
            enqueue_revision(self.service, self.owner, body.model_copy(update={'count': 2}))

    async def test_corrected_roots_remain_visible_but_do_not_generate(self):
        source, result = await self.graded()
        attempt = self.service.repository.start(self.owner, str(source.id), StartAttempt(client_request_id=uuid4()))
        grades = [dict(grade.model_dump(mode='json'), score=source.questions[index].marks) for index, grade in enumerate(result.grades or [])]
        # Store a later graded observation; earlier mistakes remain reviewable.
        with self.db.sessions.begin() as session:
            session.execute(update(attempts).where(attempts.c.id == str(attempt.id)).values(state='graded', grades=grades, submitted_at=self.service.repository.clock()))
        page = list_mistakes(self.service.repository, self.owner)
        self.assertEqual(page['total'], 5)
        self.assertEqual(page['active_count'], 0)
        with self.assertRaises(AppError) as error:
            enqueue_revision(self.service, self.owner, RevisionPracticeRequest(client_request_id=uuid4()))
        self.assertEqual(error.exception.code, 'NO_PRACTICE_MISTAKES')

    async def test_foreign_sources_rejected_and_multi_source_snapshot_survives_retry(self):
        first, _ = await self.graded()
        second, _ = await self.graded()
        body = RevisionPracticeRequest(client_request_id=uuid4(), assessment_ids=[first.id, second.id], count=10)
        with self.assertRaises(AppError): enqueue_revision(self.service, self.other, body)
        job = enqueue_revision(self.service, self.owner, body)
        with self.db.sessions.begin() as session:
            before = session.scalar(select(generation_jobs.c.progress).where(generation_jobs.c.id == job['id']))
            session.execute(update(generation_jobs).where(generation_jobs.c.id == job['id']).values(state='failed'))
        self.service.generation_jobs.retry(self.owner, job['id'])
        with self.db.sessions() as session:
            after = session.scalar(select(generation_jobs.c.progress).where(generation_jobs.c.id == job['id']))
        self.assertEqual(before, after)
        self.assertEqual(set(before['mistake_revision']['source_assessment_ids']), {str(first.id), str(second.id)})
        await AssessmentGenerationWorker(self.service).run_once()
        finished = self.service.generation_jobs.get(self.owner, job['id'])
        self.assertEqual(finished['state'], 'completed', finished)
        self.assertEqual(set(finished['result']['source_assessment_ids']), {str(first.id), str(second.id)})


    async def test_cross_context_revision_grades_keep_per_question_evidence_provenance(self):
        from app.learner.schemas import ResolveLearningContextRequest
        from app.assessments.schemas import SubmitAnswers
        from app.learner.repositories.tables.evidence import learning_evidence
        from testing.assessment_workers import run_assessment_pipeline
        first, first_attempt = await self.graded()
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Mechanics'))
        self.request = self.request.model_copy(update={'context_id': context.context_id, 'topic':'Forces', 'concept_names':['Newton laws']})
        second, second_attempt = await self.graded()
        job = enqueue_revision(self.service, self.owner, RevisionPracticeRequest(client_request_id=uuid4(), count=10))
        await AssessmentGenerationWorker(self.service).run_once()
        finished = self.service.generation_jobs.get(self.owner, job['id'])
        self.assertEqual(finished['state'], 'completed', finished)
        child = self.service.repository.detail(self.owner, finished['result']['id'])
        attempt = self.service.repository.start(self.owner, str(child.id), StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=1, client_request_id=uuid4(),
            answers={str(q.id):'a' for q in child.questions}, assistance='independent'))
        await run_assessment_pipeline(self.service)
        self.assertEqual(self.service.repository.attempt(self.owner, str(attempt.id)).evidence_status, 'applied')
        with self.db.sessions() as session:
            rows = session.execute(select(learning_evidence).where(learning_evidence.c.session_id == str(attempt.id))).mappings().all()
        self.assertEqual({r['context_id'] for r in rows}, {first.context_id, second.context_id})
        self.assertTrue(all(r['independence']==0 for r in rows))
        page = list_mistakes(self.service.repository, self.owner)
        self.assertEqual(page['active_count'], 0)
        self.assertEqual(page['total'], 10)

    async def test_concurrent_enqueue_is_idempotent_and_caps_active_jobs(self):
        from concurrent.futures import ThreadPoolExecutor
        await self.graded()
        body = RevisionPracticeRequest(client_request_id=uuid4())
        with ThreadPoolExecutor(2) as pool:
            jobs = list(pool.map(lambda _: enqueue_revision(self.service, self.owner, body), range(2)))
        self.assertEqual(jobs[0]['id'], jobs[1]['id'])
        enqueue_revision(self.service, self.owner, body.model_copy(update={'client_request_id':uuid4()}))
        with self.assertRaises(AppError) as error:
            enqueue_revision(self.service, self.owner, body.model_copy(update={'client_request_id':uuid4()}))
        self.assertEqual(error.exception.code, 'ASSESSMENT_GENERATION_BUSY')

    async def test_http_catalog_filters_and_rejects_forged_revision_metadata(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.assessments import router
        from app.student_profile.dependencies import require_onboarded_identity
        source, _ = await self.graded()
        app = FastAPI()
        app.state.assessment_service = self.service
        app.dependency_overrides[require_onboarded_identity] = lambda: SimpleNamespace(learner_id=self.owner)
        app.include_router(router, prefix='/api/v1')
        with TestClient(app) as client:
            response = client.get('/api/v1/assessments/mistakes', params={'assessment_id':str(source.id)})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.json()['total'], 5)
            body = dict(client_request_id=str(uuid4()), assessment_ids=[str(source.id)], count=2)
            forged = client.post('/api/v1/assessments/mistakes/practice', json=dict(body,tags=['revision assessment'],source_assessment_ids=[str(uuid4())]))
            self.assertEqual(forged.status_code, 422)
            created = client.post('/api/v1/assessments/mistakes/practice', json=body)
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()['state'], 'queued')
            self.assertNotIn('mistake_revision',created.text)
