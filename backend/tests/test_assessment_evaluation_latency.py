"""Bounded concurrent grading and results-before-learning regression checks."""
import asyncio
import copy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import select, func, update
from app.core.config import Settings
from app.core.exceptions import AppError
from app.assessments.schemas import GradedAssessment, StartAttempt, SubmitAnswers
from app.assessments.grading_progress import grading_signature
from app.assessments.worker import AssessmentWorker
from app.assessments.evidence_worker import AssessmentEvidenceWorker
from app.assessments.repositories.tables import evidence_jobs
from app.learner.repositories.tables.evidence import learning_evidence
from app.langchain.assessment_workflows import AssessmentWorkflows
from app.langchain.grading_batches import plan_grading_batches, grading_payload
from tests import test_assessment_flexibility as flexible


def synthetic_job(count=20):
    questions = [dict(id=f'q{i}', prompt=f'Explain React state {i}', rubric='Credit correct reasoning',
        context='', model_answer='State updates schedule renders.', marks=2, concept_ids=['react-state'], options=[])
        for i in range(count)]
    return dict(assessment=dict(questions=questions), attempt=dict(answers={q['id']: 'An explanation' for q in questions},
        extraction=None, grade_revision=1))


class SyntheticGrader:
    def __init__(self):
        self.model_factory = SimpleNamespace(_settings=Settings(assessment_grading_output_tokens=4096))
        self.calls = []; self.active = 0; self.peak = 0; self.fail_second = False; self.cancelled = False

    async def ainvoke(self, source, payload, **kwargs):
        self.calls.append(payload)
        self.active += 1; self.peak = max(self.peak, self.active)
        try:
            second = payload['questions'][0]['id'] != 'q0'
            await asyncio.sleep(.025 if second else .001)
            if second and self.fail_second:
                raise RuntimeError('Synthetic provider failure')
            return GradedAssessment(questions=[dict(question_id=q['id'], score=1, confidence=.95,
                feedback='Partly correct.') for q in payload['questions']])
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            self.active -= 1


class EvaluationBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_regular_assessment_uses_one_call(self):
        llm = SyntheticGrader(); job = synthetic_job(8)
        result = await AssessmentWorkflows(llm, None).grade(job)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(len(result.questions), 8)

    async def test_objective_answers_need_no_model_requests(self):
        llm = SyntheticGrader(); job = synthetic_job(20)
        for q in job['assessment']['questions']:
            q.update(options=[dict(id='a', label='Correct'), dict(id='b', label='Incorrect')], correct_option_id='a')
            job['attempt']['answers'][q['id']] = 'a'
        result = await AssessmentWorkflows(llm, None).grade(job)
        self.assertEqual(llm.calls, [])
        self.assertEqual(sum(grade.score for grade in result.questions), 40)

    async def test_twenty_questions_use_two_concurrent_calls_in_question_order(self):
        llm = SyntheticGrader(); job = synthetic_job()
        result = await AssessmentWorkflows(llm, None).grade(job)
        self.assertEqual([len(call['questions']) for call in llm.calls], [10, 10])
        self.assertEqual(llm.peak, 2)
        self.assertEqual([grade.question_id for grade in result.questions], [q['id'] for q in job['assessment']['questions']])
        self.assertEqual({q['id']: call['answers'][q['id']] for call in llm.calls for q in call['questions']}, job['attempt']['answers'])

    async def test_full_mock_paper_with_forty_parts_uses_two_concurrent_packets(self):
        llm = SyntheticGrader(); llm.model_factory._settings = Settings(assessment_grading_output_tokens=8192)
        job = synthetic_job(40)
        result = await AssessmentWorkflows(llm, None).grade(job)
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(llm.peak, 2)
        self.assertEqual(len(result.questions), 40)

    async def test_completed_batch_survives_failure_and_retry(self):
        llm = SyntheticGrader(); llm.fail_second = True; job = synthetic_job(); saved = []
        async def checkpoint(grades): saved[:] = copy.deepcopy(grades)
        with self.assertRaises(RuntimeError):
            await AssessmentWorkflows(llm, None).grade(job, checkpoint=checkpoint)
        self.assertEqual(len(saved), 10)
        job['attempt']['grading_progress'] = dict(signature=grading_signature(job), grades=[g.model_dump() for g in saved])
        llm.fail_second = False; llm.calls.clear()
        result = await AssessmentWorkflows(llm, None).grade(job)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(len(result.questions), 20)

    async def test_cancelled_grading_drains_both_requests(self):
        llm = SyntheticGrader()
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(AssessmentWorkflows(llm, None).grade(synthetic_job()), .005)
        self.assertEqual(llm.active, 0)
        self.assertTrue(llm.cancelled)

    async def test_context_overflow_never_spawns_more_batches_or_trims_answers(self):
        llm = SyntheticGrader(); job = synthetic_job()
        job['attempt']['answers'] = {key: 'A complex answer ' * 20000 for key in job['attempt']['answers']}
        original = copy.deepcopy(job)
        with self.assertRaises(AppError) as error:
            plan_grading_batches(llm, job['assessment'], job['attempt'], job['assessment']['questions'])
        self.assertEqual(error.exception.code, 'AI_CONTEXT_LIMIT')
        self.assertEqual(job, original)
        self.assertEqual(llm.calls, [])

    async def test_packet_keeps_complete_answer_and_rubric_without_source_receipts(self):
        job = synthetic_job(1); q = job['assessment']['questions'][0]
        q['sources'] = ['private retrieval metadata']; q['rubric'] = 'Full rubric ' * 1000
        packet = grading_payload(job['assessment'], job['attempt'], [q])
        self.assertEqual(packet['questions'][0]['rubric'], q['rubric'])
        self.assertNotIn('sources', packet['questions'][0])

    async def test_timeout_stops_automatic_retries_without_resetting_answers(self):
        job = synthetic_job(1); job['id'] = 'attempt'
        failed = []
        async def slow(*args, **kwargs): await asyncio.sleep(5)
        repo = SimpleNamespace(claim=lambda: job, checkpoint_grades=lambda *args: None,
            fail=lambda *args, **kwargs: failed.append(kwargs))
        service = SimpleNamespace(repository=repo, workflows=SimpleNamespace(grade=slow))
        with patch('app.assessments.grading_progress.GRADING_TIMEOUT_SECONDS', .005):
            await AssessmentWorker(service).run_once()
        self.assertFalse(failed[0]['retry'])
        self.assertIn('answers are saved', failed[0]['error'])


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires isolated PostgreSQL')
class ResultsBeforeLearningTests(unittest.IsolatedAsyncioTestCase):
    setUp = flexible.FlexibleEngineTests.setUp
    request = flexible.FlexibleEngineTests.request

    async def prepared(self):
        assessment = await self.service.generate(self.owner, self.request(count=6, question_format='written'))
        attempt = self.service.repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
        answers = {str(q.id): 'A supported explanation.' for q in assessment.questions}
        self.service.submit(self.owner, str(attempt.id), SubmitAnswers(client_request_id=uuid4(), expected_revision=1, answers=answers))
        return assessment, attempt, answers

    async def test_results_publish_without_executing_learning_and_background_is_idempotent(self):
        assessment, attempt, answers = await self.prepared()
        original = self.service.workflows.evidence
        def forbidden(*args): raise AssertionError('Results must not wait for learning')
        self.service.workflows.evidence = forbidden
        await AssessmentWorker(self.service).run_once()
        result = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual((result.state, result.evidence_status), ('graded', 'pending'))
        self.assertEqual(result.answers, answers)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)), 0)
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_jobs)), 1)
        self.service.workflows.evidence = original
        worker = AssessmentEvidenceWorker(self.service)
        self.assertTrue(await worker.run_once())
        self.assertFalse(await worker.run_once())
        final = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual((final.state, final.evidence_status), ('graded', 'applied'))
        self.assertEqual(final.grades, result.grades)

    async def test_learning_failure_never_hides_results_or_rolls_back_grades(self):
        _, attempt, _ = await self.prepared()
        await AssessmentWorker(self.service).run_once()
        original = self.service.workflows.evidence
        def broken(*args): raise RuntimeError('Synthetic learning outage')
        self.service.workflows.evidence = broken
        await AssessmentEvidenceWorker(self.service).run_once()
        result = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual((result.state, result.evidence_status), ('graded', 'pending'))
        self.service.workflows.evidence = original
        with self.db.sessions.begin() as session:
            session.execute(update(evidence_jobs).values(retry_at=self.service.repository.clock()))
        await AssessmentEvidenceWorker(self.service).run_once()
        self.assertEqual(self.service.repository.attempt(self.owner, str(attempt.id)).evidence_status, 'applied')

    async def test_correction_skips_stale_learning_and_preserves_grade_history(self):
        _, attempt, answers = await self.prepared()
        await AssessmentWorker(self.service).run_once()
        worker = AssessmentEvidenceWorker(self.service)
        stale = worker.jobs.claim()
        graded = self.service.repository.attempt(self.owner, str(attempt.id))
        self.service.repository.correct(self.owner, str(attempt.id), SubmitAnswers(client_request_id=uuid4(),
            expected_revision=graded.revision, answers={key: 'Corrected explanation.' for key in answers}))
        await AssessmentWorker(self.service).run_once()
        worker.jobs.complete(stale, lambda tx: self.fail('Stale revision must never write evidence'))
        await worker.run_once()
        final = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual((final.grade_revision, final.evidence_status), (2, 'applied'))
        self.assertEqual(len(final.grade_history), 1)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)), 6)

    async def test_deleting_assessment_cascades_its_background_jobs(self):
        assessment, _, _ = await self.prepared()
        await AssessmentWorker(self.service).run_once()
        self.service.repository.remove(self.owner, str(assessment.id))
        self.assertFalse(await AssessmentEvidenceWorker(self.service).run_once())
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_jobs)), 0)

    async def test_crashed_final_learning_retry_becomes_unavailable_without_affecting_results(self):
        from datetime import timedelta
        _, attempt, _ = await self.prepared()
        await AssessmentWorker(self.service).run_once()
        worker = AssessmentEvidenceWorker(self.service)
        worker.jobs.claim()
        with self.db.sessions.begin() as session:
            session.execute(update(evidence_jobs).values(attempts=3,
                claim_until=self.service.repository.clock() - timedelta(seconds=1)))
        self.assertFalse(await worker.run_once())
        result = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual((result.state, result.evidence_status), ('graded', 'unavailable'))
        self.assertEqual(len(result.grades), 6)

    async def test_background_correction_retains_previous_receipts_and_withdraws_uncertain_evidence(self):
        from app.assessments.repositories.tables import attempts
        from app.learner.repositories.tables.evidence import evidence_decision
        _, attempt, answers = await self.prepared()
        await AssessmentWorker(self.service).run_once()
        await AssessmentEvidenceWorker(self.service).run_once()
        result = self.service.repository.attempt(self.owner, str(attempt.id))
        self.service.repository.correct(self.owner, str(attempt.id), SubmitAnswers(client_request_id=uuid4(),
            expected_revision=result.revision, answers={key: 'Corrected answer' for key in answers}))
        await AssessmentWorker(self.service).run_once()
        with self.db.sessions.begin() as session:
            grades = session.scalar(select(attempts.c.grades).where(attempts.c.id == str(attempt.id)))
            for grade in grades: grade['confidence'] = .4
            session.execute(update(attempts).where(attempts.c.id == str(attempt.id)).values(grades=grades))
        await AssessmentEvidenceWorker(self.service).run_once()
        result = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual((result.state, result.evidence_status), ('graded', 'unavailable'))
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_decision).where(evidence_decision.c.status == 'ACCEPTED')), 0)
