import os
import unittest
from io import BytesIO
from uuid import uuid4
from sqlalchemy import select, func
from app.assessments.service import create_assessments
from testing.assessment_workers import run_assessment_pipeline
from app.assessments.schemas import GenerationRequest, StartAttempt, SubmitAnswers
from app.langchain.llm import MentraLLM
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.learner.repositories.tables.evidence import learning_evidence
from app.core.exceptions import AppError
from testing.history_model import HistoryChatFactory
from testing.postgres import PostgresSandbox
from testing.files import create_test_files
from testing.identities import learner_id

@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated database')
class AssessmentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db=PostgresSandbox(); self.addCleanup(self.db.close)
        self.owner,self.other=learner_id('alice'),learner_id('bob')
        self.learner=LearnerEngine(self.db.repository)
        context=self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner,name='Algebra'))
        self.files=create_test_files(self.db.sessions)
        self.service=create_assessments(self.db.sessions,MentraLLM(HistoryChatFactory()),self.learner,files=self.files)
        self.request=GenerationRequest(client_request_id=uuid4(),context_id=context.context_id,topic='Equations',concept_names=['Linear equations'],confirm_new_concepts=True,count=2)

    async def prepared(self):
        assessment=await self.service.generate(self.owner,self.request)
        attempt=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        return assessment,attempt

    async def test_replacing_draft_source_releases_only_superseded_binding(self):
        from app.files.tables import bindings
        from unittest.mock import patch
        assessment, attempt = await self.prepared()
        def stage(key):
            return self.files.upload(self.owner,BytesIO(key.encode()),'answers.txt','assessment',key)
        def store(current, file):
            return self.service.repository.store_extraction(self.owner,str(current.id),current.revision,
                dict(answers={},warnings=[]),file['id'],'answers.txt')
        first,second,third=stage('first'),stage('second'),stage('third')
        attempt=store(attempt,first)
        # Negative control recreates the audited missing-release behavior.
        with patch.object(self.files,'release'):
            attempt=store(attempt,second)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(bindings).where(bindings.c.released_at.is_(None))),2)
        attempt=store(attempt,third)
        with self.db.sessions() as session:
            active=list(session.scalars(select(bindings.c.file_id).where(bindings.c.released_at.is_(None))))
        self.assertEqual(active,[third['id']])
        self.files.cleanup()
        self.assertEqual(self.files.read(self.owner,third['id']),b'third')
        self.assertEqual(len(self.files.provider.objects),1)

    async def test_source_job_survives_client_and_replays_completed_result(self):
        from app.assessments.repositories.source_jobs import SourceJobs
        from app.assessments.source_worker import SourceWorker
        from unittest.mock import patch
        assessment, attempt=await self.prepared()
        stored=self.files.upload(self.owner,BytesIO(b'1. my answer'),'answers.txt','assessment','durable-source')
        jobs=SourceJobs(self.service.repository)
        queued=jobs.enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)
        self.assertEqual(jobs.enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)['id'],queued['id'])
        with self.assertRaises(AppError): jobs.get(self.other,queued['id'])
        with patch.object(self.service,'_extract_paper',return_value=dict(answers={},warnings=[])) as extract:
            self.assertTrue(await SourceWorker(self.service).run_once())
            self.assertFalse(await SourceWorker(self.service).run_once())
        self.assertEqual(extract.call_count,1)
        completed=jobs.get(self.owner,queued['id'])
        self.assertEqual(completed['state'],'completed')
        self.assertEqual(completed['attempt']['state'],'pending_transcription')
        self.assertEqual(jobs.enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)['state'],'completed')

    async def test_pending_source_survives_staged_expiry_and_cleanup(self):
        from app.assessments.repositories.source_jobs import SourceJobs
        from app.assessments.source_worker import SourceWorker
        from app.files.tables import assets
        from sqlalchemy import update
        from datetime import datetime,timezone,timedelta
        from unittest.mock import patch
        _,attempt=await self.prepared()
        stored=self.files.upload(self.owner,BytesIO(b'1. retained'),'answers.txt','assessment','pending-source')
        jobs=SourceJobs(self.service.repository)
        queued=jobs.enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)
        with self.db.sessions.begin() as session:
            session.execute(update(assets).where(assets.c.id==stored['id']).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
        self.files.cleanup()
        self.assertEqual(self.files.read(self.owner,stored['id']),b'1. retained')
        with patch.object(self.service,'_extract_paper',return_value=dict(answers={},warnings=[])):
            self.assertTrue(await SourceWorker(self.service).run_once())
        self.assertEqual(jobs.get(self.owner,queued['id'])['state'],'completed')

    async def test_source_job_reclaim_fences_stale_publication(self):
        from app.assessments.repositories.source_jobs import SourceJobs
        from app.assessments.repositories.tables import source_jobs
        from sqlalchemy import update
        from datetime import timedelta
        assessment, attempt=await self.prepared()
        stored=self.files.upload(self.owner,BytesIO(b'answer'),'answers.txt','assessment','reclaim-source')
        jobs=SourceJobs(self.service.repository)
        queued=jobs.enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)
        stale=jobs.claim()
        with self.db.sessions.begin() as session:
            session.execute(update(source_jobs).where(source_jobs.c.id==queued['id'])
                .values(claim_until=self.service.repository.clock()-timedelta(seconds=1)))
        current=jobs.claim()
        with self.assertRaises(AppError) as error:
            self.service.repository.store_extraction(self.owner,str(attempt.id),attempt.revision,
                dict(answers={},warnings=[]),stored['id'],'answers.txt',source_job=stale)
        self.assertEqual(error.exception.code,'ASSESSMENT_SOURCE_EXPIRED')
        jobs.finish(stale)
        self.assertTrue(jobs.active(current))
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'draft')

    async def test_background_budget_reserves_interactive_room(self):
        from app.db.admission import Admission, background_capacity, leases
        from app.core.config import Settings
        gate=Admission(self.db.sessions,settings=Settings(_env_file=None,work_global_capacity=2))
        async with background_capacity(gate,self.owner):
            with self.assertRaises(AppError):
                async with background_capacity(gate,self.other): self.fail('Background work exceeded budget')
            token=gate.acquire('model',self.other,capacity=2,owner_capacity=2)
            gate.release(token)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(leases)),0)

    async def test_queue_diagnostics_detect_missing_worker_and_clear_after_observation(self):
        from app.db.worker_status import queue_status, Heartbeat
        from app.assessments.repositories.source_jobs import SourceJobs
        from app.assessments.repositories.tables import source_jobs
        from sqlalchemy import update
        from datetime import timedelta
        assessment,attempt=await self.prepared()
        stored=self.files.upload(self.owner,BytesIO(b'answer'),'answers.txt','assessment','health-source')
        jobs=SourceJobs(self.service.repository)
        queued=jobs.enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)
        with self.db.sessions.begin() as session:
            session.execute(update(source_jobs).where(source_jobs.c.id==queued['id'])
                .values(created_at=self.service.repository.clock()-timedelta(minutes=5)))
        first=queue_status(self.db.sessions)
        row=next(row for row in first['queues'] if row['role']=='assessment.source')
        self.assertEqual(row['status'],'stalled')
        Heartbeat(self.db.sessions).pulse('assessment.source')
        second=queue_status(self.db.sessions)
        self.assertEqual(next(row for row in second['queues'] if row['role']=='assessment.source')['status'],'observed')

    async def test_busy_parse_capacity_defers_source_without_spending_attempt(self):
        from app.assessments.repositories.source_jobs import SourceJobs
        from app.assessments.repositories.tables import source_jobs
        from app.assessments.source_worker import SourceWorker
        from unittest.mock import AsyncMock,patch
        assessment,attempt=await self.prepared()
        stored=self.files.upload(self.owner,BytesIO(b'answer'),'answers.txt','assessment','capacity-source')
        jobs=SourceJobs(self.service.repository)
        queued=jobs.enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)
        async with self.service.admission.async_reserve('parse',self.owner,capacity=4,owner_capacity=1):
            with patch.object(self.service,'upload_paper_with_vision',new=AsyncMock()) as infer:
                self.assertTrue(await SourceWorker(self.service).run_once())
                infer.assert_not_called()
        with self.db.sessions() as session:
            row=session.execute(select(source_jobs).where(source_jobs.c.id==queued['id'])).mappings().one()
            self.assertEqual(row['attempts'],0)
            self.assertIsNotNone(row['retry_at'])

    async def test_source_migration_requires_drain_and_retains_originals(self):
        from alembic import command
        from app.db.migrate import migration_config,upgrade
        from app.assessments.repositories.source_jobs import SourceJobs
        from app.assessments.repositories.tables import source_jobs
        from sqlalchemy import update
        assessment,attempt=await self.prepared()
        stored=self.files.upload(self.owner,BytesIO(b'original'),'answers.txt','assessment','rollback-source')
        queued=SourceJobs(self.service.repository).enqueue(self.owner,str(attempt.id),stored['id'],attempt.revision)
        with self.assertRaisesRegex(RuntimeError,'Drain assessment source jobs'):
            with self.db.engine.connect() as connection:
                command.downgrade(migration_config(connection),'20261103_0039')
        with self.db.sessions.begin() as session:
            session.execute(update(source_jobs).where(source_jobs.c.id==queued['id']).values(state='failed'))
        with self.db.engine.connect() as connection:
            command.downgrade(migration_config(connection),'20261103_0039')
        self.assertEqual(self.files.read(self.owner,stored['id']),b'original')
        from app.assessments.repositories.tables import attempts
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(attempts.c.state).where(attempts.c.id==str(attempt.id))),'draft')
        upgrade(self.db.engine)
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'draft')
        with self.db.engine.connect() as connection:
            command.check(migration_config(connection))

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
        self.assertTrue(await run_assessment_pipeline(self.service))
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
        file=self.files.upload(self.owner,BytesIO(b'answers'),'answers.txt','assessment','paper')
        extracted=await self.service.upload_paper_with_vision(self.owner,str(attempt.id),1,file['id'])
        self.assertEqual(extracted.state,'pending_transcription')
        self.assertIsNone(extracted.extraction['extraction_confidence'])
        self.assertFalse(await run_assessment_pipeline(self.service))
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=2,client_request_id=uuid4(),answers=extracted.extraction['answers'],transcription_confirmed=True))
        await run_assessment_pipeline(self.service)
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).evidence_status,'applied')

    async def test_delete_and_new_concepts_need_no_confirmation(self):
        self.request=self.request.model_copy(update={'confirm_new_concepts':False})
        assessment,attempt=await self.prepared()
        self.service.repository.remove(self.owner,str(assessment.id))
        with self.assertRaises(AppError): self.service.repository.attempt(self.owner,str(attempt.id))

    async def test_correction_preserves_history_and_supersedes_question_evidence(self):
        assessment,attempt=await self.prepared()
        answers={str(question.id):'Original answer' for question in assessment.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers=answers))
        await run_assessment_pipeline(self.service)
        graded=self.service.repository.attempt(self.owner,str(attempt.id))
        corrected=self.service.repository.correct(self.owner,str(attempt.id),SubmitAnswers(expected_revision=graded.revision,client_request_id=uuid4(),answers={key:'Corrected answer' for key in answers}))
        self.assertEqual(corrected.grade_revision,2)
        await run_assessment_pipeline(self.service)
        final=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(final.state,'graded');self.assertEqual(len(final.grade_history),1)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),4)

    async def test_uncertain_correction_withdraws_previous_evidence_atomically(self):
        from app.learner.repositories.tables.evidence import evidence_decision
        assessment, attempt = await self.prepared()
        answers = {str(question.id):'Original answer' for question in assessment.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers=answers))
        await run_assessment_pipeline(self.service)
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
        self.assertTrue(await run_assessment_pipeline(self.service))
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
        await run_assessment_pipeline(self.service)
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
        payload = self.request.model_dump(mode='json',include={'client_request_id','context_id','topic','concept_names','confirm_new_concepts','count','purpose','grounded','document_ids'})
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
        from app.learner.schemas import ConceptResolutionRequest
        self.learner.resolve_concept(ConceptResolutionRequest(learner_id=self.owner,
            context_id=self.request.context_id, label='Linear equations'))
        candidates=self.learner.get_pending_concepts(self.owner)
        self.assertEqual(len(candidates),1)
        self.assertFalse(self.learner.get_pending_concepts(self.other))
        with self.assertRaises(AppError): self.learner.review_owned_candidate(self.other,candidates[0]['id'])
        concept=self.learner.review_owned_candidate(self.owner,candidates[0]['id'])
        self.assertEqual(self.learner.review_owned_candidate(self.owner,candidates[0]['id']).id,concept.id)
        self.assertFalse(self.learner.get_pending_concepts(self.owner))

    async def test_original_bytes_are_external_to_attempt_rows(self):
        assessment,attempt=await self.prepared()
        from app.assessments.repositories.tables import attempts
        file=self.files.upload(self.owner,BytesIO(b'x'*1024),'answers.txt','assessment','external-source')
        self.service.repository.store_extraction(self.owner,str(attempt.id),attempt.revision,{},file['id'],'answers.txt')
        self.assertNotIn('source',attempts.c)
        with self.db.sessions() as session:
            internal=self.service.repository._attempt(session,self.owner,str(attempt.id))
            self.assertNotIn('source',internal)
            self.assertEqual(internal['source_file_id'],file['id'])
        self.assertEqual(self.files.read(self.owner,file['id']),b'x'*1024)
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).id,attempt.id)
