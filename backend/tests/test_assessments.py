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
