import os
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select
from app.assessments.schemas import AssessmentIntent, GenerationRequest
from app.assessments.generation_worker import AssessmentGenerationWorker
from app.assessments.repositories.tables import generation_jobs
from app.langchain.assessment_selection import resolve_assessment_intent
from app.langchain.workflow_tools import GeneratePractice, create_workflow_tools
from app.history_management.budgets import ToolBudget
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.learner.schemas import GeneratedConceptsRequest
from app.student_profile.schemas import ProfileContext, ProfileDetails
from tests import test_assessment_flexibility as flexible
from app.core.exceptions import AppError


class IntentContractTests(unittest.TestCase):
    def test_exact_targets_preserve_legacy_fingerprints_and_require_a_context(self):
        from pydantic import ValidationError
        body = dict(client_request_id=uuid4(), context_id='context', topic='Topic')
        self.assertNotIn('concept_ids', GenerationRequest(**body).fingerprint_payload())
        selected = GenerationRequest(**body, concept_ids=[uuid4()])
        self.assertIn('concept_ids', selected.fingerprint_payload())
        with self.assertRaises(ValidationError):
            AssessmentIntent(client_request_id=uuid4(), concept_ids=[uuid4()])
    def test_selected_formats_are_canonical_and_preserve_legacy_replays(self):
        from pydantic import ValidationError
        body = dict(client_request_id=uuid4(), context_id='context', topic='Forces')
        self.assertNotIn('question_formats', GenerationRequest(**body).fingerprint_payload())
        value = AssessmentIntent(**body, count=4, question_formats=['multiple_choice','short_answer','mcq'])
        self.assertNotIn('result_style', value.fingerprint_payload())
        self.assertEqual(value.question_formats, ['mcq','short_answer'])
        self.assertEqual(value.question_format, 'mixed')
        with self.assertRaises(ValidationError):
            AssessmentIntent(**body, count=1, question_formats=['mcq','short_answer'])
        with self.assertRaises(ValidationError):
            AssessmentIntent(**body, question_formats=['auto'])

    def test_selected_formats_reject_unrequested_types_and_extra_answers(self):
        import asyncio
        from unittest.mock import AsyncMock
        from app.langchain.assessment_design import design_assessment
        from app.assessments.schemas import AssessmentDesign
        for parts in ([dict(question_type='essay',marks=1)], [dict(path=['a'],question_type='mcq',marks=1),dict(path=['b'],question_type='mcq',marks=1)]):
            request=GenerationRequest(client_request_id=uuid4(),context_id='test',topic='Forces',count=1,question_formats=['mcq'])
            llm=SimpleNamespace(ainvoke=AsyncMock(return_value=AssessmentDesign(title='Wrong outline',
                sections=[dict(title='Questions',questions=[dict(number=1,parts=parts)])])))
            with self.assertRaises(AppError) as error:
                asyncio.run(design_assessment(llm,request,[],None))
            self.assertEqual(error.exception.code,'ASSESSMENT_INVALID_GENERATION')

    def test_simple_grading_uses_equal_internal_weights_for_shorthand_parts(self):
        import asyncio
        from unittest.mock import AsyncMock
        from app.langchain.assessment_design import design_assessment
        from app.assessments.schemas import AssessmentDesign
        request=GenerationRequest(client_request_id=uuid4(),context_id='test',topic='Reasoning',
            count=2,question_format='written',result_style='grade')
        llm=SimpleNamespace(ainvoke=AsyncMock(return_value=AssessmentDesign(title='Review',
            sections=[dict(title='Reasoning',question_count=2,part_marks=[5,10])])))
        plan,_=asyncio.run(design_assessment(llm,request,[],None))
        self.assertEqual(len(plan),4)
        self.assertTrue(all(part['marks']==1 for part in plan))

    def test_bare_request_requires_no_configuration(self):
        value = AssessmentIntent(client_request_id=uuid4(), context_id='', topic='')
        self.assertIsNone(value.topic)
        self.assertIsNone(value.context_id)
        self.assertIsNone(value.count)
        self.assertEqual(GeneratePractice().question_format,'auto')


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires isolated test database')
class AssessmentIntentTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_practice_target_survives_generation_and_foreign_target_is_rejected_before_queue(self):
        target = self.learner.register_concept('Science: exact motion')
        self.learner.link_context_concept(self.owner, self.context.context_id, target.id)
        value, _ = await self.finish(AssessmentIntent(client_request_id=uuid4(), context_id=self.context.context_id,
            topic='Motion', concept_ids=[target.id], question_format='mcq', count=3, purpose='verification'))
        self.assertEqual(value.purpose, 'verification')
        self.assertTrue(all(question.concept_ids == [target.id] for question in value.questions))
        with self.assertRaises(AppError):
            await self.service.queue_generation(self.owner, AssessmentIntent(client_request_id=uuid4(),
                context_id=self.context.context_id, concept_ids=[uuid4()], topic='Foreign', count=3))

    setUp = flexible.FlexibleEngineTests.setUp

    async def finish(self, intent, owner=None):
        owner = owner or self.owner
        job = await self.service.queue_generation(owner,intent)
        await AssessmentGenerationWorker(self.service).run_once()
        result = self.service.generation_jobs.get(owner,job['id'])
        self.assertEqual(result['state'],'completed',result)
        return self.service.repository.detail(owner,result['result']['id']),job

    async def test_simple_form_uses_shared_selection_and_enforces_each_format(self):
        calls = []
        invoke = self.service.workflows.llm.ainvoke
        async def capture(source, payload, **kwargs):
            calls.append((source.value,payload))
            value = await invoke(source,payload,**kwargs)
            if source.value == 'assessment_selection':
                value.level = 'secondary'
                value.result_style = 'feedback'
            return value
        with patch.object(self.service.workflows.llm, 'ainvoke', side_effect=capture):
            value, job = await self.finish(AssessmentIntent(client_request_id=uuid4(),
                topic='Requested forces', count=4, question_formats=['mcq','short_answer'],
                instructions='Everyday examples; feedback without marks.'))
        self.assertEqual(value.preferences.result_style, 'feedback')
        self.assertEqual(value.preferences.level, 'secondary')
        self.assertEqual(len(value.questions),4)
        self.assertEqual({q.question_type for q in value.questions}, {'mcq','short_answer'})
        self.assertEqual(sum(source == 'assessment_selection' for source,_ in calls),1)
        self.assertEqual(sum(source == 'assessment_design' for source,_ in calls),1)
        with self.db.sessions() as session:
            saved = session.execute(select(generation_jobs).where(generation_jobs.c.id == job['id'])).mappings().one()
        self.assertEqual(saved['progress']['resolved_request']['question_formats'], ['mcq','short_answer'])

    async def test_bare_request_uses_owned_learning_data(self):
        await self.learner.resolve_generated_concepts(GeneratedConceptsRequest(learner_id=self.owner,
            context_id=self.context.context_id,topic='Flexible science',labels=['Science: force and motion'],permissive=True))
        value,job = await self.finish(AssessmentIntent(client_request_id=uuid4()))
        self.assertEqual(value.context_id,self.context.context_id)
        self.assertEqual(len(value.questions),4)
        with self.db.sessions() as session:
            saved=session.execute(select(generation_jobs).where(generation_jobs.c.id==job['id'])).mappings().one()
        self.assertIn('resolved_request',saved['progress'])
        self.assertIn('force and motion',saved['progress']['resolved_request']['topic'])
        self.assertNotIn('resolved_request',self.service.generation_jobs.get(self.owner,job['id']))

    async def test_cold_start_does_not_borrow_another_owners_data(self):
        value,_ = await self.finish(AssessmentIntent(client_request_id=uuid4()),self.other)
        self.assertIn('General reasoning',value.title)
        self.assertNotEqual(value.context_id,self.context.context_id)

    async def test_profile_level_is_data_and_requested_higher_level_is_allowed(self):
        profile=ProfileContext(details=ProfileDetails(education_level='primary',field_of_study='Science',
            learning_goal='Understand forces',learning_preference='concise',explanation_depth='brief'),estimates={})
        self.service.workflows.profile=SimpleNamespace(prompt_context=lambda owner:profile)
        payloads=[]
        invoke=self.service.workflows.llm.ainvoke
        async def capture(source,payload,**kwargs):
            payloads.append((source.value,payload))
            return await invoke(source,payload,**kwargs)
        intent=AssessmentIntent(client_request_id=uuid4(),topic='Quantum mechanics',count=3,
            level='graduate',result_style='grade',instructions='Give me a graduate-level assessment, without marks.')
        with patch.object(self.service.workflows.llm,'ainvoke',side_effect=capture):
            value,_=await self.finish(intent)
        self.assertEqual(value.preferences.level,'graduate')
        self.assertEqual(value.preferences.result_style,'grade')
        self.assertTrue(all(q.marks==1 for q in value.questions))
        for source,payload in payloads:
            if source in ('assessment_design','assessment_generation'):
                self.assertEqual(payload['profile']['details']['education_level'],'primary')
                self.assertEqual(payload['level'],'graduate')
                self.assertIn('learner_context',payload)
        self.assertEqual(profile.details.education_level,'primary')

    async def test_explicit_topic_structure_count_and_marks_survive_selection(self):
        intent=AssessmentIntent(client_request_id=uuid4(),context_id=self.context.context_id,topic='Requested topic',
            question_format='mock_paper',count=1,total_marks=9,duration_minutes=35,
            paper_sections=[dict(title='Case',questions=[dict(number=7,parts=[dict(path=['a','i'],marks=4),dict(path=['b'],marks=5)])])])
        value,_=await self.finish(intent)
        self.assertEqual(value.paper.total_marks,9)
        self.assertEqual(value.paper.duration_minutes,35)
        self.assertEqual([(q.number,q.part,q.marks) for q in value.questions],[(7,'a.i',4),(7,'b',5)])

    async def test_selector_rejects_foreign_context_without_writing_it(self):
        invoke=self.service.workflows.llm.ainvoke
        async def foreign(source,payload,**kwargs):
            result=await invoke(source,payload,**kwargs)
            if source.value=='assessment_selection': result.context_id='foreign-context'
            return result
        with patch.object(self.service.workflows.llm,'ainvoke',side_effect=foreign):
            with self.assertRaises(AppError):
                await resolve_assessment_intent(self.service.workflows,self.owner,AssessmentIntent(client_request_id=uuid4()))

    async def test_retry_keeps_the_selected_topic_without_rerunning_selection(self):
        invoke=self.service.workflows.llm.ainvoke
        original=self.service.workflows.generate
        selections=[]
        failed=[False]
        async def capture(source,payload,**kwargs):
            if source.value=='assessment_selection': selections.append(payload)
            return await invoke(source,payload,**kwargs)
        async def interrupt(*args,**kwargs):
            if not failed[0]: failed[0]=True; raise RuntimeError('synthetic interruption')
            return await original(*args,**kwargs)
        job=await self.service.queue_generation(self.owner,AssessmentIntent(client_request_id=uuid4()))
        worker=AssessmentGenerationWorker(self.service)
        with patch.object(self.service.workflows.llm,'ainvoke',side_effect=capture), patch.object(self.service.workflows,'generate',side_effect=interrupt):
            await worker.run_once()
            self.assertEqual(self.service.generation_jobs.get(self.owner,job['id'])['state'],'failed')
            self.service.generation_jobs.retry(self.owner,job['id'])
            await worker.run_once()
        self.assertEqual(len(selections),1)
        self.assertEqual(self.service.generation_jobs.get(self.owner,job['id'])['state'],'completed')

    async def test_chat_generation_tool_accepts_empty_arguments(self):
        conversation=str(uuid4())
        ChatRepository(self.db.sessions).begin_turn(self.owner,SendTurn(conversation_id=conversation,
            client_turn_id=uuid4(),expected_revision=0,content='Give me an assessment'))
        scope=dict(assessment_service=self.service,conversation_id=conversation,current_user_message_id=str(uuid4()),
            current_answer_text='Give me an assessment')
        tool=next(tool for tool in create_workflow_tools(self.owner,scope,ToolBudget()) if tool.name=='assessment_generate')
        result=await tool.ainvoke({})
        self.assertEqual(result['outcome'],'queued')
        self.assertEqual(scope['assessment_cards'][0]['generation_job_id'],result['generation_job_id'])

    async def test_selected_material_context_is_used_for_an_unspecified_grounded_request(self):
        self.service.workflows.rag=SimpleNamespace(assessment_materials=lambda owner, ids:[
            dict(title='Science notes',context_ids=[self.context.context_id])])
        invoke=self.service.workflows.llm.ainvoke
        async def omit_context(source,payload,**kwargs):
            result=await invoke(source,payload,**kwargs)
            if source.value=='assessment_selection': result.context_id=None
            return result
        with patch.object(self.service.workflows.llm,'ainvoke',side_effect=omit_context):
            request=await resolve_assessment_intent(self.service.workflows,self.owner,
                AssessmentIntent(client_request_id=uuid4(),grounded=True,document_ids=['approved-material']))
        self.assertEqual(request.context_id,self.context.context_id)
        self.assertEqual(request.document_ids,['approved-material'])
