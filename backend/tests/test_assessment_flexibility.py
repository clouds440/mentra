import os
import json
import unittest
from uuid import uuid4
from types import SimpleNamespace
from sqlalchemy import select, update
from app.assessments.schemas import GenerationRequest, GeneratedQuestion, StartAttempt, SubmitAnswers
from app.assessments.blueprint import blueprint, question_reference, parse_numbered_answers
from app.assessments.choice_answers import selected_options
from app.assessments.service import create_assessments
from app.assessments.worker import AssessmentWorker
from app.assessments.generation_worker import AssessmentGenerationWorker
from app.assessments.repositories.tables import generation_jobs, assessments
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest, GeneratedConceptsRequest
from app.langchain.llm import MentraLLM
from app.core.exceptions import AppError
from testing.history_model import HistoryChatFactory
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class FlexibleContractTests(unittest.TestCase):
    def test_shorthand_expansion_does_not_change_request_fingerprint(self):
        request=GenerationRequest(client_request_id=uuid4(),context_id='context',topic='Science',count=2,
            question_format='mock_paper',total_marks=10,
            paper_sections=[dict(title='Reasoning',question_count=2,part_marks=[2,3])])
        before=request.fingerprint_payload()
        plan,paper=blueprint(request)
        self.assertEqual(len(plan),4)
        self.assertEqual(paper.total_marks,10)
        self.assertEqual(request.fingerprint_payload(),before)

    def test_long_questions_and_new_types_are_not_character_capped(self):
        value = GeneratedQuestion(prompt='A detailed case. ' * 2000, concept_names=['New concept'], question_type='case_analysis',
            difficulty=.5, marks=35, model_answer='A complete answer. ' * 500, rubric='Award credit. ' * 500)
        self.assertGreater(len(value.prompt), 3000)
        self.assertEqual(value.answer_mode, 'text')

    def test_nested_references_and_written_option_letters(self):
        request = GenerationRequest(client_request_id=uuid4(), context_id='context', topic='Science', count=1, question_format='mock_paper',
            paper_sections=[dict(title='Structured', questions=[dict(number=3, context='Shared scenario', parts=[
                dict(path=['a','i'], marks=3), dict(path=['a','ii'], marks=4), dict(path=['b'], marks=5)])])])
        plan, paper = blueprint(request)
        self.assertEqual([question_reference(q, i) for i,q in enumerate(plan,1)], ['3a.i','3a.ii','3b'])
        self.assertEqual(paper.total_marks, 12)
        self.assertEqual(parse_numbered_answers('Q3(a)(i). First\n3(a)(ii) Second\n3b. Third'), [('3a.i','First'),('3a.ii','Second'),('3b','Third')])
        self.assertEqual(selected_options({'options':[dict(id='opaque-1',label='First'),dict(id='opaque-2',label='Second')]}, 'B'), ['opaque-2'])

    def test_explicit_objective_outline_and_timing_are_supported(self):
        request = GenerationRequest(client_request_id=uuid4(), context_id='context', topic='Science', count=1,
            question_format='mock_paper', duration_minutes=120, paper_sections=[dict(title='Objective',
                question_type='mcq', questions=[dict(number=1, parts=[dict(question_type='mcq', answer_mode='single_choice', marks=2)])])])
        from app.assessments.blueprint import flatten_sections
        plan, paper = flatten_sections(request, request.paper_sections, duration=60)
        self.assertEqual(plan[0]['question_type'], 'mcq')
        self.assertEqual(paper.duration_minutes, 120)

    def test_ai_outline_marks_are_balanced_without_discarding_parts(self):
        from app.assessments.blueprint import balance_outline_marks
        from app.assessments.schemas import PaperSection
        sections = [PaperSection(title='Reasoning', questions=[dict(number=1,parts=[dict(path=['a'],marks=3),dict(path=['b'],marks=4)])])]
        for total in (10, 1.5, .001):
            balance_outline_marks(sections,total)
            parts = sections[0].questions[0].parts
            self.assertAlmostEqual(sum(part.marks for part in parts),total)
            self.assertTrue(all(part.marks>0 for part in parts))
            self.assertEqual([part.path for part in parts],[['a'],['b']])


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires isolated test database')
class FlexibleEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = PostgresSandbox(); self.addCleanup(self.db.close)
        self.owner = learner_id('alice'); self.other = learner_id('bob')
        self.learner = LearnerEngine(self.db.repository)
        self.context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner,name='Flexible science'))
        self.factory = HistoryChatFactory()
        self.service = create_assessments(self.db.sessions, MentraLLM(self.factory), self.learner)

    def request(self, **kwargs):
        return GenerationRequest(client_request_id=uuid4(),context_id=self.context.context_id,topic='Scientific reasoning',concept_names=['Science: evidence'],**kwargs)

    async def test_mixed_generation_submission_and_grading_use_real_domain_pipeline(self):
        value = await self.service.generate(self.owner, self.request(count=6,question_format='mixed'))
        self.assertEqual(len(value.questions), 6)
        self.assertEqual({q.question_type for q in value.questions}, {'mcq','true_false','short_answer','multiple_select','numerical','essay'})
        self.assertNotIn('correct_option', value.model_dump_json())
        attempt = self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        answers = {str(q.id): json.dumps(['a','b']) if q.answer_mode=='multiple_choice' else q.options[0].id if q.options else 'My explanation.' for q in value.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,client_request_id=uuid4(),answers=answers))
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        result = self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(result.state, 'graded')
        self.assertEqual(len(result.grades), 6)

    async def test_full_paper_is_durable_private_and_gradeable_by_parts(self):
        request = self.request(count=12,question_format='mock_paper',total_marks=96)
        job = await self.service.queue_generation(self.owner, request)
        self.assertEqual((await self.service.queue_generation(self.owner,request))['id'], job['id'])
        with self.assertRaises(AppError): self.service.generation_jobs.get(self.other,job['id'])
        self.assertTrue(await AssessmentGenerationWorker(self.service).run_once())
        complete = self.service.generation_jobs.get(self.owner,job['id'])
        self.assertEqual(complete['state'], 'completed', complete)
        self.assertNotIn('model_answer', json.dumps(complete))
        value = self.service.repository.detail(self.owner,complete['result']['id'])
        self.assertEqual(value.paper.question_count,12); self.assertEqual(value.paper.total_marks,96)
        self.assertEqual(len(value.questions),24)
        self.assertEqual(question_reference(value.questions[3],4), '2b')
        attempt = self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={str(q.id):'A supported answer.' for q in value.questions}))
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'graded')

    async def test_selecting_every_option_does_not_earn_partial_credit(self):
        value = await self.service.generate(self.owner, self.request(count=1,question_format='multiple_select'))
        attempt = self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        question = value.questions[0]
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(),answers={str(question.id):json.dumps([option.id for option in question.options])}))
        await AssessmentWorker(self.service).run_once()
        result = self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(result.state,'graded')
        self.assertEqual(result.grades[0].score,0)

    async def test_permissive_concept_resolution_uses_new_ids_without_merging_history(self):
        first = self.learner.register_concept('Physics: fields',aliases=('fields',))
        second = self.learner.register_concept('Mathematics: fields',aliases=('fields',))
        resolved = await self.learner.resolve_generated_concepts(GeneratedConceptsRequest(learner_id=self.owner,
            context_id=self.context.context_id,topic='Electromagnetism',labels=['fields','A completely new concept'],permissive=True))
        self.assertEqual(len(resolved),2)
        self.assertNotIn(resolved[0].id,{first.id,second.id})
        self.assertEqual(self.learner.get_concepts([first.id,second.id])[first.id].canonical_name,'Physics: fields')

    async def test_unknown_generated_concepts_are_resolved_without_rejecting_questions(self):
        original = self.factory.with_structured_output
        def fresh(schema, **kwargs):
            model = original(schema, **kwargs)
            if schema.__name__ not in ('GeneratedAssessment', 'GeneratedAssessmentBatch'): return model
            async def invoke(messages):
                result = await model.ainvoke(messages)
                for question in result.questions:
                    question.concept_ids = [str(uuid4())]
                    question.concept_names = ['Science: a newly introduced relationship']
                return result
            return SimpleNamespace(ainvoke=invoke)
        self.factory.with_structured_output = fresh
        value = await self.service.generate(self.owner,self.request(count=2,question_format='written'))
        self.assertEqual(len(value.questions),2)
        for question in value.questions:
            self.assertTrue(question.concept_ids)
            self.assertEqual(self.learner.get_concepts(question.concept_ids)[question.concept_ids[0]].canonical_name,'Science: a newly introduced relationship')

    async def test_migration_preserves_existing_questions_attempts_and_grading_keys(self):
        value = await self.service.generate(self.owner,self.request(count=2,question_format='written'))
        attempt = self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        with self.db.sessions() as session:
            before = session.execute(select(assessments.c.questions).where(assessments.c.id==str(value.id))).scalar_one()
        from alembic import command
        from app.db.migrate import migration_config, upgrade
        with self.db.engine.connect() as connection:
            command.downgrade(migration_config(connection),'20261014_0022')
        upgrade(self.db.engine)
        with self.db.sessions() as session:
            after = session.execute(select(assessments.c.questions).where(assessments.c.id==str(value.id))).scalar_one()
        self.assertEqual(before,after)
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'draft')

    async def test_generation_checkpoints_resume_and_stale_workers_cannot_publish(self):
        factory = self.factory
        original = factory.with_structured_output
        offsets, fail = [], [True]
        def scripted(schema, **kwargs):
            model = original(schema, **kwargs)
            if schema.__name__ not in ('GeneratedAssessment', 'GeneratedAssessmentBatch'): return model
            async def invoke(messages):
                payload = json.loads(messages[-1].content); offset = payload['question_offset']; offsets.append(offset)
                if offset == 6 and fail[0]: raise RuntimeError('interrupted')
                return await model.ainvoke(messages)
            return SimpleNamespace(ainvoke=invoke)
        factory.with_structured_output = scripted
        job = await self.service.queue_generation(self.owner,self.request(count=12,question_format='mock_paper'))
        worker = AssessmentGenerationWorker(self.service)
        await worker.run_once()
        failed = self.service.generation_jobs.get(self.owner,job['id'])
        self.assertEqual(failed['state'],'failed'); self.assertEqual(failed['completed_parts'],6)
        fail[0] = False
        self.service.generation_jobs.retry(self.owner,job['id']); await worker.run_once()
        self.assertEqual(self.service.generation_jobs.get(self.owner,job['id'])['state'],'completed')
        self.assertEqual(offsets.count(0),1); self.assertEqual(offsets.count(6),2)
        with self.db.sessions() as session:
            self.assertEqual(len(session.execute(select(assessments).where(assessments.c.learner_id==self.owner)).all()),1)
        another = await self.service.queue_generation(self.owner,self.request(count=2,question_format='written'))
        old = self.service.generation_jobs.claim()
        with self.db.sessions.begin() as session:
            from datetime import timedelta
            session.execute(update(generation_jobs).where(generation_jobs.c.id==another['id']).values(claim_until=self.service.repository.clock()-timedelta(seconds=1)))
        new = self.service.generation_jobs.claim()
        self.assertNotEqual(old['claim_id'],new['claim_id'])
        with self.assertRaises(AppError): self.service.generation_jobs.update(old,state='completed',result={})

    async def test_grading_resumes_validated_batches_without_publishing_partial_feedback(self):
        import asyncio
        from app.assessments.schemas import RetryGrading
        value = await self.service.generate(self.owner,self.request(count=20,question_format='written'))
        from app.core.config import settings
        self.factory._settings = settings.model_copy(update={'assessment_grading_output_tokens':4096})
        attempt = self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=1,client_request_id=uuid4(),answers={str(q.id):'My answer.' for q in value.questions}))
        original = self.factory.with_structured_output; seen, fail = [], [True]
        def scripted(schema, **kwargs):
            model = original(schema,**kwargs)
            if schema.__name__ != 'GradedAssessment': return model
            async def invoke(messages):
                payload = json.loads(messages[-1].content); key = payload['questions'][0]['id']; seen.append(key)
                if key == str(value.questions[10].id) and fail[0]:
                    await asyncio.sleep(.1)
                    raise RuntimeError('interrupted grading')
                return await model.ainvoke(messages)
            return SimpleNamespace(ainvoke=invoke)
        self.factory.with_structured_output=scripted
        worker=AssessmentWorker(self.service)
        await worker.run_once()
        failed=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(failed.state,'failed'); self.assertIsNone(failed.grades)
        self.service.repository.retry_grading(self.owner,str(attempt.id),RetryGrading(client_request_id=uuid4(),expected_revision=failed.revision))
        fail[0]=False; await worker.run_once()
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'graded')
        self.assertEqual(seen.count(str(value.questions[0].id)),1)
        self.assertEqual(seen.count(str(value.questions[10].id)),2)
