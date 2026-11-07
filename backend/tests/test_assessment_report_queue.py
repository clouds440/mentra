import unittest
from uuid import uuid4
from sqlalchemy import select, func
from app.assessments.repositories.review_queue import pending_reports, reported_item, correct_report
from app.assessments.repositories.tables import item_reviews
from app.core.exceptions import AppError
from testing.assessment_workers import run_assessment_pipeline
from tests import test_assessment_quality as quality_fixture


class ReportQueueTests(unittest.IsolatedAsyncioTestCase):
    setUp = quality_fixture.QualityLifecycleTests.setUp
    prepared = quality_fixture.QualityLifecycleTests.prepared
    report = quality_fixture.QualityLifecycleTests.report

    def queue(self, **kwargs):
        return pending_reports(self.service.repository, self.owner, **kwargs)

    async def test_queue_is_owned_paged_key_free_and_coalesces_repeat_reports(self):
        paper, _ = await self.prepared()
        current = self.report(paper)
        current = self.service.repository.review_item(self.owner, str(paper.id), str(paper.questions[1].id),
            current.revision, str(uuid4()), 'ambiguous')
        self.service.repository.review_item(self.owner, str(paper.id), str(paper.questions[0].id),
            current.revision, str(uuid4()), 'wrong_answer')
        page = self.queue(limit=1)
        next_page = self.queue(limit=1, after=page['next_cursor'])
        self.assertEqual(len(page['items']), 1)
        self.assertEqual(len(next_page['items']), 1)
        self.assertIsNone(next_page['next_cursor'])
        self.assertNotEqual(page['items'][0]['question_id'], next_page['items'][0]['question_id'])
        self.assertNotIn('model_answer', str(page))
        self.assertNotIn('previous_question', str(page))
        self.assertEqual(pending_reports(self.service.repository, self.other)['items'], [])
        with self.assertRaises(AppError):
            reported_item(self.service.repository, self.other, page['items'][0]['id'])
        with self.assertRaises(ValueError):
            self.queue(limit=101)

    async def test_preview_apply_retry_regrades_saved_answers_and_resolves_queue(self):
        paper, attempt = await self.prepared()
        self.report(paper)
        identifier = self.queue()['items'][0]['id']
        report = reported_item(self.service.repository, self.owner, identifier)
        fixed = dict(report['correction_template'], correct_option_id='b',
            model_answer='The second explanation is correct.', rubric='Full credit only for b.')
        arguments = dict(expected_revision=report['expected_revision'], operation_id=str(uuid4()))
        preview = correct_report(self.service.repository, self.owner, identifier, fixed, **arguments)
        self.assertFalse(preview['applied'])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(item_reviews)), 1)
        with self.assertRaises(AppError):
            correct_report(self.service.repository, self.owner, identifier, dict(fixed, marks=5),
                **arguments, apply_digest=preview['digest'])
        result = correct_report(self.service.repository, self.owner, identifier, fixed,
            **arguments, apply_digest=preview['digest'])
        retry = correct_report(self.service.repository, self.owner, identifier, fixed,
            **arguments, apply_digest=preview['digest'])
        self.assertEqual(result, retry)
        self.assertEqual(self.queue()['items'], [])
        self.assertTrue(await run_assessment_pipeline(self.service))
        saved = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual(saved.answers, attempt.answers)
        self.assertEqual(saved.grade_revision, 2)
        self.assertEqual(saved.grades[0].score, 0)
        self.assertEqual(len(saved.grade_history), 1)

    async def test_stale_preview_cannot_override_another_item_revision(self):
        paper, _ = await self.prepared()
        current = self.report(paper)
        identifier = self.queue()['items'][0]['id']
        report = reported_item(self.service.repository, self.owner, identifier)
        arguments = dict(expected_revision=current.revision, operation_id=str(uuid4()))
        preview = correct_report(self.service.repository, self.owner, identifier, report['correction_template'], **arguments)
        self.service.repository.review_item(self.owner, str(paper.id), str(paper.questions[1].id),
            current.revision, str(uuid4()), 'ambiguous')
        with self.assertRaises(AppError) as caught:
            correct_report(self.service.repository, self.owner, identifier, report['correction_template'],
                **arguments, apply_digest=preview['digest'])
        self.assertEqual(caught.exception.code, 'REVISION_CONFLICT')
        self.assertEqual(len(self.queue()['items']), 2)

    async def test_correction_cannot_change_owned_skill_identity(self):
        paper, _ = await self.prepared()
        self.report(paper)
        identifier = self.queue()['items'][0]['id']
        report = reported_item(self.service.repository, self.owner, identifier)
        with self.assertRaises(AppError):
            correct_report(self.service.repository, self.owner, identifier,
                dict(report['correction_template'], concept_ids=['invented-skill']),
                expected_revision=report['expected_revision'], operation_id=str(uuid4()))
        self.assertTrue(reported_item(self.service.repository, self.owner, identifier)['pending'])

    async def test_new_reasons_and_report_explanation_survive_api_validation_and_storage(self):
        from app.api.routes.assessments import ItemReport
        from pydantic import ValidationError
        paper, _ = await self.prepared()
        for reason in ['off_request', 'unhelpful', 'difficulty_mismatch', 'missing_information']:
            operation = str(uuid4())
            body = ItemReport(expected_revision=paper.revision, client_request_id=operation,
                reason=reason, details='طلبت تطبيقات على التسارع، وليس حفظ تعريفات.')
            paper = self.service.repository.review_item(self.owner, str(paper.id), str(paper.questions[0].id),
                body.expected_revision, operation, body.reason, details=body.details)
            private = reported_item(self.service.repository, self.owner, operation)
            self.assertEqual(private['details'], body.details)
            self.assertEqual(private['reason'], reason)
            self.assertNotIn(body.details, paper.model_dump_json())
            with self.assertRaises(AppError):
                self.service.repository.review_item(self.owner, str(paper.id), str(paper.questions[0].id),
                    body.expected_revision, operation, body.reason, details='Changed after submission')
        with self.assertRaises(ValidationError):
            ItemReport(expected_revision=paper.revision, client_request_id=uuid4(), reason='unhelpful', details='x'*2001)

    async def test_schema_rollback_cannot_discard_a_students_report_explanation(self):
        from app.db.migrate import downgrade, upgrade
        paper, _ = await self.prepared()
        downgrade(self.db.engine, '20261106_0048')
        upgrade(self.db.engine)
        operation = str(uuid4())
        self.service.repository.review_item(self.owner, str(paper.id), str(paper.questions[0].id),
            paper.revision, operation, 'off_request', details='I requested multi-step questions.')
        with self.assertRaisesRegex(RuntimeError, 'Export report explanations'):
            downgrade(self.db.engine, '20261106_0048')
        self.assertEqual(reported_item(self.service.repository, self.owner, operation)['details'],
            'I requested multi-step questions.')
