"""Regression boundaries between new practice shortcuts and existing durable workflows."""
import unittest
import os
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select, update
from app.assessments.schemas import MistakePracticeRequest, StartAttempt, SubmitAnswers, AssessmentIntent
from app.assessments.repositories.tables import assessments
from app.assessments.evidence_worker import AssessmentEvidenceWorker
from app.learner.repositories.tables import learning_evidence
from app.learner.schemas import ConceptStateRequest
from app.core.exceptions import AppError
from testing.assessment_workers import run_assessment_pipeline
from tests import test_assessments as fixtures


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated database')
class ProductFollowupTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.AssessmentTests.setUp

    async def test_deleted_chat_purges_unsaved_jobs_and_cannot_enqueue_after_authorization_race(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        from app.assessments.repositories.tables import generation_jobs
        repository = ChatRepository(self.db.sessions)
        conversation = str(uuid4())
        repository.begin_turn(self.owner,SendTurn(conversation_id=conversation,client_turn_id=uuid4(),expected_revision=0,content='Prepare practice.'))
        request = AssessmentIntent(client_request_id=uuid4(),context_id=self.request.context_id,topic='Practice',count=3)
        job = self.service.generation_jobs.enqueue(self.owner,request,conversation)
        current = repository.status(self.owner,conversation)
        repository.edit(self.owner,conversation,current['conversation']['revision'],None,True)
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(generation_jobs.c.id).where(generation_jobs.c.id==job['id'])))
        with self.assertRaises(AppError):
            self.service.generation_jobs.enqueue(self.owner,request.model_copy(update={'client_request_id':uuid4()}),conversation)

    async def test_deleted_followup_operation_cannot_resurrect_on_retry(self):
        from app.assessments.repositories.tables import practice_operations
        source, attempt = await self.graded()
        body = MistakePracticeRequest(client_request_id=uuid4(), expected_grade_revision=1, question_ids=[source.questions[0].id])
        child = self.service.repository.practise_mistakes(self.owner,str(attempt.id),body)
        self.service.repository.remove(self.owner,str(child.id))
        with self.assertRaises(AppError) as failure:
            self.service.repository.practise_mistakes(self.owner,str(attempt.id),body)
        self.assertEqual(failure.exception.code,'ASSESSMENT_PRACTICE_DELETED')
        with self.db.sessions() as session:
            self.assertEqual(len(session.execute(select(practice_operations)).all()),1)
            self.assertIsNone(session.scalar(select(assessments.c.id).where(assessments.c.id==str(child.id))))
        fresh = self.service.repository.practise_mistakes(self.owner,str(attempt.id),body.model_copy(update={'client_request_id':uuid4()}))
        self.assertNotEqual(fresh.id,child.id)

    async def test_database_fence_protects_older_workers_from_claimed_independence(self):
        from app.assessments.repositories.tables import attempts
        source, result = await self.graded()
        concept = source.questions[0].concept_ids[0]
        before = self.learner.get_concept_state(ConceptStateRequest(learner_id=self.owner,concept_id=concept))
        child = self.service.repository.practise_mistakes(self.owner,str(result.id),MistakePracticeRequest(
            client_request_id=uuid4(), expected_grade_revision=1,question_ids=[source.questions[0].id]))
        attempt = self.service.repository.start(self.owner,str(child.id),StartAttempt(client_request_id=uuid4()))
        self.assertEqual(attempt.assistance,'assisted')
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),
            answers={str(child.questions[0].id):'a'},assistance='independent'))
        with self.db.sessions.begin() as session:
            # Simulate the previous API writing only fields it understands.
            session.execute(update(attempts).where(attempts.c.id==str(attempt.id)).values(assistance='independent'))
        job = self.service.repository.claim()
        self.assertEqual(job['attempt']['assistance'],'assisted')
        job['assessment'].pop('practice_lineage')  # Previous worker's projection.
        grades = await self.service.workflows.grade(job)
        self.service.repository.complete(job,grades,lambda tx:self.service.workflows.evidence(job,grades,tx))
        after = self.learner.get_concept_state(ConceptStateRequest(learner_id=self.owner,concept_id=concept))
        self.assertEqual(after.mastery,before.mastery)
        self.assertEqual(after.independent_item_count,before.independent_item_count)

    async def test_concurrent_duplicate_creation_returns_one_derivative(self):
        from concurrent.futures import ThreadPoolExecutor
        source, attempt = await self.graded()
        body = MistakePracticeRequest(client_request_id=uuid4(), expected_grade_revision=1, question_ids=[source.questions[0].id])
        with ThreadPoolExecutor(2) as pool:
            children = list(pool.map(lambda _: self.service.repository.practise_mistakes(self.owner, str(attempt.id), body), range(2)))
        self.assertEqual(children[0].id, children[1].id)

    async def test_migration_roundtrip_preserves_existing_records_and_refuses_to_erase_exposure(self):
        from alembic import command
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from sqlalchemy import text
        from app.db.metadata import metadata
        from app.db.migrate import migration_config, upgrade
        source = await self.service.generate(self.owner, self.request)
        with self.db.engine.connect() as connection:
            command.downgrade(migration_config(connection), '20261015_0025')
        upgrade(self.db.engine)
        self.assertEqual(self.service.repository.detail(self.owner, str(source.id)), source)
        with self.db.engine.connect() as connection:
            diffs = compare_metadata(MigrationContext.configure(connection, opts={
                'include_object':lambda obj,name,kind,reflected,compare_to: kind!='table' or name=='assessment'}), metadata)
            self.assertEqual(diffs, [])
        original, attempt = await self.graded()
        child = self.service.repository.practise_mistakes(self.owner, str(attempt.id), MistakePracticeRequest(
            client_request_id=uuid4(), expected_grade_revision=1, question_ids=[original.questions[0].id]))
        with self.db.engine.connect() as connection:
            # Newer migrations also refuse to discard saved score-policy history
            # before the older exposure-lineage fence can be reached.
            with self.assertRaisesRegex(RuntimeError, 'Cannot (remove exposure lineage|discard saved assessment score-adjustment provenance)'):
                command.downgrade(migration_config(connection), '20261015_0025')
        self.assertEqual(self.service.repository.detail(self.owner, str(child.id)), child)
        with self.db.engine.connect() as connection:
            from alembic.script import ScriptDirectory
            self.assertEqual(connection.scalar(text('SELECT version_num FROM alembic_version')),
                             ScriptDirectory.from_config(migration_config()).get_current_head())
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        conversation = str(uuid4())
        ChatRepository(self.db.sessions).begin_turn(self.owner, SendTurn(conversation_id=conversation,
            client_turn_id=uuid4(), expected_revision=0, content='Keep a written practice draft.'))
        card = await self.service.generate_chat(self.owner, conversation, self.request.model_copy(update={
            'client_request_id':uuid4(), 'question_format':'written', 'count':1, 'revision_assessment_id':child.id,
            'revision_instructions':'Keep this as a written practice draft.'}))
        self.assertIsNone(card['assessment_id'])
        self.service.repository.remove(self.owner, str(child.id))
        with self.db.engine.connect() as connection:
            with self.assertRaisesRegex(RuntimeError, 'Cannot (remove exposure lineage|discard saved assessment score-adjustment provenance)'):
                command.downgrade(migration_config(connection), '20261015_0025')

    async def test_api_practice_and_evidence_projection_use_typed_private_responses(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.assessments import router as assessment_router
        from app.api.routes.learning import router as learning_router
        from app.student_profile.dependencies import require_onboarded_identity
        source, result = await self.graded()
        app = FastAPI()
        app.state.assessment_service, app.state.learner_service = self.service, self.learner
        app.dependency_overrides[require_onboarded_identity] = lambda: SimpleNamespace(learner_id=self.owner)
        app.include_router(assessment_router, prefix='/api/v1'); app.include_router(learning_router, prefix='/api/v1')
        with TestClient(app) as client:
            response = client.post(f'/api/v1/assessments/attempts/{result.id}/practice', json=dict(
                client_request_id=str(uuid4()), expected_grade_revision=1, question_ids=[str(source.questions[0].id)]))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertTrue(response.json()['practice_source']['known_exposure'])
            self.assertNotIn('correct_option_id', response.text)
            detail = client.get(f'/api/v1/learning/understanding/{source.questions[0].concept_ids[0]}', params={'context_id':source.context_id})
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.headers['cache-control'], 'no-store')
            self.assertTrue(detail.json()['recent_evidence'][0]['source_available'])
            self.assertNotIn('policy_data', detail.text)

    async def graded(self):
        assessment = await self.service.generate(self.owner, self.request.model_copy(update={'client_request_id':uuid4(), 'question_format':'mcq', 'count':6}))
        attempt = self.service.repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=1, client_request_id=uuid4(),
            answers={str(q.id):'b' if i < 5 else 'a' for i,q in enumerate(assessment.questions)}, assistance='independent'))
        job = self.service.repository.claim()
        grades = await self.service.workflows.grade(job)
        # Domain-trusted partial grades model a mixed written/multiple-select paper.
        for i in (3,4):
            grade = grades.questions[i]
            grade.score = assessment.questions[i].marks / 2
            for value in grade.concept_grades.values(): value.score = grade.score
        self.service.repository.complete(job, grades)
        await AssessmentEvidenceWorker(self.service).run_once()
        return assessment, self.service.repository.attempt(self.owner, str(attempt.id))

    async def test_subset_replay_private_keys_parent_immutability_and_owner_isolation(self):
        source, result = await self.graded()
        ids = [str(q.id) for q in source.questions[:5]]
        body = MistakePracticeRequest(client_request_id=uuid4(), expected_grade_revision=result.grade_revision, question_ids=ids)
        child = self.service.repository.practise_mistakes(self.owner, str(result.id), body)
        self.assertEqual(len(child.questions), 5)
        self.assertEqual([q.prompt for q in child.questions], [q.prompt for q in source.questions[:5]])
        self.assertTrue(set(str(q.id) for q in child.questions).isdisjoint(ids))
        for secret in ('model_answer','rubric','correct_option_id','question_items'):
            self.assertNotIn(secret, child.model_dump_json())
        self.assertTrue(child.practice_source.known_exposure)
        self.assertEqual(self.service.repository.practise_mistakes(self.owner, str(result.id), body).id, child.id)
        self.assertEqual(self.service.repository.attempt(self.owner, str(result.id)), result)
        self.assertEqual(self.service.repository.detail(self.owner, str(source.id)), source)
        for owner, request in [(self.other, body), (self.owner, body.model_copy(update={'client_request_id':uuid4(), 'expected_grade_revision':2})),
                (self.owner, body.model_copy(update={'client_request_id':uuid4(), 'question_ids':[source.questions[-1].id]}))]:
            with self.assertRaises(AppError): self.service.repository.practise_mistakes(owner, str(result.id), request)
        with self.assertRaises(AppError):
            self.service.repository.practise_mistakes(self.owner, str(result.id), body.model_copy(update={'question_ids':[source.questions[0].id]}))
        # Recovery uses the saved child even after the parent was deleted.
        self.service.repository.remove(self.owner, str(source.id))
        self.assertEqual(self.service.repository.practise_mistakes(self.owner, str(result.id), body).id, child.id)
        self.assertEqual(self.service.repository.detail(self.owner, str(child.id)), child)

    async def test_exposed_practice_and_corrections_keep_root_item_and_never_add_independent_items(self):
        source, result = await self.graded()
        concept = source.questions[0].concept_ids[0]
        before = self.learner.get_concept_state(ConceptStateRequest(learner_id=self.owner, concept_id=concept))
        body = MistakePracticeRequest(client_request_id=uuid4(), expected_grade_revision=1, question_ids=[source.questions[0].id])
        child = self.service.repository.practise_mistakes(self.owner, str(result.id), body)
        attempt = self.service.repository.start(self.owner, str(child.id), StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=1, client_request_id=uuid4(),
            answers={str(child.questions[0].id):'a'}, assistance='independent'))
        self.assertTrue(await run_assessment_pipeline(self.service))
        graded = self.service.repository.attempt(self.owner, str(attempt.id))
        after = self.learner.get_concept_state(ConceptStateRequest(learner_id=self.owner, concept_id=concept))
        self.assertEqual(after.independent_item_count, before.independent_item_count)
        self.assertEqual(after.mastery, before.mastery)
        self.assertEqual(after.last_demonstrated_at, before.last_demonstrated_at)
        self.service.repository.correct(self.owner, str(attempt.id), SubmitAnswers(expected_revision=graded.revision,
            client_request_id=uuid4(), answers={str(child.questions[0].id):'b'}, assistance='independent'))
        self.assertTrue(await run_assessment_pipeline(self.service))
        with self.db.sessions() as session:
            records = session.execute(select(learning_evidence).where(learning_evidence.c.session_id==str(attempt.id))).mappings().all()
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r['item_id']==f'{source.id}:{source.questions[0].id}' and r['independence']==0 and r['attempt_number']==2 for r in records))
        corrected = self.service.repository.attempt(self.owner, str(attempt.id))
        grandchild = self.service.repository.practise_mistakes(self.owner, str(attempt.id), MistakePracticeRequest(
            client_request_id=uuid4(), expected_grade_revision=corrected.grade_revision, question_ids=[child.questions[0].id]))
        with self.db.sessions() as session:
            row = self.service.repository._assessment(session, self.owner, str(grandchild.id))
            self.assertEqual(row['practice_lineage']['question_items'][str(grandchild.questions[0].id)], f'{source.id}:{source.questions[0].id}')
        explanation = self.learner.get_progress_explanation(self.owner, concept, source.context_id)
        self.assertEqual(explanation.recent_evidence[0].participation, 'repeated')
        self.assertEqual(explanation.recent_evidence[0].grade_revision, 2)
        self.assertLessEqual(len(explanation.recent_evidence), 5)
        self.assertNotIn('policy_data', explanation.model_dump_json())
        self.assertEqual(explanation.independent_item_count, before.independent_item_count)

    async def test_paper_references_keep_cross_part_context_but_only_selected_parts_take_answers(self):
        source, result = await self.graded()
        from app.assessments.schemas import PaperInfo
        paper = PaperInfo(total_marks=12, question_count=3, instructions='Use the following passage for all parts.',
            sections=[dict(title='Section A', question_count=3, part_marks=[2,2], instructions='Give units.')])
        with self.db.sessions.begin() as session:
            row = self.service.repository._assessment(session, self.owner, str(source.id))
            questions = row['questions']
            for i,q in enumerate(questions):
                q.update(number=i//2+1, part='a' if i%2==0 else 'b', context='Shared passage: speed = distance / time.')
            session.execute(update(assessments).where(assessments.c.id==str(source.id)).values(questions=questions, paper=paper.model_dump(mode='json')))
        child = self.service.repository.practise_mistakes(self.owner, str(result.id), MistakePracticeRequest(
            client_request_id=uuid4(), expected_grade_revision=1, question_ids=[source.questions[1].id]))
        self.assertEqual(len(child.questions), 1)
        self.assertEqual(child.questions[0].part, 'b')
        self.assertIn('Shared passage', child.questions[0].context)
        self.assertEqual(len(child.practice_source.reference_questions), 6)
        self.assertIn('Give units.', child.practice_source.instructions)
        self.assertNotIn('model_answer', child.model_dump_json())
        from app.langchain.grading_batches import grading_payload
        with self.db.sessions() as session:
            private = self.service.repository._assessment(session, self.owner, str(child.id))
        payload = grading_payload(private, dict(answers={str(child.questions[0].id):'work'}), private['questions'])
        self.assertEqual(len(payload['questions']), 1)
        self.assertEqual(len(payload['original_paper_reference']['questions']), 6)

    async def test_generation_replay_precedes_mutable_targets_and_checks_payload(self):
        intent = AssessmentIntent(client_request_id=uuid4(), context_id=self.request.context_id, topic='Recover me',
            concept_ids=[uuid4()], count=3)
        with patch.object(self.learner, 'get_practice_concepts', return_value=[]):
            job = await self.service.queue_generation(self.owner, intent)
        with patch.object(self.learner, 'get_practice_concepts', side_effect=AppError('UNAVAILABLE','Changed',404)) as validate:
            replay = await self.service.queue_generation(self.owner, intent)
            self.assertEqual(replay['id'], job['id'])
            validate.assert_not_called()
            with self.assertRaises(AppError):
                await self.service.queue_generation(self.owner, intent.model_copy(update={'topic':'Changed'}))

    async def test_revision_and_chat_publication_cannot_strip_known_exposure(self):
        source, attempt = await self.graded()
        child = self.service.repository.practise_mistakes(self.owner, str(attempt.id), MistakePracticeRequest(
            client_request_id=uuid4(), expected_grade_revision=1, question_ids=[source.questions[0].id]))
        request = self.request.model_copy(update={'client_request_id':uuid4(), 'question_format':'mcq', 'count':1,
            'revision_assessment_id':child.id, 'revision_instructions':'Keep the same question and make the wording clearer.'})
        revised = await self.service.generate(self.owner, request)
        self.assertTrue(revised.practice_source.known_exposure)
        self.assertEqual(revised.practice_source.attempt_id, attempt.id)
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        conversation = str(uuid4())
        ChatRepository(self.db.sessions).begin_turn(self.owner, SendTurn(conversation_id=conversation,
            client_turn_id=uuid4(), expected_revision=0, content='Revise my mistake practice.'))
        card = await self.service.generate_chat(self.owner, conversation, request.model_copy(update={'client_request_id':uuid4()}))
        self.assertTrue(card['assessment']['practice_source']['known_exposure'])
        published = self.service.repository.detail(self.owner, card['assessment_id'])
        self.assertTrue(published.practice_source.known_exposure)

    async def test_unknown_explanation_and_deleted_source_links_preserve_accepted_evidence(self):
        concept = self.learner.register_concept('Unpractised topic')
        self.learner.link_context_concept(self.owner, self.request.context_id, concept.id)
        value = self.learner.get_progress_explanation(self.owner, concept.id, self.request.context_id)
        self.assertIsNone(value.mastery); self.assertEqual(value.evidence_count, 0)
        self.assertEqual(value.recent_evidence, [])
        self.assertIsNone(value.last_independent_at)
        with self.assertRaises(AppError): self.learner.get_progress_explanation(self.other, concept.id)
        source, attempt = await self.graded()
        references = [(str(source.id), str(attempt.id), attempt.grade_revision)]
        self.assertEqual(self.service.repository.available_evidence_sources(self.owner, references), set(references))
        self.assertEqual(self.service.repository.available_evidence_sources(self.other, references), set())
        self.service.repository.remove(self.owner, str(source.id))
        self.assertEqual(self.service.repository.available_evidence_sources(self.owner, references), set())
        value = self.learner.get_progress_explanation(self.owner, source.questions[0].concept_ids[0], source.context_id)
        self.assertGreater(value.evidence_count, 0)
        self.assertTrue(value.recent_evidence)

    async def test_uncertain_regrade_withdraws_old_support_without_erasing_observations(self):
        source, attempt = await self.graded()
        self.service.repository.correct(self.owner, str(attempt.id), SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(), answers=attempt.answers, assistance='independent'))
        job = self.service.repository.claim()
        grades = await self.service.workflows.grade(job)
        for grade in grades.questions: grade.confidence = .5
        self.service.repository.complete(job, grades, lambda tx:self.service.workflows.evidence(job, grades, tx))
        value = self.learner.get_progress_explanation(self.owner, source.questions[0].concept_ids[0], source.context_id)
        self.assertEqual(value.recent_evidence, [])
        self.assertEqual(value.evidence_count, 0)
        self.assertIsNone(value.mastery)
        with self.db.sessions() as session:
            self.assertEqual(len(session.execute(select(learning_evidence.c.id)).all()), 6)
