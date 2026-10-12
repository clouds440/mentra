import asyncio
import json
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock, patch
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from app.core.exceptions import AppError
from app.history_management.budgets import ToolBudget
from app.langchain.activity import ActivityPublisher, publish_activity
from app.langchain.planning import plan_request, general_query
from app.langchain.tool_execution import ToolExecutor
from app.langchain.tool_selection import ToolSelection
from app.langchain.history_orchestration import tool_reply
from app.langchain.tool_policy import DirectAnswer, DirectNewChatReply
from app.langchain.workflow_budget import model_budget


class Empty(BaseModel):
    pass


def tool(name, action, domain='learner', schema=Empty):
    return StructuredTool.from_function(name=name, description='Read requested information', args_schema=schema,
                                        coroutine=action, metadata={'domain': domain})


class Trace:
    def __init__(self): self.events = []
    async def publish(self, update): self.events.append(update)


class RoutingTests(unittest.TestCase):
    def test_only_general_queries_are_candidates(self):
        for query in ('Hello', 'What can you do?', 'Explain photosynthesis', 'What is gravity?'):
            self.assertTrue(general_query(query), query)
            self.assertEqual([s.module for s in plan_request(query).steps], ['chat', 'profile'])
        for query in ('Explain my progress', 'Explain this file', 'What is the latest news?',
                      'Explain photosynthesis and create a quiz', 'Summarize pasted notes',
                      'What can you do and show my agenda?', 'And make it harder', 'Explain your current health'):
            self.assertFalse(general_query(query), query)

    def test_events_and_contextual_assessment_revision(self):
        self.assertIn('event_lookup', plan_request('When is the exam?').tool_names)
        self.assertIn('event_manage', plan_request('Remind me tomorrow').tool_names)
        plan = plan_request('And make it harder', context_rows=[dict(role='assistant', metadata={'assessment_cards': [{'id': 'draft'}]})])
        self.assertIn('assessment_revise', plan.tool_names)
        self.assertIn('assessment_generate', plan_request('Give me a test').tool_names)

    def test_explicit_sources_and_attachments_deny_general_shortcut(self):
        for options in ({'selected_sources': True}, {'attachments': True}):
            plan = plan_request('Explain photosynthesis', **options)
            self.assertFalse(plan.direct_candidate)
            self.assertTrue(any(step.required and step.module in ('rag', 'documents') for step in plan.steps))


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    def executor(self):
        self.trace, self.scope, self.budget = Trace(), {}, ToolBudget()
        return ToolExecutor(self.budget, self.scope, ActivityPublisher(self.trace))

    async def test_read_retries_without_model_and_caches_success(self):
        execute = self.executor()
        action = AsyncMock(side_effect=[TimeoutError(), {'answer': 'verified'}])
        async def invoke():
            self.budget.call()  # Domain wrappers must not double count.
            return await action()
        read = tool('read', invoke)
        with patch('app.langchain.tool_execution.asyncio.sleep', new=AsyncMock()):
            result = await execute.execute(read, {})
        self.assertEqual(result, {'answer': 'verified'})
        self.assertEqual(await execute.execute(read, {}), result)
        self.assertEqual(action.await_count, 2)
        self.assertEqual(self.budget.calls, 2)
        self.assertEqual(len({e.step_id for e in self.trace.events}), 1)
        self.assertIn('retry_wait', [e.status for e in self.trace.events])

    async def test_exhaustion_suppresses_same_dependency(self):
        execute = self.executor()
        action = AsyncMock(side_effect=AppError('LEARNER_UNAVAILABLE', 'Learning context unavailable.', 503))
        async def invoke(): return await action()
        with patch('app.langchain.tool_execution.asyncio.sleep', new=AsyncMock()), patch('app.langchain.tool_execution.workflow_logger.event') as log:
            first = await execute.execute(tool('read', invoke), {})
            repeated = await execute.execute(tool('read', invoke), {})
            sibling = await execute.execute(tool('other_read', invoke), {})
        self.assertEqual(first['attempts'], 3)
        self.assertTrue(repeated['repeated_failure'])
        self.assertTrue(sibling['repeated_failure'])
        self.assertEqual(action.await_count, 3)
        self.assertEqual(len(self.scope['tool_warnings']), 2)
        failed = [call.kwargs for call in log.call_args_list if call.args[0] == 'tool.failed']
        self.assertEqual(failed[0]['error_code'], 'LEARNER_UNAVAILABLE')
        self.assertEqual(failed[0]['attempts'], 3)
        self.assertEqual(len([call for call in log.call_args_list if call.args[0] == 'tool.retry_scheduled']), 2)
        self.assertEqual(len([call for call in log.call_args_list if call.args[0] == 'tool.exhausted_skip']), 2)

    async def test_authorization_is_not_retried_and_writes_are_unknown(self):
        execute = self.executor()
        async def forbidden(): raise AppError('FORBIDDEN', 'Not permitted.', 403)
        receipt = await execute.execute(tool('read', forbidden), {})
        self.assertEqual(receipt['category'], 'authorization')
        self.assertEqual(receipt['attempts'], 1)
        async def write(): raise TimeoutError()
        receipt = await execute.execute(tool('event_manage', write, 'events'), {})
        self.assertEqual(receipt['effect_certainty'], 'unknown')
        self.assertFalse(receipt['retryable'])
        self.assertEqual(self.budget.writes, 1)

    async def test_reporting_outage_preserves_saved_receipt(self):
        class Broken:
            async def publish(self, update): raise RuntimeError('private content must not appear')
        execute = ToolExecutor(ToolBudget(), {}, ActivityPublisher(Broken()))
        async def write(): return dict(outcome='saved', id='committed')
        self.assertEqual(await execute.execute(tool('event_manage', write), {}), dict(outcome='saved', id='committed'))

    async def test_reporting_outage_stops_repeated_reports_but_keeps_write_guard(self):
        class Broken:
            publish = AsyncMock(side_effect=RuntimeError('Reporting outage'))
            ensure_active = AsyncMock()
        sink = Broken()
        publisher = ActivityPublisher(sink)
        await publisher.emit('first', 'running', 'Preparing your answer')
        await publisher.emit('second', 'running', 'Preparing your answer')
        await publisher.ensure_active()
        self.assertEqual(sink.publish.await_count, 1)
        sink.ensure_active.assert_awaited_once()

    async def test_lifecycle_guard_prevents_write_and_propagates(self):
        class Expired:
            async def publish(self, update): pass
            async def ensure_active(self): raise AppError('CHAT_ATTEMPT_EXPIRED', 'No longer running.', 409)
        action = AsyncMock()
        async def write(): return await action()
        execute = ToolExecutor(ToolBudget(), {}, ActivityPublisher(Expired()))
        with self.assertRaises(AppError):
            await execute.execute(tool('event_manage', write), {})
        action.assert_not_awaited()

    async def test_business_failure_reports_failed_and_recovery_card_is_saved(self):
        execute = self.executor()
        async def invoke(): return dict(outcome='answer_preparation_failed', assessment_saved=True, attempt_id='attempt')
        receipt = await execute.execute(tool('assessment_answer', invoke), {})
        self.assertEqual(receipt['attempt_id'], 'attempt')
        self.assertEqual(self.trace.events[-1].status, 'failed')
        self.assertIn('assessment is saved', self.trace.events[-1].user_message)

    async def test_invalid_arguments_count_once_before_execution(self):
        class Input(BaseModel):
            identifier: str
        execute = self.executor()
        action = AsyncMock()
        async def invoke(identifier): return await action(identifier)
        receipt = await execute.execute(tool('read', invoke, schema=Input), {})
        self.assertEqual(receipt['code'], 'TOOL_INVALID_ARGUMENTS')
        self.assertEqual(self.budget.calls, 1)
        action.assert_not_awaited()

    async def test_answer_reserve_stops_optional_work(self):
        execute = self.executor()
        action = AsyncMock()
        async def invoke(): return await action()
        with model_budget() as envelope:
            envelope.answer_reserve = 151
            receipt = await execute.execute(tool('read', invoke), {})
        self.assertEqual(receipt['code'], 'TOOL_BUDGET')
        action.assert_not_awaited()

    async def test_retry_after_outside_deadline_is_not_ignored(self):
        execute = self.executor()
        error = AppError('BUSY', 'The service is busy.', 429)
        error.headers = {'retry-after':'600'}
        action = AsyncMock(side_effect=error)
        async def read(): return await action()
        with model_budget(), patch('app.langchain.tool_execution.asyncio.sleep', new=AsyncMock()) as sleep:
            receipt = await execute.execute(tool('read', read), {})
        self.assertEqual(receipt['attempts'], 1)
        sleep.assert_not_awaited()

    async def test_http_timeout_retries_and_honors_short_retry_after(self):
        import httpx
        execute = self.executor()
        response = httpx.Response(503, headers={'retry-after':'0.02'}, request=httpx.Request('GET','http://unit.invalid'))
        action = AsyncMock(side_effect=[httpx.HTTPStatusError('private', request=response.request, response=response), {'verified':True}])
        async def read(): return await action()
        with patch('app.langchain.tool_execution.asyncio.sleep', new=AsyncMock()) as sleep:
            receipt = await execute.execute(tool('read', read), {})
        self.assertEqual(receipt, {'verified':True})
        sleep.assert_awaited_once_with(.02)

    async def test_mutation_invalidates_both_read_caches_and_prefetch(self):
        execute = self.executor()
        self.scope['_initial_learner_context'] = {'old':True}
        version = 1
        async def read(): return {'version':version}
        async def write():
            nonlocal version
            version += 1
            return {'outcome':'saved'}
        read_tool = tool('get_active_learning_contexts', read)
        self.assertEqual(await execute.execute(read_tool, {}), {'version':1})
        self.budget.cache['learner:old'] = {'version':1}
        await execute.execute(tool('resolve_student_concept', write), {})
        self.assertNotIn('learner:old', self.budget.cache)
        self.assertNotIn('_initial_learner_context', self.scope)
        self.assertEqual(await execute.execute(read_tool, {}), {'version':2})

    async def test_live_assessment_status_is_not_reused_as_a_cached_snapshot(self):
        execute = self.executor()
        action = AsyncMock(side_effect=[{'state':'RUNNING'}, {'state':'GRADED'}])
        async def status(): return await action()
        status_tool = tool('assessment_status', status, 'assessment')
        self.assertEqual((await execute.execute(status_tool, {}))['state'], 'RUNNING')
        self.assertEqual((await execute.execute(status_tool, {}))['state'], 'GRADED')
        self.assertEqual(action.await_count, 2)


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_toolbox_is_available_once_under_admission_budget(self):
        async def invoke(): return {}
        selection = ToolSelection([tool('history_lookup', invoke), tool('event_lookup', invoke)], {'history_lookup':'history', 'event_lookup':'events'}, {'workflow_modules':{'chat'}})
        selection.scope['_admit_schemas'] = lambda tools: True
        result = await selection.discovery().ainvoke({'all_tools':True})
        self.assertEqual(result['newly_enabled'], ['event_lookup', 'history_lookup'])
        result = await selection.discovery().ainvoke({'all_tools':True})
        self.assertEqual(result['outcome'], 'already_enabled')
    async def test_missing_service_never_claims_enabled(self):
        async def invoke(): return {}
        selection = ToolSelection([tool('history_lookup', invoke, 'history')], {'history_lookup': 'history'}, {'workflow_modules': {'chat'}})
        result = await selection.discovery().ainvoke({'modules': ['events']})
        self.assertEqual(result['outcome'], 'unavailable')
        self.assertEqual(result['unavailable'], ['events'])
        self.assertEqual(selection.selected(), [])

    async def test_exact_discovery_prunes_used_schema_and_catalog_is_bounded(self):
        async def invoke(): return {}
        scope = {'workflow_modules': {'history'}}
        selection = ToolSelection([tool('history_lookup', invoke), tool('event_lookup', invoke)], {'history_lookup': 'history', 'event_lookup': 'events'}, scope)
        selection.complete('history_lookup')
        result = await selection.discovery().ainvoke({'tool_names': ['event_lookup']})
        self.assertEqual(result['newly_enabled'], ['event_lookup'])
        self.assertEqual([t.name for t in selection.selected()], ['event_lookup'])
        catalog = await selection.discovery().ainvoke({'catalog_only': True})
        self.assertIn('events', catalog['capabilities'])
        scope['_admit_schemas'] = lambda tools: False
        result = await selection.discovery().ainvoke({'modules': ['history']})
        self.assertEqual(result['code'], 'TOOL_SCHEMA_LIMIT')
        self.assertEqual([t.name for t in selection.selected()], ['event_lookup'])


class DirectAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def reply(self, responses, *, first=False, query='Explain photosynthesis'):
        scope = dict(current_user_message_id='question', current_answer_text=query, history_references=[], memory_references=[],
                     execution_plan=plan_request(query), workflow_modules={'chat'}, history_token_budget=4096)
        calls = []
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                calls.append(kwargs)
                return responses.pop(0)
        from app.chat.titles import NewChatReply
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=[]):
            result = await tool_reply(Model(), [HumanMessage(content=query, id='question')], SimpleNamespace(events=None), 'owner', scope, (), {}, output_schema=NewChatReply if first else None)
        return result, calls, scope

    async def test_general_answer_and_title_take_one_model_call(self):
        response = AIMessage(content='', tool_calls=[dict(name='DirectNewChatReply', id='final', args=dict(content='Plants convert light into chemical energy.', conversation_title='Photosynthesis', general_query=True, needs_tools=False, uncertain=False))])
        result, calls, scope = await self.reply([response], first=True)
        self.assertIsInstance(result, DirectNewChatReply)
        self.assertEqual(len(calls), 1)
        self.assertEqual(scope['_tool_budget'].calls, 0)
        self.assertEqual([getattr(t, 'name', getattr(t, '__name__', '')) for t in calls[0]['tools']], ['enable_workflow_tools', 'DirectNewChatReply'])
        self.assertIsNone(calls[0]['on_delta'])

    async def test_uncertain_candidate_is_rejected_and_clarification_allowed(self):
        rejected = AIMessage(content='', tool_calls=[dict(name='DirectAnswer', id='bad', args=dict(content='A speculative answer.', general_query=True, needs_tools=False, uncertain=True))])
        clarification = AIMessage(content='', tool_calls=[dict(name='DirectAnswer', id='clarify', args=dict(content='Which topic would you like explained?', general_query=False, needs_tools=True, uncertain=True))])
        result, calls, scope = await self.reply([rejected, clarification])
        self.assertTrue(scope['direct_rejected'])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.content, 'Which topic would you like explained?')

    async def test_missing_approval_cannot_be_bypassed_on_second_plain_answer(self):
        with self.assertRaises(AppError):
            await self.reply([AIMessage(content='First unapproved answer'), AIMessage(content='Second unapproved answer')])

    async def test_bad_title_preserves_only_an_approved_general_answer(self):
        response = AIMessage(content='', tool_calls=[dict(name='DirectNewChatReply', id='final', args=dict(content='Plants use light energy.', conversation_title='x' * 100, general_query=True, needs_tools=False, uncertain=False))])
        result, calls, scope = await self.reply([response], first=True)
        self.assertEqual(result.content, 'Plants use light energy.')
        self.assertEqual(len(calls), 1)
        self.assertEqual(scope['_tool_budget'].calls, 0)

    async def test_approval_fields_must_be_actual_booleans(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            DirectAnswer(content='Answer', general_query='true', needs_tools='false', uncertain='false')

    async def test_oversized_read_rolls_back_undelivered_references(self):
        scope = dict(current_user_message_id='question', history_references=[], memory_references=[], workflow_modules={'history'}, study_sources=[])
        async def read():
            scope['history_references'].append({'token':'H1'})
            scope['study_sources'].append({'token':'S1'})
            return {'content':'text ' * 20000}
        rounds = 0
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                nonlocal rounds
                rounds += 1
                if rounds == 1:
                    return AIMessage(content='', tool_calls=[dict(name='history_lookup', args={}, id='read')])
                receipt = json.loads(next(m.content for m in messages if isinstance(m, ToolMessage)))
                assert receipt['code'] == 'TOOL_BUDGET'
                return AIMessage(content='The source could not be delivered.')
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=[tool('history_lookup', read, 'history')]):
            await tool_reply(Model(), [HumanMessage(content='Recall', id='question')], SimpleNamespace(events=None), 'owner', scope, (), {})
        self.assertEqual(scope['history_references'], [])
        self.assertEqual(scope['study_sources'], [])

    async def test_read_selection_and_retry_need_only_two_model_calls(self):
        action = AsyncMock(side_effect=[TimeoutError(), {'verified': True}])
        async def read(): return await action()
        scope = dict(current_user_message_id='question', history_references=[], memory_references=[], workflow_modules={'history'})
        responses = [AIMessage(content='', tool_calls=[dict(name='history_lookup', args={}, id='read')]), AIMessage(content='A supported answer')]
        model_calls = []
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                model_calls.append(kwargs)
                return responses.pop(0)
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=[tool('history_lookup', read, 'history')]), patch('app.langchain.tool_execution.asyncio.sleep', new=AsyncMock()):
            result = await tool_reply(Model(), [HumanMessage(content='Recall', id='question')], SimpleNamespace(events=None), 'owner', scope, (), {})
        self.assertEqual(result.content, 'A supported answer')
        self.assertEqual(len(model_calls), 2)
        self.assertEqual(action.await_count, 2)

    async def test_second_invalid_argument_stops_corrections_and_finalizes(self):
        class Input(BaseModel):
            identifier: str
        action = AsyncMock()
        async def read(identifier): return await action(identifier)
        scope = dict(current_user_message_id='question', history_references=[], memory_references=[], workflow_modules={'history'})
        rounds = []
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                rounds.append(kwargs)
                if len(rounds) < 3:
                    return AIMessage(content='', tool_calls=[dict(name='history_lookup', args={'extra':len(rounds)}, id=f'read-{len(rounds)}')])
                return AIMessage(content='The required identifier is missing.')
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=[tool('history_lookup', read, 'history', Input)]):
            await tool_reply(Model(), [HumanMessage(content='Recall', id='question')], SimpleNamespace(events=None), 'owner', scope, (), {})
        action.assert_not_awaited()
        self.assertEqual(len(rounds), 3)
        self.assertIsNone(rounds[-1]['tools'])
        self.assertEqual(scope['_tool_budget'].calls, 2)

    async def test_parallel_reads_preserve_success_and_distinct_call_ids(self):
        trace = Trace()
        good, bad = AsyncMock(return_value={'verified':'context'}), AsyncMock(side_effect=TimeoutError())
        async def read_good(): return await good()
        async def read_bad(): return await bad()
        reads = [tool('get_active_learning_contexts', read_good), tool('get_relevant_learner_context', read_bad)]
        scope = dict(current_user_message_id='question', history_references=[], memory_references=[], workflow_modules={'learner'}, learner_service=Mock(), activity=ActivityPublisher(trace))
        rounds = 0
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                nonlocal rounds
                rounds += 1
                if rounds == 1:
                    return AIMessage(content='', tool_calls=[dict(name=read.name, args={}, id=f'call-{index}') for index,read in enumerate(reads)])
                receipts = {message.tool_call_id:json.loads(message.content) for message in messages if isinstance(message, ToolMessage)}
                assert receipts['call-0']['verified'] == 'context'
                assert receipts['call-1']['code'] == 'TOOL_TIMEOUT'
                return AIMessage(content='The context is verified; detailed progress was unavailable.')
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=[]), patch('app.langchain.learner_tools.create_learner_tools', return_value=reads), patch('app.langchain.tool_execution.asyncio.sleep', new=AsyncMock()):
            await tool_reply(Model(), [HumanMessage(content='Recall', id='question')], SimpleNamespace(events=None), 'owner', scope, (), {})
        self.assertEqual(rounds, 2)
        self.assertEqual(good.await_count, 1)
        self.assertEqual(bad.await_count, 3)
        self.assertEqual({event.tool_call_id for event in trace.events if event.status == 'completed'}, {'call-0'})
        self.assertEqual({event.tool_call_id for event in trace.events if event.status == 'failed'}, {'call-1'})

    async def test_identical_parallel_reads_share_one_physical_admission(self):
        action = AsyncMock(return_value={'verified':'context'})
        async def read(): return await action()
        reads = [tool('get_active_learning_contexts', read)]
        scope = dict(current_user_message_id='question', history_references=[], memory_references=[], workflow_modules={'learner'}, learner_service=Mock())
        rounds = 0
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                nonlocal rounds
                rounds += 1
                if rounds == 1:
                    return AIMessage(content='', tool_calls=[dict(name=reads[0].name, args={}, id=identifier) for identifier in ('first', 'second')])
                receipts = {message.tool_call_id:json.loads(message.content) for message in messages if isinstance(message, ToolMessage)}
                assert receipts['first']['verified'] == 'context'
                assert receipts['second']['same_result_as'] == 'first'
                return AIMessage(content='A verified context.')
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=[]), patch('app.langchain.learner_tools.create_learner_tools', return_value=reads):
            await tool_reply(Model(), [HumanMessage(content='Recall', id='question')], SimpleNamespace(events=None), 'owner', scope, (), {})
        action.assert_awaited_once()
        self.assertEqual(scope['_tool_budget'].calls, 1)


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_inaccessible_explicit_source_rejects_without_model_call(self):
        from app.langchain.orchestration_service import OrchestrationService
        from app.rag.schemas import ChatSelection
        rag = Mock()
        rag.search.side_effect = AppError('DOCUMENT_NOT_FOUND', 'Material not found.', 404)
        chat = SimpleNamespace(reply=AsyncMock())
        with self.assertRaises(AppError) as raised:
            await OrchestrationService(chat, rag=rag).chat_reply([('user', 'Explain photosynthesis')], ChatSelection(document_ids=[str(uuid4())]), 'owner')
        self.assertEqual(raised.exception.status_code, 404)
        rag.search.assert_called_once()
        chat.reply.assert_not_awaited()

    async def test_general_query_skips_all_unrelated_reads(self):
        from app.langchain.orchestration_service import OrchestrationService
        service = Mock()
        service.profile.prompt_context.return_value = SimpleNamespace(model_dump=lambda **kwargs: {'details': {'preferred_name': 'Ayesha'}})
        chat = SimpleNamespace(reply=AsyncMock(return_value='A general explanation.'))
        orchestration = OrchestrationService(chat, learner=service, rag=service, assessments=service, history=service, attachments=service)
        scope = dict(conversation_id='chat', current_user_message_id='user', context_rows=[], history_references=[], memory_references=[])
        response = await orchestration.chat_reply([('user', 'Explain photosynthesis')], None, 'owner', history_scope=scope)
        self.assertEqual(response.content, 'A general explanation.')
        service.assert_not_called()
        service.search.assert_not_called()
        service.chat.recent.assert_not_called()
        service.prompt_context.assert_not_called()
        service.get_relevant_context.assert_not_called()
        service.profile.prompt_context.assert_called_once_with('owner')
        self.assertEqual(chat.reply.call_args.kwargs['profile_context']['details']['preferred_name'], 'Ayesha')
        self.assertEqual(scope['_tool_budget'].calls, 1)

    async def test_required_document_failure_reaches_limited_answer(self):
        from app.langchain.orchestration_service import OrchestrationService
        attachments = Mock()
        attachments.extract.side_effect = AppError('DOCUMENT_UNAVAILABLE', 'The document could not be read.', 503)
        attachments.image_input.return_value = None
        chat = SimpleNamespace(reply=AsyncMock(return_value='The document content could not be verified.'))
        orchestration = OrchestrationService(chat, attachments=attachments)
        scope = dict(conversation_id='chat', current_user_message_id='user', context_rows=[], attachment_ids=['file'], history_references=[], memory_references=[])
        response = await orchestration.chat_reply([('user', 'Summarize the attached file')], None, 'owner', history_scope=scope)
        self.assertEqual(response.tool_warnings[0]['task_impact'], 'required_for_part')
        self.assertEqual(attachments.extract.call_count, 1)
        self.assertTrue(chat.reply.call_args.kwargs['recovery_context'])

    async def test_distinct_attachments_do_not_share_a_prefetch_cache_entry(self):
        from app.langchain.orchestration_service import OrchestrationService
        attachments = Mock()
        attachments.extract.side_effect = ['first content', 'second content']
        attachments.image_input.return_value = None
        attachments.context.side_effect = lambda extracted, *a, **kw: {'text':extracted}
        chat = SimpleNamespace(reply=AsyncMock(return_value='Two documents were read.'))
        scope = dict(conversation_id='chat', current_user_message_id='user', context_rows=[], attachment_ids=['first', 'second'], history_references=[], memory_references=[])
        await OrchestrationService(chat, attachments=attachments).chat_reply([('user','Compare the attached files')], None, 'owner', history_scope=scope)
        self.assertEqual(attachments.extract.call_count, 2)
        self.assertEqual(chat.reply.call_args.kwargs['document_context'], [{'text':'first content'}, {'text':'second content'}])


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_retry_is_observed_without_duplicate_retry_owner(self):
        import httpx
        from langchain_openai import ChatOpenAI
        from app.langchain.provider_activity import observe_request
        from app.langchain.provider_invocation import invoke_provider
        attempts = []
        async def transport(request):
            attempts.append(request.headers.get('x-stainless-retry-count'))
            if len(attempts) == 1:
                return httpx.Response(503, json={'error':{'message':'Transient test outage'}}, headers={'retry-after':'0.01'})
            return httpx.Response(200, json={'id':'test', 'object':'chat.completion', 'created':1, 'model':'test', 'choices':[{'index':0,'message':{'role':'assistant','content':'Recovered'},'finish_reason':'stop'}], 'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
        trace = Trace()
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport), event_hooks={'request':[observe_request]}) as client:
            model = ChatOpenAI(model='test', api_key='test-only', base_url='http://unit.invalid/v1', max_retries=2, http_async_client=client)
            with publish_activity(ActivityPublisher(trace)), model_budget():
                result = await invoke_provider(model, [HumanMessage(content='Hello')])
        self.assertEqual(result.content, 'Recovered')
        self.assertEqual(attempts, ['0','1'])
        self.assertEqual(len([event for event in trace.events if event.status == 'retry_wait']), 1)
    async def test_existing_sdk_retry_header_reports_without_a_model_call(self):
        from app.langchain.provider_activity import observe_request, provider_attempt_scope
        trace = Trace()
        token = provider_attempt_scope.set(('provider-step', 3))
        try:
            with publish_activity(ActivityPublisher(trace)):
                await observe_request(SimpleNamespace(headers={'x-stainless-retry-count': '1'}))
        finally:
            provider_attempt_scope.reset(token)
        self.assertIn('attempt 2 of 3', trace.events[0].user_message)

    async def test_model_invocation_obeys_shared_deadline(self):
        from app.langchain.provider_invocation import invoke_provider
        async def slow(messages):
            await asyncio.Event().wait()
        with model_budget() as envelope:
            envelope.deadline -= 149.99
            with self.assertRaises(TimeoutError):
                await invoke_provider(SimpleNamespace(ainvoke=slow), [])
