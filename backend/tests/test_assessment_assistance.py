import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from pydantic import ValidationError

from app.assessments.schemas import SubmitAnswers, StartAttempt, AssessmentAssistance
from app.assessments.repositories.list_view import summaries
from testing.assessment_workers import run_assessment_pipeline
from tests import test_assessments as fixtures


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires isolated PostgreSQL')
class AssistanceScoringTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.AssessmentTests.setUp

    async def grade(self, assistance):
        assessment = await self.service.generate(self.owner, self.request.model_copy(update={
            'client_request_id':uuid4(), 'question_format':'mcq', 'count':2}))
        attempt = self.service.repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
        answers = {str(question.id):question.options[0].id for question in assessment.questions}
        self.service.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(), answers=answers, assistance=assistance))
        await run_assessment_pipeline(self.service)
        return assessment, self.service.repository.attempt(self.owner, str(attempt.id))

    async def test_real_enum_and_assisted_score_leave_correctness_and_evidence_intact(self):
        assessment, attempt = await self.grade(AssessmentAssistance.assisted)
        raw = sum(question.marks for question in assessment.questions)
        self.assertEqual(attempt.reported_assistance, AssessmentAssistance.assisted)
        self.assertEqual(attempt.scoring.raw_score, raw)
        self.assertEqual(attempt.scoring.adjusted_score, round(raw*.9,4))
        self.assertEqual(attempt.scoring.multiplier, .9)
        self.assertTrue(all(grade.outcome == 'correct' for grade in attempt.grades))
        self.assertEqual(attempt.evidence_status, 'applied')
        summary = summaries(self.service.repository,self.owner)['items'][0]['attempt_summary']
        self.assertEqual(summary.correct,2); self.assertEqual(summary.incorrect,0)
        with self.db.sessions() as session:
            row = session.execute(text('SELECT pg_typeof(assistance)::text, pg_typeof(reported_assistance)::text FROM assessment_attempt WHERE id=:id'),dict(id=str(attempt.id))).one()
            self.assertTrue(all(value.endswith('assessment_assistance_kind') for value in row))
        with self.assertRaises(ValidationError):
            SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={},assistance='yes')

    async def test_independent_and_unknown_have_no_score_penalty(self):
        for assistance in (AssessmentAssistance.independent, AssessmentAssistance.unknown):
            _, attempt = await self.grade(assistance)
            self.assertEqual(attempt.scoring.multiplier,1)
            self.assertEqual(attempt.scoring.adjusted_score,attempt.scoring.raw_score)

    async def test_draft_assistance_round_trips_and_survives_answer_sheet_extraction(self):
        from io import BytesIO
        from app.assessments.schemas import SaveDraftAnswers
        assessment = await self.service.generate(self.owner,self.request.model_copy(update={
            'client_request_id':uuid4(),'question_format':'mcq','count':2}))
        attempt=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        body=SaveDraftAnswers(expected_revision=attempt.revision,answers={},assistance='assisted')
        saved=self.service.repository.save_draft_answers(self.owner,str(attempt.id),body)
        self.assertEqual(saved.reported_assistance,AssessmentAssistance.assisted)
        self.assertEqual(self.service.repository.save_draft_answers(self.owner,str(attempt.id),body).revision,saved.revision)
        asset=self.files.upload(self.owner,BytesIO(b'1. A\n2. A'),'answers.txt','assessment',str(uuid4()))
        reviewed=self.service.repository.store_extraction(self.owner,str(attempt.id),saved.revision,
            dict(answers={str(q.id):'A' for q in assessment.questions},warnings=[]),asset['id'],'answers.txt')
        self.assertEqual(reviewed.reported_assistance,AssessmentAssistance.assisted)

    async def test_corrections_keep_original_scores_and_do_not_compound_adjustment(self):
        _, attempt = await self.grade(AssessmentAssistance.assisted)
        original = attempt.scoring
        for assistance in (AssessmentAssistance.assisted, AssessmentAssistance.independent):
            body=SubmitAnswers(expected_revision=attempt.revision,client_request_id=uuid4(),answers=attempt.answers,assistance=assistance)
            pending=self.service.repository.correct(self.owner,str(attempt.id),body)
            self.assertIsNone(pending.scoring)
            await run_assessment_pipeline(self.service)
            attempt=self.service.repository.attempt(self.owner,str(attempt.id))
            self.assertEqual(attempt.scoring.multiplier,.9 if assistance == AssessmentAssistance.assisted else 1)
            self.assertEqual(attempt.scoring.raw_score,original.raw_score)
        self.assertEqual(attempt.grade_history[0]['scoring'],original.model_dump(mode='json'))

    async def test_repeated_practice_exposure_does_not_claim_self_reported_ai_use(self):
        from tests.test_product_followups import ProductFollowupTests
        from app.assessments.schemas import MistakePracticeRequest
        source, original = await ProductFollowupTests.graded(self)
        practice = self.service.repository.practise_mistakes(self.owner, str(original.id), MistakePracticeRequest(
            client_request_id=uuid4(), expected_grade_revision=original.grade_revision, question_ids=[source.questions[0].id]))
        attempt = self.service.repository.start(self.owner, str(practice.id), StartAttempt(client_request_id=uuid4()))
        answers={str(question.id):question.options[0].id for question in practice.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(),answers=answers,assistance='independent'))
        await run_assessment_pipeline(self.service)
        result=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(result.assistance,AssessmentAssistance.assisted)
        self.assertEqual(result.reported_assistance,AssessmentAssistance.independent)
        self.assertEqual(result.scoring.multiplier,1)

    async def test_enum_migration_preserves_legacy_grades_without_retroactive_penalty(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        _, attempt = await self.grade(AssessmentAssistance.assisted)
        path=Path(__file__).parents[1]/'alembic/versions/20261025_0031_assessment_assistance_scoring.py'
        spec=importlib.util.spec_from_file_location('assistance_migration',path)
        migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        with self.db.engine.begin() as connection:
            # Recreate an old, already-graded row before testing the additive upgrade.
            connection.execute(text('UPDATE assessment_attempt SET scoring=NULL'))
            before=connection.execute(text('SELECT grades FROM assessment_attempt WHERE id=:id'),dict(id=str(attempt.id))).scalar_one()
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                migration.upgrade()
            after=connection.execute(text('SELECT grades, reported_assistance, scoring FROM assessment_attempt WHERE id=:id'),dict(id=str(attempt.id))).one()
            self.assertEqual(after.grades,before)
            self.assertEqual(after.reported_assistance,'assisted')
            self.assertIsNone(after.scoring)
