"""Bounded LangGraph coordinator over trusted domain tools."""
import asyncio
from typing import Literal
from pydantic import BaseModel, Field
import json
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
from .token_policy import count_messages as count_tokens_approximately
from app.core.config import settings
from app.core.exceptions import AppError
from app.langchain.prompts import PromptSource, get_system_prompt
from app.history_management.budgets import ToolBudget
from app.history_management.tools import create_history_tools
from pydantic import ValidationError


async def tool_reply(llm, conversation, service, owner, scope, additional_sources, context, *, output_schema=None):
    budget = ToolBudget()
    tools = create_history_tools(service, owner, scope, budget)
    parallel_reads = set()
    if scope.get('event_proposal_service') is not None and service.events is not None:
        from .event_tools import create_event_tools
        tools.extend(create_event_tools(service.events, scope['event_proposal_service'], owner, scope, budget))
    if scope.get('learner_service') is not None:
        from .learner_tools import create_learner_tools
        from langchain_core.tools import StructuredTool
        for tool in create_learner_tools(scope['learner_service'], owner):
            if tool.name == 'get_student_weaknesses':
                continue  # Same capability as get_study_recommendations.
            is_read = tool.name != 'resolve_student_concept'
            if is_read:
                parallel_reads.add(tool.name)
            async def read(_tool=tool, **arguments):
                budget.call(write=_tool.name == 'resolve_student_concept')
                if _tool.name == 'resolve_student_concept':
                    result = await _tool.ainvoke(arguments)
                    for key in list(budget.cache):
                        if key.startswith('learner:'): budget.cache.pop(key)
                    return result
                key = 'learner:' + _tool.name + json.dumps(arguments, sort_keys=True, default=str)
                if key not in budget.cache:
                    budget.cache[key] = asyncio.create_task(_tool.ainvoke(arguments))
                try:
                    return await budget.cache[key]
                except Exception:
                    budget.cache.pop(key, None)
                    raise
            tools.append(StructuredTool.from_function(name=tool.name, description=tool.description,
                args_schema=tool.args_schema, coroutine=read))
    from .workflow_tools import create_workflow_tools
    tools.extend(create_workflow_tools(owner, scope, budget))
    enabled = set(scope.get('workflow_modules', ('history', 'memory', 'learner', 'events', 'rag', 'assessment')))
    domains = dict(history_lookup='history', user_memory='memory', event_lookup='events', event_manage='events',
                   search_study_material='rag', assessment_generate='assessment', assessment_revise='assessment', assessment_question='assessment', assessment_status='assessment', assessment_answer='assessment', assessment_lookup='assessment')
    def selected():
        return [tool for tool in tools if tool.name == 'enable_workflow_tools' or domains.get(tool.name, 'learner') in enabled]
    class EnableModules(BaseModel):
        modules: list[Literal['history', 'memory', 'learner', 'events', 'rag', 'assessment']] = Field(min_length=1, max_length=3)
    async def enable(modules):
        budget.call()
        enabled.update(modules)
        return dict(outcome='enabled', modules=modules)
    # A small router permits compound requests without eagerly binding every domain.
    if scope.get('workflow_modules') is not None:
        from langchain_core.tools import StructuredTool
        tools.append(StructuredTool.from_function(name='enable_workflow_tools', args_schema=EnableModules,
            description='Enable another domain when needed for the current request. This grants no additional permissions; all tools retain server authorization.', coroutine=enable))
    if scope.get('activity') is not None:
        from .tool_activity import announced_tool
        tools = [announced_tool(tool, scope['activity']) for tool in tools]
    dispatch = {tool.name: tool for tool in tools}
    instructions = '\n\n'.join(get_system_prompt(x) for x in (PromptSource.CHAT, *additional_sources, PromptSource.HISTORY_MANAGEMENT))
    from .token_policy import schema_tokens
    tool_schema = json.dumps([tool.args_schema.model_json_schema() for tool in selected()])
    if output_schema is not None:
        tool_schema += json.dumps(output_schema.model_json_schema())
    context = dict(context, history_scope=dict(current_user_message_id=scope['current_user_message_id'],
        visible_user_messages=[dict(id=x.id, excerpt=str(x.content)[:100]) for x in conversation if x.type == 'human' and x.id][-8:]))
    if scope.get('chat_assessments'):
        context['chat_assessments'] = scope['chat_assessments']
    if scope.get('assessment_attachment_ids'):
        context['assessment_answer_attachments'] = scope['assessment_attachment_ids']
    system_context = json.dumps(context, ensure_ascii=False, default=str)
    system_cost = count_tokens_approximately([SystemMessage(content=instructions + system_context)]) + schema_tokens(selected()) + schema_tokens([output_schema] if output_schema else [])
    # Reserve maximum cumulative result size plus call protocol overhead upfront;
    # trim prior exchanges once, preserving the current user question.
    available = min(scope.get('history_token_budget', settings.chat_history_token_budget),
        settings.chat_context_window_tokens - settings.chat_output_token_reserve - system_cost - 4000)
    while len(conversation) > 1 and conversation[0].type != 'human':
        conversation.pop(0)
    while len(conversation) > 1 and count_tokens_approximately(conversation) > available:
        conversation.pop(0)
        while len(conversation) > 1 and conversation[0].type != 'human':
            conversation.pop(0)
    if available < count_tokens_approximately(conversation):
        raise AppError('CHAT_CONTEXT_LIMIT', 'Question, study sources and tool schemas exceed the model context budget.', 422)
    scope['visible_ids'] = [message.id for message in conversation if message.id]
    scope['evidence_ids'] = {message.id for message in conversation if message.type == 'human' and message.id}
    context['history_scope']['visible_user_messages'] = [x for x in context['history_scope']['visible_user_messages'] if x['id'] in scope['evidence_ids']]
    system_context = json.dumps(context, ensure_ascii=False, default=str)
    sources = (*additional_sources, PromptSource.HISTORY_MANAGEMENT)

    async def completed(response):
        # Structured first-turn output is buffered until validated. Only public
        # answer text enters the activity stream, never title/tool JSON.
        if output_schema is not None and scope.get('on_delta') and isinstance(response.content, str):
            for start in range(0, len(response.content), 1000):
                await scope['on_delta'](response.content[start:start+1000])
        return response

    def validate_output(arguments):
        try:
            return output_schema.model_validate(arguments)
        except ValidationError:
            # A bad title must not discard an otherwise valid answer.
            content = arguments.get('content') if isinstance(arguments, dict) else None
            if isinstance(content, str) and content.strip():
                return AIMessage(content=content)
            raise AppError('AI_PROVIDER_ERROR', 'The provider returned an invalid final answer.', 502)

    async def model_round(state):
        iteration = state['iteration']
        # Tool results are never trimmed into orphan messages.
        final = iteration == 4 or budget.calls >= 6
        available_tools = [] if final else selected()
        if output_schema is not None:
            available_tools = [*available_tools, output_schema]
        round_cost = count_tokens_approximately([SystemMessage(content=instructions + system_context)]) + schema_tokens(available_tools)
        if round_cost + count_tokens_approximately(conversation) + settings.chat_output_token_reserve + 256 > settings.chat_context_window_tokens:
            raise AppError('CHAT_CONTEXT_LIMIT', 'Tool execution exceeded the configured context budget.', 422)
        from app.core.logging import workflow_logger
        workflow_logger.event('model.round', round=iteration+1, tool_count=len(available_tools), final_round=final)
        try:
            response = await llm.ainvoke_messages(PromptSource.CHAT, conversation,
                additional_sources=sources, system_context=system_context, tools=available_tools or None,
                **({'tool_choice': output_schema.__name__ if final else 'required'} if output_schema else {}),
                on_delta=None if output_schema else scope.get('on_delta'))
        except Exception as error:
            from openai import BadRequestError
            unsupported = isinstance(error, (NotImplementedError, AttributeError)) or (isinstance(error, BadRequestError)
                and any(word in str(error).lower() for word in ('tools', 'function', 'tool_choice'))
                and any(word in str(error).lower() for word in ('not supported', 'unsupported', 'unknown parameter')))
            if not unsupported:
                raise
            # Providers without tool binding still support ordinary grounded chat.
            fallback_context = system_context + '\nHistory and memory tools are unavailable. Do not claim to have retrieved or saved personal information.'
            if output_schema:
                fallback_context += '\nFunction calling is unavailable. Instead return a JSON object matching this schema: ' + json.dumps(output_schema.model_json_schema())
            response = await llm.ainvoke_messages(PromptSource.CHAT, conversation,
                additional_sources=additional_sources, system_context=fallback_context)
        if isinstance(response, AIMessage) and response.invalid_tool_calls:
            raise AppError('AI_PROVIDER_ERROR', 'The provider returned malformed tool arguments. Retry this message.', 502)
        if not isinstance(response, AIMessage) or not response.tool_calls:
            if output_schema and isinstance(response.content, str):
                try:
                    payload = json.loads(response.content)
                except (ValueError, TypeError):
                    payload = None
                if isinstance(payload, dict):
                    response = validate_output(payload)
            return dict(response=response, done=True)
        if output_schema:
            outputs = [call for call in response.tool_calls if call['name'] == output_schema.__name__]
            if outputs:
                if len(response.tool_calls) != 1:
                    raise AppError('AI_PROVIDER_ERROR', 'The provider mixed a final answer with pending tools.', 502)
                return dict(response=validate_output(outputs[0]['args']), done=True)
        if final:
            raise AppError('AI_PROVIDER_ERROR', 'The provider did not produce a final answer within the tool limit.', 502)
        if len(response.tool_calls) > 6:
            raise AppError('TOOL_BUDGET', 'The provider requested too many tools in one response.', 422)
        return dict(response=response, done=False)

    async def dispatch_round(state):
        response = state['response']
        conversation.append(response)

        async def invoke(call):
            tool = dispatch.get(call['name'])
            if tool is None or (call['name'] != 'enable_workflow_tools' and domains.get(call['name'], 'learner') not in enabled):
                budget.call()
                return dict(outcome='rejected', reason='Unknown tool.')
            from .activity import current_tool_call
            token = current_tool_call.set(call.get('id'))
            try:
                from app.core.logging import workflow_logger
                async with workflow_logger.step('app.langchain.history_orchestration', 'tool.dispatch', input=dict(tool_name=tool.name)) as execution:
                    result = await tool.ainvoke(call['args'])
                    status = result.get('outcome') if isinstance(result, dict) else None
                    execution.result(dict(domain_status=status or 'returned'),
                                     'rejected' if status == 'rejected' else 'degraded' if status == 'unavailable' else 'success')
                    return result
            finally:
                current_tool_call.reset(token)

        async def capture(call):
            try:
                return await invoke(call)
            except Exception as error:
                return error

        # Only scope-independent learner reads may overlap. History, sources and
        # event tools mutate reference scope and remain ordered, as do all writes.
        # Batch adjacent reads so dependencies on earlier writes stay intact.
        pending = {}
        for position, call in enumerate(response.tool_calls):
            history_count, memory_count = len(scope['history_references']), len(scope['memory_references'])
            evidence_before = set(scope['evidence_ids'])
            visible_before = list(scope['visible_ids'])
            try:
                if position not in pending and call['name'] in parallel_reads:
                    batch = []
                    for index in range(position, len(response.tool_calls)):
                        if response.tool_calls[index]['name'] not in parallel_reads: break
                        batch.append((index,response.tool_calls[index]))
                    values = await asyncio.gather(*(capture(item) for _,item in batch))
                    pending.update({index:value for (index,_),value in zip(batch,values)})
                result = pending[position] if position in pending else await invoke(call)
                if isinstance(result, Exception):
                    raise result
                content = json.dumps(result, ensure_ascii=False, default=str, separators=(',', ':'))
                full_content = content
                if content in budget.delivered:
                    content = json.dumps(dict(same_result_as=budget.delivered[content]), separators=(',', ':'))
                try:
                    budget.consume(content)
                except AppError:
                    is_write = call['name'] in ('event_manage', 'resolve_student_concept', 'assessment_generate', 'assessment_revise', 'assessment_answer') or (
                        call['name'] == 'user_memory' and call['args'].get('action') != 'recall')
                    if not is_write:
                        raise
                    # Domain effects have committed. Always report a compact
                    # truthful receipt; never turn a saved write into unavailable.
                    receipt = dict(outcome=result.get('outcome', result.get('status', 'returned')), details_omitted=True)
                    for key in ('event', 'proposal', 'memory', 'assessment'):
                        value = result.get(key)
                        if isinstance(value, dict):
                            receipt[key] = {field:value[field] for field in ('id', 'revision', 'status') if field in value}
                    for key in ('concept_id', 'candidate_id', 'id', 'draft_id', 'assessment_id', 'attempt_id'):
                        if result.get(key): receipt[key] = result[key]
                    content = json.dumps(receipt, separators=(',', ':'))
                    # Reserved by ToolBudget.call(write=True), independent of
                    # the optional large details already omitted above.
                    budget.result_characters += len(content.encode('utf-8'))
                    budget.result_tokens += count_tokens_approximately([ToolMessage(content=content, tool_call_id=call['id'])])
                budget.delivered.setdefault(full_content, call['id'])
            except Exception as error:
                del scope['history_references'][history_count:]
                del scope['memory_references'][memory_count:]
                scope['evidence_ids'] = evidence_before
                scope['visible_ids'] = visible_before
                for key in list(budget.cache):
                    if key.startswith(('history:', 'recall:')):
                        budget.cache.pop(key)
                content = json.dumps(dict(outcome='unavailable', reason=error.message if isinstance(error, AppError) else 'Tool arguments or execution failed. Nothing is confirmed.'))
            conversation.append(ToolMessage(content=content, tool_call_id=call['id'], name=call['name']))
        return dict(iteration=state['iteration']+1)

    from .graphs.tool_coordinator import coordinate
    from .workflow_budget import model_budget
    with model_budget():
        response = await coordinate(model_round, dispatch_round)
    return await completed(response)
