import os
import unittest
from io import BytesIO
from uuid import uuid4
from sqlalchemy import select, func
from app.assessments.service import create_assessments
from app.assessments.worker import AssessmentWorker
from app.assessments.schemas import GenerationRequest, StartAttempt, SubmitAnswers
from app.langchain.llm import MentraLLM
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.learner.repositories.tables.evidence import learning_evidence
from app.core.exceptions import AppError
from testing.history_model import HistoryChatFactory
from testing.postgres import PostgresSandbox
from testing.identities import learner_id

@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated database')
class AssessmentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db=PostgresSandbox(); self.addCleanup(self.db.close)
        self.owner,self.other=learner_id('alice'),learner_id('bob')
        self.learner=LearnerEngine(self.db.repository)
        context=self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner,name='Algebra'))
        self.service=create_assessments(self.db.sessions,MentraLLM(HistoryChatFactory()),self.learner)
        self.request=GenerationRequest(client_request_id=uuid4(),context_id=context.context_id,topic='Equations',concept_names=['Linear equations'],confirm_new_concepts=True,count=2)

    async def prepared(self):
        assessment=await self.service.generate(self.owner,self.request)
        attempt=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        return assessment,attempt

    async def test_generation_hides_keys_and_replays_without_duplicates(self):
        assessment=await self.service.generate(self.owner,self.request)
        replay=await self.service.generate(self.owner,self.request)
        self.assertEqual(assessment.id,replay.id)
        self.assertNotIn('model_answer',assessment.model_dump_json())
        self.assertNotIn('rubric',assessment.model_dump_json())
        with self.assertRaises(AppError): self.service.repository.detail(self.other,str(assessment.id))

    async def test_existing_canonical_concept_is_linked_for_a_new_student(self):
        await self.service.generate(self.owner,self.request)
        context=self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.other,name='Algebra'))
        request=self.request.model_copy(update={'context_id':context.context_id,'client_request_id':uuid4(),'confirm_new_concepts':False})
        await self.service.generate(self.other,request)
        targets=self.learner.get_study_targets(self.other,[context.context_id])
        self.assertTrue(targets['recommendations'])

    async def test_complete_answers_grading_and_atomic_learner_evidence(self):
        assessment,attempt=await self.prepared()
        with self.assertRaises(AppError):
            self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={}))
        answers={str(question.id):'A partial answer.' for question in assessment.questions}
        body=SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers=answers)
        self.service.submit(self.owner,str(attempt.id),body)
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        result=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(result.state,'graded'); self.assertEqual(result.evidence_status,'applied')
        self.assertEqual(self.service.submit(self.owner,str(attempt.id),body).state,'graded')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),2)

    async def test_rollback_keeps_grades_and_mastery_uncommitted(self):
        assessment,attempt=await self.prepared()
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={str(q.id):'Answer' for q in assessment.questions}))
        job=self.service.repository.claim(); grades=await self.service.workflows.grade(job)
        def fail(tx):
            self.service.workflows.evidence(job,grades,tx)
            raise RuntimeError('crash before domain commit')
        with self.assertRaises(RuntimeError): self.service.repository.complete(job,grades,fail)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),0)
        self.service.repository.complete(job,grades,lambda tx:self.service.workflows.evidence(job,grades,tx))
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'graded')

    async def test_paper_requires_complete_confirmed_transcription(self):
        assessment,attempt=await self.prepared()
        from app.documents.schemas import DocumentContent
        class Reader:
            def read(self,*args,**kwargs): return DocumentContent(format='text',media_type='text/plain',blocks=[{'text':'1. First answer\n2. Second answer','page':1,'method':'OCR'}],warnings=['OCR confidence is unknown'],reader_revision='test-ocr')
        self.service.reader=Reader()
        extracted=self.service.upload_paper(self.owner,str(attempt.id),1,BytesIO(b'answers'),'answers.txt')
        self.assertEqual(extracted.state,'pending_transcription')
        self.assertIsNone(extracted.extraction['extraction_confidence'])
        self.assertFalse(await AssessmentWorker(self.service).run_once())
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=2,client_request_id=uuid4(),answers=extracted.extraction['answers'],transcription_confirmed=True))
        await AssessmentWorker(self.service).run_once()
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).evidence_status,'applied')

    async def test_delete_and_unknown_concept_requirements(self):
        self.request=self.request.model_copy(update={'confirm_new_concepts':False})
        with self.assertRaises(AppError): await self.service.generate(self.owner,self.request)
        self.request=self.request.model_copy(update={'confirm_new_concepts':True})
        assessment,attempt=await self.prepared()
        self.service.repository.remove(self.owner,str(assessment.id))
        with self.assertRaises(AppError): self.service.repository.attempt(self.owner,str(attempt.id))

    async def test_correction_preserves_history_and_supersedes_question_evidence(self):
        assessment,attempt=await self.prepared()
        answers={str(question.id):'Original answer' for question in assessment.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers=answers))
        await AssessmentWorker(self.service).run_once()
        graded=self.service.repository.attempt(self.owner,str(attempt.id))
        corrected=self.service.repository.correct(self.owner,str(attempt.id),SubmitAnswers(expected_revision=graded.revision,client_request_id=uuid4(),answers={key:'Corrected answer' for key in answers}))
        self.assertEqual(corrected.grade_revision,2)
        await AssessmentWorker(self.service).run_once()
        final=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(final.state,'graded');self.assertEqual(len(final.grade_history),1)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),4)

    async def test_uncertain_correction_withdraws_previous_evidence_atomically(self):
        from app.learner.repositories.tables.evidence import evidence_decision
        assessment, attempt = await self.prepared()
        answers = {str(question.id):'Original answer' for question in assessment.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers=answers))
        await AssessmentWorker(self.service).run_once()
        graded = self.service.repository.attempt(self.owner,str(attempt.id))
        self.service.repository.correct(self.owner,str(attempt.id),SubmitAnswers(expected_revision=graded.revision,client_request_id=uuid4(),answers={key:'Corrected' for key in answers}))
        job = self.service.repository.claim()
        grades = await self.service.workflows.grade(job)
        uncertain = grades.model_copy(update={'questions':[question.model_copy(update={'confidence':.5}) for question in grades.questions]})
        def rollback(tx):
            self.service.workflows.evidence(job,uncertain,tx)
            raise RuntimeError('rollback withdrawal')
        with self.assertRaises(RuntimeError): self.service.repository.complete(job,uncertain,rollback)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_decision).where(evidence_decision.c.status=='ACCEPTED')),2)
        self.service.repository.complete(job,uncertain,lambda tx:self.service.workflows.evidence(job,uncertain,tx))
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence_decision).where(evidence_decision.c.status=='ACCEPTED')),0)
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),2)
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).evidence_status,'unavailable')

    async def test_partial_confidence_preserves_reliable_question_evidence(self):
        assessment, attempt = await self.prepared()
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={str(q.id):'Answer' for q in assessment.questions}))
        job = self.service.repository.claim()
        grades = await self.service.workflows.grade(job)
        grades.questions[0].confidence = .5
        self.service.repository.complete(job,grades,lambda tx:self.service.workflows.evidence(job,grades,tx))
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).evidence_status,'partial')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),1)

    async def test_generation_claim_and_grounding_fail_closed(self):
        claim = self.service.repository.claim_generation(self.owner,self.request)
        with self.assertRaises(AppError) as raised: await self.service.generate(self.owner,self.request)
        self.assertEqual(raised.exception.code,'ASSESSMENT_GENERATING')
        self.service.repository.release_generation(self.owner,self.request.client_request_id,claim)
        with self.assertRaises(AppError):
            await self.service.generate(self.owner,self.request.model_copy(update={'grounded':True}))
        # A failed generation releases its claim, so a legitimate retry works.
        result = await self.service.generate(self.owner,self.request)
        self.assertEqual(len(result.questions),2)

    async def test_large_valid_answers_are_graded_without_single_huge_call(self):
        request = self.request.model_copy(update={'count':10})
        assessment = await self.service.generate(self.owner,request)
        attempt = self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={str(q.id):'Answer. '*1000 for q in assessment.questions}))
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        graded = self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(graded.state,'graded')
        self.assertEqual(len(graded.grades),10)

    async def test_profile_projection_replays_without_double_counting_and_retracts(self):
        from app.student_profile.service import StudentProfileService
        from app.student_profile.repositories.postgres import PostgresStudentProfileRepository
        from app.student_profile.schemas import ProfileUpdate
        from testing.profile_evaluator import TestProfileEvaluator
        from tests.student_profile.test_profile import details
        profile = StudentProfileService(PostgresStudentProfileRepository(self.db.sessions),TestProfileEvaluator())
        profile.update_details(self.owner,ProfileUpdate(expected_version=profile.get(self.owner).version,details=details()))
        assessment = await self.service.generate(self.owner,self.request.model_copy(update={'count':6}))
        attempt = self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        answers = {str(question.id):'Original answer' for question in assessment.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers=answers))
        await AssessmentWorker(self.service).run_once()
        updated = profile.get(self.owner)
        self.assertEqual(updated.estimates.domain_familiarity.evidence_count,6)
        self.assertIsNotNone(updated.estimates.domain_familiarity.value)
        self.assertIsNone(updated.estimates.reasoning.value)
        from app.langchain.profile_bridge import project_learning_profile
        with self.service.repository.transactions.write(self.owner) as tx: project_learning_profile(tx,self.owner)
        self.assertEqual(profile.get(self.owner).estimates,updated.estimates)
        graded = self.service.repository.attempt(self.owner,str(attempt.id))
        self.service.repository.correct(self.owner,str(attempt.id),SubmitAnswers(expected_revision=graded.revision,client_request_id=uuid4(),answers={key:'Corrected answer' for key in answers}))
        job = self.service.repository.claim(); grades = await self.service.workflows.grade(job)
        for question in grades.questions: question.confidence=.5
        self.service.repository.complete(job,grades,lambda tx:self.service.workflows.evidence(job,grades,tx))
        final = profile.get(self.owner)
        self.assertEqual(final.details,updated.details)
        self.assertEqual(final.estimates.domain_familiarity.evidence_count,0)
        self.assertIsNone(final.estimates.domain_familiarity.value)

    async def test_multi_concept_question_uses_overall_grade_for_profile_once(self):
        from app.student_profile.service import StudentProfileService
        from app.student_profile.repositories.postgres import PostgresStudentProfileRepository
        from app.student_profile.schemas import ProfileUpdate
        from app.learner.schemas import ConceptResolutionRequest
        from testing.profile_evaluator import TestProfileEvaluator
        from tests.student_profile.test_profile import details
        profile = StudentProfileService(PostgresStudentProfileRepository(self.db.sessions),TestProfileEvaluator())
        profile.update_details(self.owner,ProfileUpdate(expected_version=profile.get(self.owner).version,details=details()))
        request = self.request.model_copy(update={'count':1,'concept_names':['Linear equations','Factoring']})
        generated,sources = await self.service.workflows.generate(self.owner,request)
        second = self.learner.resolve_concept(ConceptResolutionRequest(label='Factoring',learner_id=self.owner,context_id=request.context_id))
        generated.questions[0].concept_ids.append(second.concept_id)
        assessment = self.service.repository.save(self.owner,request,generated,sources)
        attempt = self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={str(assessment.questions[0].id):'Partially correct'}))
        job = self.service.repository.claim(); grades = await self.service.workflows.grade(job)
        values = list(grades.questions[0].concept_grades.values())
        values[0].score=0; values[1].score=values[1].max_score
        self.service.repository.complete(job,grades,lambda tx:self.service.workflows.evidence(job,grades,tx))
        estimate = profile.get(self.owner).estimates.domain_familiarity
        self.assertEqual(estimate.evidence_count,1)
        self.assertEqual(estimate.successful_weight,0)

    async def test_generation_hash_preserves_pre_revision_request_replays(self):
        from app.history_management.repositories.events.postgres import request_hash
        payload = self.request.model_dump(mode='json',exclude={'revision_draft_id','revision_assessment_id','revision_instructions'})
        self.assertEqual(request_hash(payload),request_hash(self.request.fingerprint_payload()))
        assessment = await self.service.generate(self.owner,self.request)
        self.assertEqual((await self.service.generate(self.owner,self.request)).id,assessment.id)

    async def test_misconceptions_follow_accepted_grading_evidence(self):
        assessment, attempt = await self.prepared()
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={str(q.id):'Answer' for q in assessment.questions}))
        job=self.service.repository.claim(); grades=await self.service.workflows.grade(job)
        grades.questions[0].misconceptions=['Confuses addition and multiplication']
        self.service.repository.complete(job,grades,lambda tx:self.service.workflows.evidence(job,grades,tx))
        concept=assessment.questions[0].concept_ids[0]
        found=self.db.repository.misconceptions_for_concepts(self.owner,[concept])
        self.assertIn('Confuses addition and multiplication',found[concept])
        self.assertFalse(self.db.repository.misconceptions_for_concepts(self.other,[concept]))

    async def test_owned_candidate_review_is_fenced_and_idempotent(self):
        with self.assertRaises(AppError):
            await self.service.generate(self.owner,self.request.model_copy(update={'confirm_new_concepts':False}))
        candidates=self.learner.get_pending_concepts(self.owner)
        self.assertEqual(len(candidates),1)
        self.assertFalse(self.learner.get_pending_concepts(self.other))
        with self.assertRaises(AppError): self.learner.review_owned_candidate(self.other,candidates[0]['id'])
        concept=self.learner.review_owned_candidate(self.owner,candidates[0]['id'])
        self.assertEqual(self.learner.review_owned_candidate(self.owner,candidates[0]['id']).id,concept.id)
        self.assertFalse(self.learner.get_pending_concepts(self.owner))

    async def test_blob_is_excluded_from_routine_attempt_reads(self):
        assessment,attempt=await self.prepared()
        from app.assessments.repositories.tables import attempts
        from sqlalchemy import update
        with self.db.sessions.begin() as session:
            session.execute(update(attempts).where(attempts.c.id==str(attempt.id)).values(source=b'x'*1024))
        with self.db.sessions() as session:
            internal=self.service.repository._attempt(session,self.owner,str(attempt.id))
            self.assertNotIn('source',internal)
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).id,attempt.id)
