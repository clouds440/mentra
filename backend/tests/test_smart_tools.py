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
from app.history_management.events.capture import event_candidate
from app.langchain.assessment_workflows import AssessmentWorkflows
from app.langchain.history_orchestration import tool_reply
from app.langchain.planning import plan_request
from app.langchain.prompts import PromptSource
from app.langchain.tool_selection import ToolSelection


OWNER = str(UUID(int=1))


def scope(query):
    return dict(current_user_message_id=str(UUID(int=2)), user_sequence=2,
                conversation_id=str(UUID(int=3)), current_answer_text=query,
                history_references=[], memory_references=[], context_rows=[],
                execution_plan=plan_request(query))


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_general_work_is_not_routed_by_words_inside_supplied_content(self):
        for query in ('Rewrite this text: My previous schedule changed today.',
                      'Translate this sentence: Remember my old notes.',
                      'Debug this code:\nprint("latest news")', 'Explain an event loop',
                      'Define assessment'):
            plan = plan_request(query)
            self.assertTrue(plan.direct_candidate, query)
            self.assertEqual(plan.tool_names, [], query)
            self.assertEqual([step.module for step in plan.steps], ['chat', 'profile'])

    def test_each_personal_domain_gets_relevant_tools_only(self):
        self.assertEqual(plan_request('What are my saved preferences?').tool_names, ['user_memory'])
        self.assertEqual(plan_request('Find my earlier message about fractions').tool_names, ['history_lookup'])
        self.assertEqual(plan_request('Where did we discuss fractions?').tool_names,
                         ['conversation_summary_search', 'history_lookup'])
        self.assertEqual(plan_request('Show my current learning progress').tool_names, ['get_relevant_learner_context'])
        self.assertEqual(plan_request('Explain my notes').tool_names, ['search_study_material'])
        self.assertEqual(plan_request('Research current battery chemistry').tool_names, ['web_research'])

    def test_practice_needs_only_the_generator_and_no_learner_prefetch(self):
        for query in ('Give me 1 question quiz', 'Give me a test', 'Give me one MCQ quiz on fractions',
                      'مجھے ایک سوال کا کوئز دیں', 'Mujhe fractions ka aik sawal ka quiz do',
                      'Test my understanding of fractions', 'How do I improve my English? Give me a quiz.'):
            with self.subTest(query=query):
                plan = plan_request(query)
                self.assertIn('assessment_generate', plan.tool_names)
                self.assertNotIn('event_manage', plan.tool_names)
                self.assertNotIn('learner', [step.module for step in plan.steps])
                self.assertEqual(plan.required_outcome, 'assessment')
                self.assertFalse(event_candidate(query))

    def test_explanation_editing_and_negation_do_not_require_creation(self):
        for query in ('Explain what a quiz is', 'Rewrite these quiz questions',
                      'Do not create a quiz, explain fractions', 'Write unit tests for this code',
                      'The teacher will give a quiz', 'I will practice fractions tonight'):
            self.assertIsNone(plan_request(query).required_outcome)

    def test_conversational_questions_do_not_require_or_prebind_assessments(self):
        cases = (
            "I'm a beginner. I want to learn English. Where do I start? Can you ask me a few options/questions to get started?",
            'Ask me a few questions about my goals and interests.',
            'Give me options to choose a learning path.',
            'Make a beginner learning plan for English.',
            'Help me practice algebra.',
            'Give me one ungraded question and discuss my reasoning.',
            'Ask me one MCQ, just here in chat.',
            'See if I understand fractions by talking it through.',
            'Can you ask questions about my study preferences?',
            'I need help preparing for a test. Ask about my goals first.',
            'Can you give me advice about my quiz?',
            'مجھے انگریزی سیکھنے کے لیے میرے مقاصد کے بارے میں سوال پوچھیں',
        )
        previous = [dict(role='assistant', metadata=dict(assessment_cards=[dict(id='previous')]))]
        for query in cases:
            for rows in ((), previous):
                with self.subTest(query=query, previous_assessment=bool(rows)):
                    plan = plan_request(query, context_rows=rows)
                    self.assertIsNone(plan.required_outcome)
                    self.assertFalse(any(name in plan.tool_names for name in
                        ('assessment_generate', 'assessment_generate_advanced', 'assessment_revise')))

    async def test_conversation_can_return_native_questions_without_assessment_service(self):
        state = scope('Ask me a few questions to choose a learning path.')
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[
            AIMessage(content='', tool_calls=[dict(name='present_choices', id='goals', args=dict(
                kind='single_choice', question='What do you want to work towards?',
                options=[dict(id='work', label='Work'), dict(id='travel', label='Travel')]))]),
            AIMessage(content='Choose what matters most to you.')]))
        reply = await tool_reply(model, [HumanMessage(content=state['current_answer_text'])],
            None, OWNER, state, (), {})
        self.assertTrue(reply.content)
        self.assertEqual(len(state['interactions']), 1)
        self.assertFalse(state.get('assessment_cards'))
        self.assertFalse(state.get('_assessment_attempted'))

    def test_agenda_is_read_only_and_combined_announcement_still_routes(self):
        self.assertEqual(plan_request('What is my agenda tomorrow?').tool_names, ['event_lookup'])
        self.assertFalse(event_candidate('What is my agenda tomorrow?'))
        query = 'My exam is tomorrow; quiz me on fractions'
        self.assertTrue(event_candidate(query))
        self.assertIn('assessment_generate', plan_request(query).tool_names)
        self.assertIn('event_manage', plan_request(query).tool_names)

    def test_explanations_about_tests_do_not_trigger_event_capture(self):
        for query in ('How do I create a quiz?', 'Explain my test results', 'My unit test failed'):
            self.assertFalse(event_candidate(query), query)
        self.assertTrue(event_candidate('I have an exam'))

    def test_completion_distinguishes_lookups_from_requested_mutations(self):
        from app.langchain.planning import fulfills_domain_attempt
        reminder = plan_request('Remind me tomorrow')
        self.assertFalse(fulfills_domain_attempt(reminder, 'events', 'event_lookup', {}, 'Remind me tomorrow'))
        self.assertTrue(fulfills_domain_attempt(reminder, 'events', 'event_manage', {}, 'Remind me tomorrow'))
        query = 'Remember that I prefer worked examples'
        memory = plan_request(query)
        self.assertFalse(fulfills_domain_attempt(memory, 'memory', 'user_memory', {'action':'recall'}, query))
        self.assertTrue(fulfills_domain_attempt(memory, 'memory', 'user_memory', {'action':'remember'}, query))

    def test_web_is_selected_when_needed_instead_of_globally(self):
        self.assertNotIn('web_search', plan_request('Explain photosynthesis').tool_names)
        self.assertIn('web_search', plan_request('Check the latest news').tool_names)
        self.assertIn('web_research', plan_request('Research current battery chemistry').tool_names)

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
        self.assertEqual(selection.active, {'assessment_lookup', 'assessment_status'})


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

    async def test_native_clarification_defers_assessment_without_forcing_generation(self):
        for first, name, arguments in (
            (False, 'present_choices', dict(kind='single_choice', question='Which topic?',
                options=[dict(id='joins', label='SQL joins'), dict(id='indexes', label='SQL indexes')])),
            (True, 'request_input', dict(kind='text_input', question='Which topic would you like to practice?',
                fields=[dict(id='topic', label='Topic')])),
            (False, 'present_choices', dict(kind='multiple_choice', question='Which areas?',
                options=[dict(id='joins', label='SQL joins'), dict(id='indexes', label='SQL indexes')])),
            (False, 'request_input', dict(kind='form', question='What should we cover?',
                fields=[dict(id='topic', label='Topic'), dict(id='goal', label='Goal')])),
        ):
            with self.subTest(tool=name, first=first):
                state = scope('Create an assessment')
                state['user_sequence'] = 1 if first else 2
                generate = AsyncMock()
                state['assessment_service'] = SimpleNamespace(generate_chat_from_topic=generate)
                from app.chat.titles import NewChatReply
                final = (AIMessage(content='', tool_calls=[dict(name='NewChatReply', id='final',
                         args=dict(content='Here is your assessment.', conversation_title='Practice setup'))])
                         if first else AIMessage(content='Here is your assessment.'))
                model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[
                    AIMessage(content='', tool_calls=[dict(name=name, args=arguments, id='clarify')]), final]))
                reply = await tool_reply(model, [HumanMessage(content=state['current_answer_text'])],
                    None, OWNER, state, (), {}, output_schema=NewChatReply if first else None)
                self.assertEqual(len(state['interactions']), 1)
                self.assertIn('below so I can continue', reply.content)
                self.assertNotIn('Here is your assessment', reply.content)
                self.assertFalse(state.get('_outcome_repaired'))
                self.assertEqual(model.ainvoke_messages.await_count, 2)
                generate.assert_not_awaited()

    async def test_static_visual_does_not_replace_requested_assessment(self):
        from app.core.exceptions import AppError
        state = scope('Create an assessment')
        state['assessment_service'] = SimpleNamespace()
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[
            AIMessage(content='', tool_calls=[dict(name='enable_workflow_tools',
                args=dict(tool_names=['present_visuals']), id='enable')]),
            AIMessage(content='', tool_calls=[dict(name='present_visuals', args=dict(question='Difficulty estimate',
                bars=[dict(label='Estimated difficulty', value=2, max=5)]), id='bars')]),
            AIMessage(content='Here is your assessment.'), AIMessage(content='Here is your assessment.')]))
        with self.assertRaises(AppError) as error:
            await tool_reply(model, [HumanMessage(content=state['current_answer_text'])], None, OWNER, state, (), {})
        self.assertEqual(error.exception.code, 'ASSESSMENT_UNAVAILABLE')

    async def test_failed_generation_cannot_be_followed_by_a_fake_prose_quiz(self):
        from app.core.exceptions import AppError
        state = scope('Give me one MCQ quiz on fractions')
        generate = AsyncMock(side_effect=AppError('ASSESSMENT_UNAVAILABLE','Practice is unavailable.',503))
        state['assessment_service'] = SimpleNamespace(generate_chat_from_topic=generate)
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[AIMessage(content='',tool_calls=[
            dict(name='assessment_generate',args=dict(topic='Fractions',count=1,question_format='mcq'),id='g')]),
            AIMessage(content='Question 1: What is half of four?')]))
        reply = await tool_reply(model,[HumanMessage(content=state['current_answer_text'])],None,OWNER,state,(),{})
        self.assertNotIn('Question 1',reply.content)
        self.assertIn('couldn’t create',reply.content)
        self.assertEqual(generate.await_count,1)

    async def test_repair_keeps_the_advanced_generator_for_explicit_marks(self):
        state = scope('Create a quiz with 10 total marks')
        state['assessment_service'] = SimpleNamespace(generate_chat_from_topic=AsyncMock(return_value=dict(
            id=str(uuid4()),assessment_id=None,assessment=dict(id=str(uuid4()),title='Ten marks',questions=[]))))
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[AIMessage(content='Here is your quiz'),
            AIMessage(content='',tool_calls=[dict(name='assessment_generate_advanced',args=dict(topic='Fractions',count=2,total_marks=10),id='g')])]))
        await tool_reply(model,[HumanMessage(content=state['current_answer_text'])],None,OWNER,state,(),{})
        names = [getattr(tool,'name','') for tool in model.ainvoke_messages.call_args_list[1].kwargs['tools']]
        self.assertIn('assessment_generate_advanced',names)
        self.assertNotIn('assessment_generate',names)
        self.assertEqual(state['assessment_service'].generate_chat_from_topic.call_args.kwargs['total_marks'],10)

    async def test_native_clarification_defers_a_lookup_without_inventing_arguments(self):
        state = scope('Find my earlier message about fractions')
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[
            AIMessage(content='',tool_calls=[dict(name='enable_workflow_tools',args=dict(tool_names=['present_choices']),id='enable')]),
            AIMessage(content='',tool_calls=[dict(name='present_choices',args=dict(kind='single_choice',question='Which discussion?',
                options=[dict(id='halves',label='Halves'),dict(id='thirds',label='Thirds')]),id='choose')]),
            AIMessage(content='I found the discussion.')]))
        reply = await tool_reply(model,[HumanMessage(content=state['current_answer_text'])],None,OWNER,state,(),{})
        self.assertEqual(len(state['interactions']),1)
        self.assertIn('Choose an option',reply.content)
        self.assertNotIn('history',state.get('_attempted_domains',set()))
        self.assertFalse(state.get('_outcome_repaired'))

    async def test_unrelated_preparation_warning_does_not_allow_a_prose_quiz(self):
        from app.core.exceptions import AppError
        state = scope('Give me one MCQ quiz on fractions')
        state['assessment_service'] = SimpleNamespace()
        state['tool_warnings'] = [dict(tool_name='profile_context',code='TOOL_TIMEOUT')]
        model = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='Question 1: Which is correct?')))
        with self.assertRaises(AppError) as error:
            await tool_reply(model,[HumanMessage(content=state['current_answer_text'])],None,OWNER,state,(),{})
        self.assertEqual(error.exception.code,'ASSESSMENT_UNAVAILABLE')

    async def test_quiz_receipt_cannot_skip_requested_external_work(self):
        state = scope('Give me 1 question quiz about the latest news')
        state['assessment_service'] = SimpleNamespace(generate_chat_from_topic=AsyncMock(return_value=dict(
            id=str(uuid4()),assessment_id=None,assessment=dict(id=str(uuid4()),title='News practice',questions=[]))))
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[AIMessage(content='',tool_calls=[
            dict(name='assessment_generate',args=dict(topic='News',count=1,question_format='mcq'),id='g')]),
            AIMessage(content='News practice')]))
        reply = await tool_reply(model,[HumanMessage(content=state['current_answer_text'])],None,OWNER,state,(),{})
        self.assertEqual(model.ainvoke_messages.await_count,2)
        self.assertIn('couldn’t complete',reply.content)
        self.assertEqual(len(state['assessment_cards']),1)

    async def test_required_lookups_across_domains_cannot_be_replaced_by_a_claim(self):
        class Query(BaseModel):
            query: str
            action: str = 'recall'
        cases=[('Check the latest news','web_search','web'),
               ('Show my agenda','event_lookup','events'),
               ('Find my earlier message about fractions','history_lookup','history'),
               ('Explain my notes','search_study_material','rag'),
               ('Find my saved preferences','user_memory','memory')]
        for query,name,domain in cases:
            with self.subTest(domain=domain):
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                result = (dict(outcome='ok', current_date=now.date().isoformat(), current_datetime=now.isoformat(),
                    reference_timezone='UTC', delivered_at=now.isoformat()) if domain == 'web'
                    else dict(outcome='ok', items=[]))
                action=AsyncMock(return_value=result)
                async def run(_action=action, **arguments):return await _action(**arguments)
                tool=StructuredTool.from_function(name=name,description='Synthetic owned lookup',args_schema=Query,coroutine=run)
                model=SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[AIMessage(content='I checked it.'),
                    AIMessage(content='',tool_calls=[dict(name=name,args=dict(query='synthetic'),id='read')]),
                    AIMessage(content='No matching results were returned.')]))
                state=scope(query)
                with patch('app.langchain.workflow_tools.create_workflow_tools',return_value=[tool]):
                    response=await tool_reply(model,[HumanMessage(content=query)],None,OWNER,state,(),{})
                self.assertEqual(response.content,'No matching results were returned.')
                self.assertEqual(action.await_count,1)
                self.assertIn(domain,state['_attempted_domains'])
                self.assertIsNone(model.ainvoke_messages.call_args_list[0].kwargs['on_delta'])

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

    async def test_repeated_text_only_quiz_fails_without_publishing_fake_success(self):
        from app.core.exceptions import AppError
        state = scope('Give me one MCQ quiz on fractions')
        state['assessment_service'] = SimpleNamespace()
        model = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='Question 1: Which is correct?')))
        with self.assertRaises(AppError) as error:
            await tool_reply(model, [HumanMessage(content=state['current_answer_text'])], None, OWNER, state, (), {})
        self.assertEqual(error.exception.code, 'ASSESSMENT_UNAVAILABLE')
        self.assertEqual(model.ainvoke_messages.await_count, 2)
        self.assertFalse(state.get('assessment_cards'))

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
            dict(name='assessment_generate', args=dict(topic='Fractions', count=1, question_format='mcq'), id='generate')])) )
        reply = await tool_reply(model, [HumanMessage(content=state['current_answer_text'])], None, OWNER, state, (), {})
        self.assertEqual(model.ainvoke_messages.await_count, 1)
        self.assertEqual(len(state['assessment_cards']), 1)
        self.assertEqual(reply.content, 'Fractions practice')
        self.assertEqual(service.generate_chat_from_topic.call_args.kwargs['delivery'], 'interactive')

    async def test_prose_cannot_replace_a_requested_quiz(self):
        state = scope('Give me one MCQ quiz on fractions')
        service = SimpleNamespace(generate_chat_from_topic=AsyncMock(return_value=dict(
            id=str(uuid4()), assessment_id=None, assessment=dict(id=str(uuid4()),title='Fractions practice', questions=[]))))
        state['assessment_service'] = service
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[
            AIMessage(content='Question 1: What is half of four?'),
            AIMessage(content='', tool_calls=[dict(name='assessment_generate',
                args=dict(topic='Fractions',count=1,question_format='mcq'),id='generate')])]))
        await tool_reply(model, [HumanMessage(content=state['current_answer_text'])], None, OWNER, state, (), {})
        self.assertEqual(model.ainvoke_messages.await_count, 2)
        self.assertTrue(state['_outcome_repaired'])
        self.assertEqual(len(state['assessment_cards']), 1)
        self.assertIsNone(model.ainvoke_messages.call_args_list[0].kwargs['on_delta'])


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
