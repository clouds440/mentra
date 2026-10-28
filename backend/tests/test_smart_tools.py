"""Outcome, cost and discovery regressions; no provider or database required."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.assessments.schemas import GenerationRequest, GeneratedAssessmentBatch, AssessmentTargets, AssessmentDesign
from app.assessments.structure import small_practice
from testing.legacy_event_capture import event_candidate
from app.langchain.assessment_workflows import AssessmentWorkflows
from app.langchain.history_orchestration import tool_reply
from testing.legacy_keyword_policy import plan_request
from app.langchain.prompts import PromptSource
from app.langchain.tool_selection import ToolSelection


OWNER = str(UUID(int=1))


def scope(query):
    return dict(current_user_message_id=str(UUID(int=2)), user_sequence=2,
                conversation_id=str(UUID(int=3)), current_answer_text=query,
                history_references=[], memory_references=[], context_rows=[],
                execution_plan=plan_request(query))


class RoutingTests(unittest.IsolatedAsyncioTestCase):










    def test_delivery_preserves_legacy_replays(self):
        body = dict(client_request_id=uuid4(), context_id='context', topic='Fractions')
        old = GenerationRequest(**body)
        self.assertEqual(old.fingerprint_payload(), GenerationRequest(**body, delivery='interactive').fingerprint_payload())
        self.assertNotEqual(old.fingerprint_payload(), GenerationRequest(**body, delivery='written').fingerprint_payload())

    def test_ordinary_schema_omits_nested_paper_arguments_but_advanced_is_available(self):
        from app.langchain.workflow_tools import QuickPractice, GeneratePractice
        self.assertNotIn('paper_sections', QuickPractice.model_fields)
        self.assertIn('paper_sections', GeneratePractice.model_fields)
        self.assertIn('assessment_generate_advanced', plan_request('Create a quiz with 10 total marks').tool_names)

    def test_activity_exposes_only_a_validated_public_reference(self):
        from app.langchain.activity import ActivityAssessment
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ActivityAssessment(kind='draft', id=uuid4(), title='Practice', model_answer='PRIVATE')

    def test_small_path_keeps_complex_structure_in_the_designer(self):
        body = dict(client_request_id=uuid4(), context_id='context', topic='Fractions', count=1, question_format='mcq')
        self.assertTrue(small_practice(GenerationRequest(**body, instructions='Give me one MCQ on fractions.')))
        for changes in (dict(instructions='Use two parts'), dict(total_marks=10),
                        dict(instructions='Make each question worth five marks'),
                        dict(instructions='Set a time limit of 5 minutes'),
                        dict(duration_minutes=5), dict(question_format='proof'), dict(count=20)):
            self.assertFalse(small_practice(GenerationRequest(**dict(body, **changes))))


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_requested_unused_tool_survives_another_discovery(self):
        class Empty(BaseModel):
            pass
        async def run():
            return {}
        tools = [StructuredTool.from_function(name=name, description='Read', args_schema=Empty, coroutine=run)
                 for name in ('assessment_lookup', 'assessment_status')]
        selection = ToolSelection(tools, {t.name:'assessment' for t in tools},
                                  dict(execution_plan=SimpleNamespace(tool_names=[])))
        discover = selection.discovery()
        await discover.ainvoke(dict(tool_names=['assessment_lookup']))
        await discover.ainvoke(dict(tool_names=['assessment_status']))
        self.assertEqual(selection.active, {'assessment_lookup', 'assessment_status'})
        selection.complete('assessment_lookup')
        await discover.ainvoke(dict(tool_names=['assessment_status']))
        self.assertEqual(selection.active, {'assessment_status'})
        await discover.ainvoke(dict(all_tools=True))
        selection.complete('assessment_lookup')
        await discover.ainvoke(dict(tool_names=['assessment_status']))
        await discover.ainvoke(dict(all_tools=True))
        self.assertEqual(selection.active, {'assessment_status'})


class OutcomeTests(unittest.IsolatedAsyncioTestCase):
    def test_old_checkpoint_keeps_receipts_without_replaying_obsolete_routing_instructions(self):
        from langchain_core.messages import SystemMessage, ToolMessage
        from app.history_management.budgets import ToolBudget
        from app.langchain.response_runtime import ResponseRuntime
        conversation = [HumanMessage(content='Ask me about my learning goals.'),
            AIMessage(content='', tool_calls=[dict(name='present_choices', args={}, id='choices')]),
            ToolMessage(content='{"outcome":"displayed"}', tool_call_id='choices'),
            SystemMessage(content='The requested assessment has not been created. Use assessment_generate.')]
        state = dict(_tool_execution_state=dict(results={'choices':dict(outcome='displayed')}))
        runtime = ResponseRuntime(conversation, state, ToolBudget(), ToolSelection([], {}, {}), SimpleNamespace())
        snapshot = runtime.capture()
        snapshot.pop('policy_version')  # Pre-fix retained response.
        runtime.restore(snapshot)
        self.assertEqual([message.type for message in conversation], ['human', 'ai', 'tool'])
        self.assertEqual(runtime.executor.results, {'choices':dict(outcome='displayed')})
        conversation.append(SystemMessage(content='A current bounded protocol repair.'))
        runtime.restore(runtime.capture())
        self.assertEqual(conversation[-1].type, 'system')









    async def test_supplied_memory_summary_does_not_bind_unrelated_memory_tools(self):
        state=scope('Explain photosynthesis')
        captured=[]
        class Model:
            async def ainvoke_messages(self,source,messages,**kwargs):
                captured.append(kwargs)
                return AIMessage(content='',tool_calls=[dict(name='DirectAnswer',id='answer',args=dict(
                    content='Plants use light to make sugars.',general_query=True,needs_tools=False,uncertain=False))])
        await tool_reply(Model(),[HumanMessage(content=state['current_answer_text'])],SimpleNamespace(events=None),OWNER,state,(),
                         dict(memories_summary=dict(content='Prefers short explanations.',revision=1)))
        self.assertNotIn('user_memory',[getattr(t,'name','') for t in captured[0]['tools']])
        self.assertNotIn(PromptSource.HISTORY_MANAGEMENT,captured[0]['additional_sources'])


    async def test_compound_request_keeps_its_explanation_call(self):
        state = scope('Give me 1 question quiz on fractions and explain why it is useful')
        state['assessment_service'] = SimpleNamespace(generate_chat_from_topic=AsyncMock(return_value=dict(
            id=str(uuid4()),assessment_id=None,assessment=dict(id=str(uuid4()),title='Fractions practice',questions=[]))))
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[AIMessage(content='',tool_calls=[
            dict(name='assessment_generate',args=dict(topic='Fractions',count=1,question_format='mcq'),id='g')]),
            AIMessage(content='This checks whether you can compare equal portions.')]))
        reply = await tool_reply(model,[HumanMessage(content=state['current_answer_text'])],None,OWNER,state,(),{})
        self.assertEqual(model.ainvoke_messages.await_count,2)
        self.assertIn('equal portions',reply.content)

    async def test_real_card_completes_in_one_routing_call(self):
        state = scope('Give me 1 question quiz on fractions')
        service = SimpleNamespace(generate_chat_from_topic=AsyncMock(return_value=dict(
            id=str(uuid4()), assessment_id=None, assessment=dict(id=str(uuid4()),title='Fractions practice', questions=[]))))
        state['assessment_service'] = service
        model = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='', tool_calls=[
            dict(name='assessment_generate', args=dict(topic='Fractions', count=1, question_format='mcq'), id='generate'), dict(name='FinishResponse',id='finish',args=dict(content=''))])) )
        reply = await tool_reply(model, [HumanMessage(content=state['current_answer_text'])], None, OWNER, state, (), {})
        self.assertEqual(model.ainvoke_messages.await_count, 1)
        self.assertEqual(len(state['assessment_cards']), 1)
        self.assertEqual(reply.content, 'Fractions practice')
        self.assertEqual(service.generate_chat_from_topic.call_args.kwargs['delivery'], 'interactive')



class SmallWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def run_workflow(self, compact):
        calls = []
        concept = SimpleNamespace(id='concept', canonical_name='Fractions: halves')
        async def resolve(request):
            return [SimpleNamespace(id='concept', canonical_name=label) for label in request.labels]
        learner = SimpleNamespace(get_context_summaries=lambda *a: [],
            get_study_targets=lambda *a: dict(recommendations=[],verification=[]),
            get_concepts=lambda ids: {identifier:concept for identifier in ids},
            resolve_generated_concepts=resolve,
            get_relevant_context=lambda *a: SimpleNamespace(model_dump=lambda **k: dict(concepts=[])))
        class Model:
            async def ainvoke(self, source, payload, **kwargs):
                calls.append(source.value)
                if source is PromptSource.ASSESSMENT_TARGETS:
                    return AssessmentTargets(concept_names=['Fractions: halves'])
                if source is PromptSource.ASSESSMENT_DESIGN:
                    return AssessmentDesign(title='Fractions', sections=[dict(title='Practice',question_count=1,
                        question_type='mcq',part_marks=[1])])
                return GeneratedAssessmentBatch(title='Fractions', questions=[dict(prompt='What is half of four?',
                    question_type='mcq',concept_names=['Fractions: halves'],difficulty=.3,marks=1,
                    options=[dict(id='a',label='2'),dict(id='b',label='3')],correct_option_id='a',
                    model_answer='2',rubric='Award 1 mark only for a.')])
        request = GenerationRequest(client_request_id=uuid4(),context_id='context',topic='Fractions',
            count=1,question_format='mcq',instructions='Give me one MCQ on fractions.',delivery='interactive')
        workflows = AssessmentWorkflows(Model(), learner)
        with patch('app.assessments.structure.small_practice', return_value=compact):
            result, _ = await workflows.generate(OWNER, request)
        self.assertEqual(result.questions[0].concept_ids, ['concept'])
        return calls, result

    async def test_three_model_stages_become_one_without_dropping_validation(self):
        before, reference = await self.run_workflow(False)
        after, result = await self.run_workflow(True)
        self.assertEqual(before, ['assessment_targets', 'assessment_design', 'assessment_generation'])
        self.assertEqual(after, ['assessment_generation'])
        self.assertEqual(result.title, reference.title)
        self.assertEqual(result.paper, reference.paper)
        self.assertEqual(result.questions[0].model_dump(exclude={'section', 'number'}),
                         reference.questions[0].model_dump(exclude={'section', 'number'}))


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_library_scope_is_validated_without_speculative_search(self):
        from app.langchain.orchestration_service import OrchestrationService
        from app.rag.schemas import ChatSelection
        from unittest.mock import Mock
        rag=SimpleNamespace(validate_selection=Mock(return_value=dict(context_count=1,document_count=1)),search=Mock())
        chat=SimpleNamespace(reply=AsyncMock(return_value='Source-grounded response'))
        await OrchestrationService(chat,rag=rag).chat_reply([('user','Explain Newton laws')],
            ChatSelection(mode='SOURCE_SPECIFIC',document_ids=[str(uuid4())]),OWNER)
        rag.validate_selection.assert_called_once()
        rag.search.assert_not_called()

    async def test_latest_profile_affects_next_model_call_in_the_same_chat(self):
        from app.langchain.orchestration_service import OrchestrationService
        from app.langchain.chat_service import ChatService
        from app.langchain.llm import MentraLLM
        from tests.test_chat_titles import ScriptedModel
        from unittest.mock import Mock
        from app.langchain.tool_policy import DirectAnswer
        replies=[AIMessage(content='',tool_calls=[dict(name=DirectAnswer.__name__,id=f'a{i}',args=dict(
            content='A clear explanation.',general_query=True,needs_tools=False,uncertain=False))]) for i in range(2)]
        model=ScriptedModel(replies)
        details=dict(preferred_name='Before',learning_preference='balanced',explanation_depth='standard')
        profile=Mock(side_effect=lambda *a:SimpleNamespace(model_dump=lambda **k:dict(details=dict(details))))
        history=SimpleNamespace(profile=SimpleNamespace(prompt_context=profile),
            summary_context=lambda *a:(dict(state='empty',content='',revision=0),None),events=None)
        chat=ChatService(MentraLLM(SimpleNamespace(get_model=lambda:model)))
        service=OrchestrationService(chat,history=history)
        for preference in ('balanced','concise'):
            details.update(learning_preference=preference,preferred_name='After' if preference=='concise' else 'Before')
            await service.chat_reply([('user','Explain photosynthesis')],None,OWNER,history_scope=scope('Explain photosynthesis'))
        self.assertEqual(profile.call_count,2)
        self.assertIn('"preferred_name":"After"',model.calls[-1][0][0].content)
        self.assertIn('"default_word_target":100',model.calls[-1][0][0].content)
