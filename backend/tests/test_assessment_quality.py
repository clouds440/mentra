import unittest
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select,func
from app.assessments.quality import check_question,executable_choice_check
from app.assessments.schemas import GeneratedQuestion,GenerationRequest,StartAttempt,SubmitAnswers,MistakePracticeRequest
from app.assessments.repositories.tables import item_reviews,assessments,attempts
from app.assessments.repositories.evidence import AssessmentEvidenceJobs
from app.assessments.evidence_worker import AssessmentEvidenceWorker
from app.assessments.worker import AssessmentWorker
from app.langchain.generation_recovery import GenerationMismatch
from app.core.exceptions import AppError
from app.learner.repositories.tables import learning_evidence,evidence_decision
from testing.assessment_workers import run_assessment_pipeline
from tests import test_assessment_flexibility as fixtures


class QualityChecks(unittest.TestCase):
    def test_real_before_sample_with_two_dots_below_ba_is_rejected(self):
        options=[dict(id='ba',label='ب'),dict(id='ta',label='ت'),dict(id='tha',label='ث')]
        question=self.item(prompt='أي حرف من الحروف التالية له **نقطتان** تحته؟',options=options,
            correct_option_id='ba',model_answer='الباء لها نقطتان تحتها.')
        with self.assertRaisesRegex(GenerationMismatch,'arabic_letter_dot_key_mismatch'):check_question(question)
        correct=question.model_copy(update=dict(prompt='أي حرف له نقطة واحدة تحته؟',model_answer='الباء لها نقطة واحدة تحتها.'))
        self.assertIn('arabic_letter_dot_key',check_question(correct)['checks'])
        geometry=correct.model_copy(update=dict(prompt='أي نقطة تقع أعلى النقطة أ؟'))
        self.assertNotIn('arabic_letter_dot_key',check_question(geometry)['checks'])

    def item(self,**updates):
        return GeneratedQuestion(**dict(dict(prompt='Find `result`.\n```python\na = [1, 2]\nb = [3]\nresult = a + b\n```',
            concept_ids=['known'],marks=1,difficulty=.2,options=[dict(id='a',label='`[1, 2, 3]`'),dict(id='b',label='`[4, 5]`')],
            correct_option_id='a',model_answer='Concatenation joins the two lists.',rubric='Full credit for the correct option.'),**updates))

    def test_python_concat_key_is_checked_without_executing_model_code(self):
        self.assertTrue(executable_choice_check(self.item()))
        with self.assertRaisesRegex(GenerationMismatch,'executable_choice_key_mismatch'):
            executable_choice_check(self.item(correct_option_id='b'))

    def test_saved_array_concatenation_error_has_a_trusted_runtime_regression(self):
        from array import array
        self.assertEqual((array('i',[1,2])+array('i',[3])).tolist(),[1,2,3])
        question=self.item(prompt='Find `result`.\n```python\nfrom array import array\na = array("i", [1, 2])\nb = array("i", [3])\nresult = a + b\n```',
            options=[dict(id='a',label='`array("i", [1, 2, 3])`'),dict(id='b',label='`array("i", [4, 5])`')])
        self.assertTrue(executable_choice_check(question))

    def test_checker_abstains_on_side_effects_ambiguous_target_or_large_operations(self):
        for code in ['import os\nresult = os.remove("private")', 'result = [1]*1000000000',
                'result = open("private").read()', 'result = [x for x in range(1000000)]']:
            self.assertFalse(executable_choice_check(self.item(prompt=f'Find `result`.\n```python\n{code}\n```')))
        self.assertFalse(executable_choice_check(self.item(prompt='Find `a`.\n```python\na = [1, 2]\nresult = [3]\n```')))

    def test_duplicate_labels_and_full_answer_leaks_are_rejected_multilingually(self):
        with self.assertRaisesRegex(GenerationMismatch,'duplicate_option_labels'):
            check_question(self.item(options=[dict(id='a',label='Choice'),dict(id='b',label=' choice ')]))
        answer='هذا هو الحل الكامل الذي لا ينبغي إظهاره قبل الإجابة.'
        with self.assertRaisesRegex(GenerationMismatch,'answer_leaked'):
            check_question(self.item(model_answer=answer,context=answer))
        self.assertEqual(check_question(self.item())['semantic_review'],'unverified')


class QualityLifecycleTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.FlexibleEngineTests.setUp

    async def test_exact_repeated_new_quiz_does_not_manufacture_independent_mastery(self):
        from app.learner.repositories.tables import learner_concept_state
        first,_=await self.prepared()
        def state():
            with self.db.sessions() as session:return dict(session.execute(select(learner_concept_state).where(
                learner_concept_state.c.learner_id==self.owner,learner_concept_state.c.concept_id==first.questions[0].concept_ids[0])).mappings().one())
        before=state();second,attempt=await self.prepared()
        self.assertNotEqual(first.id,second.id);self.assertEqual(attempt.state,'graded')
        after=state()
        self.assertEqual(before['policy_data_json']['independent_items'],after['policy_data_json']['independent_items'])
        with self.db.sessions() as session:
            rows=list(session.execute(select(learning_evidence).where(learning_evidence.c.learner_id==self.owner)).mappings())
        self.assertEqual(len(rows),4)
        copies=[row for row in rows if row['metadata_json'].get('assessment_id')==str(second.id)]
        self.assertTrue(all(row['independence']==0 and row['metadata_json']['known_item_exposure'] for row in copies))

    async def prepared(self,*,apply=True,answer='a'):
        value=await self.service.generate(self.owner,GenerationRequest(client_request_id=uuid4(),
            context_id=self.context.context_id,topic='Reasoning',concept_names=['Evidence'],count=2,question_format='mcq'))
        attempt=self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(),answers={str(q.id):answer for q in value.questions},assistance='independent'))
        await AssessmentWorker(self.service).run_once()
        if apply: await AssessmentEvidenceWorker(self.service).run_once()
        return value,self.service.repository.attempt(self.owner,str(attempt.id))

    def report(self,value,**kwargs):
        return self.service.repository.review_item(self.owner,str(value.id),str(value.questions[0].id),
            value.revision,str(uuid4()),'wrong_answer',**kwargs)

    async def test_invalidation_withdraws_only_affected_evidence_preserves_answers_and_is_private(self):
        value,attempt=await self.prepared()
        operation=str(uuid4())
        result=self.service.repository.review_item(self.owner,str(value.id),str(value.questions[0].id),
            value.revision,operation,'wrong_answer')
        self.assertEqual(result.questions[0].validation['state'],'invalidated')
        self.assertNotIn('previous_question',result.model_dump_json())
        self.assertNotIn('correct_option_id',result.model_dump_json())
        saved=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(saved.answers,attempt.answers)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),2)
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_decision).where(evidence_decision.c.status=='ACCEPTED')),1)
        self.service.repository.review_item(self.owner,str(value.id),str(value.questions[0].id),value.revision,operation,'wrong_answer')
        with self.assertRaises(AppError): self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        with self.assertRaises(AppError): self.service.repository.review_item(self.other,str(value.id),str(value.questions[0].id),value.revision,str(uuid4()),'wrong_answer')

    async def test_inflight_evidence_job_rechecks_item_admission(self):
        value,attempt=await self.prepared(apply=False)
        jobs=AssessmentEvidenceJobs(self.service.repository)
        job=jobs.claim()
        self.report(value)
        from app.assessments.schemas import GradedAssessment,QuestionGrade
        grades=GradedAssessment(questions=[QuestionGrade.model_validate({key:v for key,v in item.items() if key in QuestionGrade.model_fields}) for item in job['attempt']['grades']])
        jobs.complete(job,lambda tx:self.service.workflows.evidence(job,grades,tx))
        with self.db.sessions() as session:
            ids=list(session.scalars(select(learning_evidence.c.metadata_json)))
        self.assertTrue(all(item['question_id']!=str(value.questions[0].id) for item in ids))

    async def test_trusted_key_correction_regrades_once_with_original_key_history(self):
        value,attempt=await self.prepared()
        invalid=self.report(value)
        private=self.service.repository.revision_source(self.owner,str(value.id))['questions'][0]
        fixed={key:v for key,v in private.items() if key in GeneratedQuestion.model_fields}
        fixed.update(correct_option_id='b',model_answer='The second explanation is correct.',rubric='Full credit only for b.')
        self.service.repository.review_item(self.owner,str(value.id),str(value.questions[0].id),invalid.revision,
            str(uuid4()),'trusted_correction',correction=fixed)
        self.assertTrue(await run_assessment_pipeline(self.service))
        saved=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(saved.grade_revision,2)
        self.assertEqual(saved.grades[0].score,0)
        self.assertEqual(saved.answers,attempt.answers)
        self.assertEqual(len(saved.grade_history),1)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(item_reviews)),2)
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_decision).where(evidence_decision.c.status=='ACCEPTED')),2)
        self.assertFalse(await AssessmentEvidenceWorker(self.service).run_once())

    async def test_withdrawal_failure_rolls_back_review_and_evidence(self):
        value,_=await self.prepared()
        with patch.object(self.service.repository,'withdraw_item_evidence',side_effect=RuntimeError('rollback')):
            with self.assertRaises(RuntimeError): self.report(value)
        self.assertEqual(self.service.repository.detail(self.owner,str(value.id)).revision,value.revision)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(item_reviews)),0)
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_decision).where(evidence_decision.c.status=='ACCEPTED')),2)

    async def test_copied_mistake_item_is_quarantined_and_cannot_continue_scoring(self):
        value,attempt=await self.prepared(answer='b')
        clone=self.service.repository.practise_mistakes(self.owner,str(attempt.id),MistakePracticeRequest(
            client_request_id=uuid4(),expected_grade_revision=attempt.grade_revision,question_ids=[value.questions[0].id]))
        cloned_attempt=self.service.repository.start(self.owner,str(clone.id),StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner,str(cloned_attempt.id),SubmitAnswers(client_request_id=uuid4(),
            expected_revision=cloned_attempt.revision,answers={str(clone.questions[0].id):'b'}))
        await run_assessment_pipeline(self.service)
        self.report(value)
        refreshed=self.service.repository.detail(self.owner,str(clone.id))
        self.assertEqual(refreshed.questions[0].validation['state'],'invalidated')
        with self.assertRaises(AppError): self.service.repository.start(self.owner,str(clone.id),StartAttempt(client_request_id=uuid4()))
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_decision).where(evidence_decision.c.status=='ACCEPTED')),1)

    async def test_invalidation_fences_a_grading_worker_that_already_generated_results(self):
        value=await self.service.generate(self.owner,GenerationRequest(client_request_id=uuid4(),context_id=self.context.context_id,
            topic='Reasoning',concept_names=['Evidence'],count=1,question_format='mcq'))
        attempt=self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(client_request_id=uuid4(),expected_revision=attempt.revision,
            answers={str(value.questions[0].id):'a'}))
        job=self.service.repository.claim()
        grades=await self.service.workflows.grade(job)
        self.report(value)
        with self.assertRaises(AppError): self.service.repository.complete(job,grades)

    async def test_report_api_is_owned_private_and_does_not_accept_key_corrections(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.assessments import router
        from app.student_profile.dependencies import require_onboarded_identity
        from app.core.exception_handlers import register_exception_handlers
        value,_=await self.prepared()
        app=FastAPI();app.state.assessment_service=self.service
        current=[self.other]
        app.dependency_overrides[require_onboarded_identity]=lambda:SimpleNamespace(learner_id=current[0])
        register_exception_handlers(app);app.include_router(router)
        client=TestClient(app)
        path=f'/assessments/{value.id}/items/{value.questions[0].id}/report'
        body=dict(expected_revision=value.revision,client_request_id=str(uuid4()),reason='wrong_answer')
        self.assertEqual(client.post(path,json=body).status_code,404)
        current[0]=self.owner
        self.assertEqual(client.post(path,json=dict(body,correct_option_id='b')).status_code,422)
        response=client.post(path,json=body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['questions'][0]['validation']['state'],'invalidated')
        self.assertNotIn('correct_option_id',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
