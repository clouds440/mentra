"""Bounded LangGraph coordinator over trusted domain tools."""
import asyncio
import json
from hashlib import sha256
from .concurrent_reads import StagedRead, staging_reads, gather_reads
from .tool_cache import tool_cache_key, REVALIDATED_READS, copy_result
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
from .token_policy import count_messages as count_tokens_approximately
from app.core.config import settings
from app.core.exceptions import AppError
from app.langchain.prompts import PromptSource, get_system_prompt
from app.history_management.budgets import ToolBudget
from app.history_management.tools import create_history_tools
from pydantic import ValidationError


async def tool_reply(llm, conversation, service, owner, scope, additional_sources, context, *, output_schema=None):
    from .recovery_receipts import restore_recovery
    restore_recovery(scope)
    budget = scope.setdefault('_tool_budget', ToolBudget())
    from .activity import ActivityPublisher
    from .tool_execution import ToolExecutor, failure, remember_failure, LIFECYCLE_CODES
    from .tool_policy import DOMAINS, is_write
    from .tool_selection import ToolSelection
    publisher = scope.get('activity', ActivityPublisher())
    executor = ToolExecutor(budget, scope, publisher)
    tools = create_history_tools(service, owner, scope, budget) if service is not None else []
    if scope.get('attachment_service') is not None:
        from .attachment_tools import create_attachment_tools
        tools.extend(create_attachment_tools(scope['attachment_service'], owner, scope, budget))
    web = scope.get('web_search_service')
    if web is not None and web.enabled and owner:
        from .web_tools import create_web_tools
        tools.extend(create_web_tools(web, owner, scope, budget))
        now = web.envelope('ok')
        context = dict(context, web_clock=dict(current_date=now.current_date.isoformat(),
            current_datetime=now.current_datetime.isoformat(), reference_timezone=now.reference_timezone))
    domains = {tool.name: DOMAINS.get(tool.name, 'history') for tool in tools}
    parallel_reads = set()
    if scope.get('event_proposal_service') is not None and getattr(service, 'events', None) is not None:
        from .event_tools import create_event_tools
        tools.extend(create_event_tools(service.events, scope['event_proposal_service'], owner, scope, budget))
        domains.update({tool.name: 'events' for tool in tools if tool.name in ('event_lookup', 'event_manage')})
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
                if _tool.name == 'get_relevant_learner_context' and scope.get('_initial_learner_context') and arguments.get('query') == scope.get('current_answer_text') and not arguments.get('context_ids'):
                    return scope['_initial_learner_context']
                if key not in budget.cache:
                    budget.cache[key] = asyncio.create_task(_tool.ainvoke(arguments))
                try:
                    return await budget.cache[key]
                except Exception:
                    budget.cache.pop(key, None)
                    raise
            tools.append(StructuredTool.from_function(name=tool.name, description=tool.description,
                args_schema=tool.args_schema, coroutine=read))
            domains[tool.name] = 'learner'
    from .workflow_tools import create_workflow_tools
    tools.extend(create_workflow_tools(owner, scope, budget))
    from app.chat.interactions import create_interaction_tools
    tools.extend(create_interaction_tools(owner, scope, budget))
    if scope.get('stateless'):
        tools = [tool for tool in tools if not is_write(tool.name,{})]
    domains.update({tool.name: DOMAINS[tool.name] for tool in tools if tool.name in DOMAINS})
    for tool in tools:
        tool.metadata = dict(tool.metadata or {}, domain=domains.get(tool.name, 'unknown'))
    selection = ToolSelection(tools, domains, scope)
    # A supplied summary is data, not a reason to bind memory/history schemas on
    # every unrelated request. Relevant missing detail remains discoverable.
    discovery = selection.discovery()
    tools.append(discovery)
    def tool_enabled(name):
        return name == 'enable_workflow_tools' or name in selection.active
    def selected():
        return [*[tool for tool in selection.selected() if domains.get(tool.name) not in executor.outages], discovery]
    dispatch = {tool.name: tool for tool in tools}
    additional_sources = tuple(dict.fromkeys((*additional_sources, PromptSource.TOOL_RECOVERY, PromptSource.SEMANTIC_ORCHESTRATION)))
    def prompt_sources(available_tools):
        from .prompts.chat_ui import UI_TOPICS
        topics = set(scope.get('_ui_topics', ()))
        if any(getattr(tool, 'name', '') == 'present_visuals' for tool in available_tools):
            topics.add('bars')
        ui_sources = tuple(PromptSource('chat_ui_' + topic) for topic in UI_TOPICS if topic in topics)
        used = set(scope.get('_selected_operations', [])) | selection.explicit
        personal = any(domains.get(name) in ('history','memory') for name in used)
        rag = any(domains.get(name) == 'rag' for name in used) or bool(scope.get('study_sources'))
        assessment = any(domains.get(name) == 'assessment' for name in used)
        external = any(domains.get(name) == 'web' for name in used) or bool(scope.get('web_sources') or scope.get('web_searches'))
        return tuple(dict.fromkeys((*ui_sources, *additional_sources, *([PromptSource.WEB_SEARCH] if external else []), *([PromptSource.CHAT_ASSESSMENT] if assessment else []), *([PromptSource.RAG_CONTEXT] if rag else []), *([PromptSource.HISTORY_MANAGEMENT] if personal or scope['history_references'] or scope['memory_references'] else []))))
    instructions = '\n\n'.join(get_system_prompt(x) for x in (PromptSource.CHAT, *prompt_sources(selected())))
    from .token_policy import schema_tokens
    from .decision_schemas import FinishResponse
    from .task_outcomes import finalize, record_receipt, receipt_id
    answer_schema = FinishResponse
    context = dict(context, capabilities=selection.catalog)
    summary = scope.get('conversation_summary')
    if summary and summary['through_sequence'] < scope['user_sequence']:
        context['conversation_summary'] = dict(summary, state='ready')
    if scope.get('retrieval_selection'):
        selection_scope = scope['retrieval_selection']
        context['study_source_selection'] = dict(mode=selection_scope.mode, document_count=len(selection_scope.document_ids or []), context_count=len(selection_scope.context_ids or []))
    from .context_envelope import visible_context
    context.update(visible_context(scope))
    context = dict(context, history_scope=dict(current_user_message_id=scope['current_user_message_id'],
        visible_user_messages=[dict(id=x.id, excerpt=str(x.content)[:100]) for x in conversation if x.type == 'human' and x.id][-8:]))
    if scope.get('interaction_response'):
        context['interaction_response'] = scope['interaction_response']
    if scope.get('chat_assessments'):
        context['chat_assessments'] = scope['chat_assessments']
    if scope.get('assessment_attachment_ids'):
        context['assessment_answer_attachments'] = scope['assessment_attachment_ids']
    system_context = json.dumps(context, ensure_ascii=False, default=str, separators=(',', ':'))
    system_cost = count_tokens_approximately([SystemMessage(content=instructions + system_context)]) + schema_tokens(selected()) + schema_tokens([answer_schema] if answer_schema else [])
    # Reserve maximum cumulative result size plus call protocol overhead upfront;
    # trim prior exchanges once, preserving the current user question.
    image_allowance = 2048 * sum(isinstance(block, dict) and block.get('type') == 'image_url'
        for message in conversation if isinstance(message.content, list) for block in message.content)
    current_question = next((message for message in reversed(conversation) if message.type == 'human'), None)
    current_cost = count_tokens_approximately([current_question]) if current_question is not None else 0
    # Protect the latest complete artifact when it fits, independent of wording.
    # Earlier artifacts remain recoverable through owner-scoped history lookup.
    latest_artifact = next((message for message in reversed(conversation) if message.type == 'ai' and message.id), None)
    edit_source_id = latest_artifact.id if latest_artifact and count_tokens_approximately([latest_artifact]) <= 4096 else None
    edit_index = next((index for index, message in enumerate(conversation) if message.type == 'ai' and message.id == edit_source_id), None) if edit_source_id else None
    if edit_source_id and edit_index is None:
        raise AppError('CHAT_EDIT_SOURCE_REQUIRED', 'The original response is not available here. Please paste it or specify which response to revise.', 422)
    coverage = summary['through_sequence'] if summary and summary['through_sequence'] < scope['user_sequence'] else 0
    unsummarized_ids = {str(row['id']) for row in scope.get('context_rows', []) if row.get('sequence', 0) > coverage}
    unsummarized = [message for message in conversation if message.id in unsummarized_ids and message is not current_question]
    # Retain more unsummarized context while a summary is pending or failed.
    # This allowance disappears once its coverage catches up; it is not paid compaction.
    history_target = max(scope.get('history_token_budget', settings.chat_history_token_budget),
        min(4096, count_tokens_approximately(unsummarized)))
    if edit_index is not None:
        start = max(0, edit_index - 1)
        history_target = max(history_target, count_tokens_approximately(conversation[start:]))
    recent_reserve = min(history_target,
        max(0, count_tokens_approximately(conversation) - current_cost))
    minimum = system_cost + current_cost + recent_reserve + 1056
    context_ceiling = settings.chat_context_window_tokens - settings.chat_output_token_reserve - 256
    ordinary_limit = min(settings.chat_input_tokens, context_ceiling)
    recovery_limit = min(settings.chat_recovery_input_tokens, context_ceiling)
    input_limit = ordinary_limit if minimum + 600 <= ordinary_limit else max(ordinary_limit, recovery_limit)
    scope['_chat_input_limit'] = input_limit
    result_space = max(0, input_limit - system_cost - current_cost - recent_reserve - 1056)
    result_token_ceiling, result_byte_ceiling = budget.max_result_tokens, budget.max_result_bytes
    budget.max_result_tokens = min(result_token_ceiling, result_space)
    budget.max_result_bytes = min(budget.max_result_bytes, budget.max_result_tokens * 4)
    available = min(max(history_target + image_allowance, current_cost + recent_reserve),
        input_limit - system_cost - budget.max_result_tokens - 800)
    while len(conversation) > 1 and conversation[0].type != 'human':
        conversation.pop(0)
    while len(conversation) > 1 and count_tokens_approximately(conversation) > available:
        conversation.pop(0)
        while len(conversation) > 1 and conversation[0].type != 'human':
            conversation.pop(0)
    if available < count_tokens_approximately(conversation):
        raise AppError('CHAT_CONTEXT_LIMIT', 'Question, study sources and tool schemas exceed the model context budget.', 422)
    scope['visible_ids'] = [message.id for message in conversation if message.id]
    for artifact in context.get('visible_artifacts', []):
        artifact['available'] = artifact['message_id'] in scope['visible_ids']
    scope['evidence_ids'] = {message.id for message in conversation if message.type == 'human' and message.id}
    context['history_scope']['visible_user_messages'] = [x for x in context['history_scope']['visible_user_messages'] if x['id'] in scope['evidence_ids']]
    system_context = json.dumps(context, ensure_ascii=False, default=str, separators=(',', ':'))
    repairs = 0

    def admit_schemas(new_tools):
        nonlocal input_limit
        candidate_tools = [*new_tools, discovery, *([answer_schema] if answer_schema else [])]
        candidate_instructions = '\n\n'.join(get_system_prompt(x) for x in (PromptSource.CHAT, *prompt_sources(candidate_tools)))
        candidate_context = dict(context, missing_context=scope.get('tool_warnings', []))
        total = count_tokens_approximately([SystemMessage(content=candidate_instructions + json.dumps(candidate_context, ensure_ascii=False, default=str, separators=(',', ':'))), *conversation]) + schema_tokens(candidate_tools)
        # Fitting schemas alone is insufficient: discovery must leave room for
        # its receipt and a real lookup, rather than forcing the next round final.
        required = total + 1024 + min(1024, result_token_ceiling)
        if required > input_limit and required <= recovery_limit:
            input_limit = recovery_limit
            scope['_chat_input_limit'] = input_limit
        admitted = required <= input_limit
        if admitted:
            remaining = max(0, input_limit - total - 1024)
            budget.max_result_tokens = min(result_token_ceiling, budget.result_tokens + remaining)
            budget.max_result_bytes = min(result_byte_ceiling, budget.result_characters + remaining*4)
        return admitted
    scope['_admit_schemas'] = admit_schemas

    async def completed(response):
        # Structured first-turn output is buffered until validated. Only public
        # answer text enters the activity stream, never title/tool JSON.
        if (answer_schema is not None or scope.get('tool_warnings')) and scope.get('on_delta') and isinstance(response.content, str):
            for start in range(0, len(response.content), 1000):
                await scope['on_delta'](response.content[start:start+1000])
        return response

    def validate_output(arguments):
        try:
            return FinishResponse.model_validate(arguments)
        except ValidationError:
            # Only a title error can be repaired without changing semantics.
            if isinstance(arguments, dict) and arguments.get('conversation_title') is not None:
                return FinishResponse.model_validate(dict(arguments, conversation_title=None))
            raise

    async def model_round(state):
        nonlocal repairs
        iteration = state['iteration']
        if state.get('finish_decision'):
            decision = validate_output(state['finish_decision'])
            receipt = scope.get('_assessment_receipt')
            if not decision.content and receipt and receipt.get('title'):
                decision.content = ('Preparing ' if receipt['state'] == 'pending' else '') + receipt['title']
            finalize(scope, decision)
            return dict(response=decision.model_dump(mode='json'), done=True)
        # Tool results are never trimmed into orphan messages.
        from .workflow_budget import current_budget
        envelope = current_budget.get()
        results_full = budget.result_tokens > budget.max_result_tokens - 600 or budget.result_characters > budget.max_result_bytes - 1800
        final_reasons = [name for name, condition in (
            ('round_limit', iteration == 4), ('call_limit', budget.calls >= budget.max_calls),
            ('repair_limit', scope.get('_repair_exhausted', False)),
            ('repeated_failure', scope.get('_exhausted_repeat', False)),
            ('deadline', bool(envelope and envelope.remaining <= envelope.answer_reserve)),
            ('result_budget', results_full)) if condition]
        final = bool(final_reasons)
        available_tools = [] if final else selected()
        if answer_schema is not None:
            available_tools = [*available_tools, answer_schema]
        if scope.get('tool_warnings'):
            context['missing_context'] = scope['tool_warnings']
        context['action_receipts'] = [{key:task[key] for key in ('id','operation','state','job_id','job_kind') if key in task}
            for task in scope.get('_task_receipts',{}).values() if not task.get('superseded_by')]
        if scope.get('attempt',1)>1:
            context['recovery'] = dict(attempt=scope['attempt'],kind='resume' if scope.get('resume') else 'retry',
                prior_outcome=scope.get('response_outcome'))
        runtime_context = json.dumps(context, ensure_ascii=False, default=str, separators=(',', ':'))
        sources = prompt_sources(available_tools)
        round_instructions = '\n\n'.join(get_system_prompt(x) for x in (PromptSource.CHAT, *sources))
        round_cost = count_tokens_approximately([SystemMessage(content=round_instructions + runtime_context)]) + schema_tokens(available_tools)
        if round_cost + count_tokens_approximately(conversation) + 256 > input_limit:
            raise AppError('CHAT_CONTEXT_LIMIT', 'Tool execution exceeded the configured context budget.', 422)
        from app.core.logging import workflow_logger
        workflow_logger.event('model.round', round=iteration+1, tool_count=len(available_tools), schema_tokens=schema_tokens(available_tools), final_round=final, final_reasons=final_reasons,
            result_tokens_remaining=max(0, budget.max_result_tokens-budget.result_tokens),
            result_bytes_remaining=max(0, budget.max_result_bytes-budget.result_characters))
        workflow_logger.event('chat.context_budget', input_limit=input_limit, estimated_input_tokens=round_cost+count_tokens_approximately(conversation),
            summary_revision=summary['revision'] if summary else 0, recent_history_target=history_target)
        try:
            response = await llm.ainvoke_messages(PromptSource.CHAT, conversation,
                additional_sources=sources, system_context=runtime_context, tools=available_tools or None,
                **({'tool_choice': answer_schema.__name__ if final else 'required'} if answer_schema else {}),
                on_delta=None)
        except Exception as error:
            from .provider_protocol import ProviderProtocolError
            if isinstance(error, ProviderProtocolError):
                if repairs >= 1 or final:
                    raise AppError('AI_PROVIDER_ERROR', 'Mentra couldn’t finish this response. Please try again.', 502) from error
                repairs += 1
                budget.call()
                conversation.append(SystemMessage(content='The provider returned tool-control markup as plain text. No tool executed. Use native function calls with the provided schemas, or give a truthful final answer. Never print tool-control markup.'))
                await publisher.emit('protocol-repair', 'failed', 'The tool request was invalid. Correcting it once.', error_code='TOOL_PROTOCOL_INVALID')
                return dict(iteration=iteration+1, response=None, done=False, repair=True)
            from openai import BadRequestError
            unsupported = isinstance(error, NotImplementedError) or (isinstance(error, BadRequestError)
                and any(word in str(error).lower() for word in ('tools', 'function', 'tool_choice'))
                and any(word in str(error).lower() for word in ('not supported', 'unsupported', 'unknown parameter')))
            if not unsupported:
                raise
            remember_failure(scope, 'tool_binding', dict(code='TOOL_BINDING_UNAVAILABLE', reason='This model provider cannot run the requested tools. Lookups and actions remain unverified.', task_impact='optional'))
            # Providers without tool binding still support ordinary grounded chat.
            fallback_context = runtime_context + '\nAll listed domain tools are unavailable through this provider. Do not claim a lookup or action was performed.'
            if answer_schema:
                fallback_context += '\nFunction calling is unavailable. Instead return a JSON object matching this schema: ' + json.dumps(answer_schema.model_json_schema())
            response = await llm.ainvoke_messages(PromptSource.CHAT, conversation,
                additional_sources=sources, system_context=fallback_context)
        if isinstance(response, AIMessage) and response.invalid_tool_calls:
            if repairs >= 1 or final:
                raise AppError('AI_PROVIDER_ERROR', 'Mentra couldn’t finish this response. Please try again.', 502)
            repairs += 1
            budget.call()
            conversation.append(SystemMessage(content='The preceding model output had malformed function arguments and was not executed. Return valid arguments matching the provided schema, or a truthful final answer.'))
            await publisher.emit('protocol-repair', 'failed', 'The tool request was invalid. Correcting it once.', error_code='TOOL_INVALID_ARGUMENTS')
            return dict(iteration=iteration+1, response=None, done=False, repair=True)
        if not isinstance(response, AIMessage) or not response.tool_calls:
            content = getattr(response, 'content', '')
            try:
                payload = json.loads(content) if isinstance(content, str) else None
            except (ValueError, TypeError):
                payload = None
            decision = validate_output(payload) if isinstance(payload, dict) else FinishResponse(content=content if isinstance(content,str) else '')
            finalize(scope, decision)
            return dict(response=decision.model_dump(mode='json'), done=True)
        outputs = [call for call in response.tool_calls if call['name'] in ('FinishResponse', 'NewChatReply', 'DirectAnswer', 'DirectNewChatReply')]
        if outputs:
            if len(response.tool_calls) != 1:
                if len(outputs) == 1 and not outputs[0]['args'].get('content'):
                    decision = validate_output(outputs[0]['args'])
                    actions = [call for call in response.tool_calls if call not in outputs]
                    return dict(response=response.model_copy(update={'tool_calls':actions}),
                        finish_decision=decision.model_dump(mode='json'), done=False)
                if repairs >= 1 or final:
                    raise AppError('AI_PROVIDER_ERROR', 'The response mixed an answer with unfinished actions. Please retry.', 502)
                repairs += 1
                conversation.append(SystemMessage(content='No actions executed. Return only needed native tool calls OR FinishResponse; never mix finalization with pending actions.'))
                return dict(iteration=iteration+1, response=None, done=False)
            arguments = {key:value for key,value in outputs[0]['args'].items() if key not in ('general_query','needs_tools','uncertain')}
            try:
                decision = validate_output(arguments)
                finalize(scope, decision)
            except (AppError, ValidationError):
                if repairs >= 1 or final: raise
                repairs += 1
                conversation.append(SystemMessage(content='Final response validation failed. Use only actual receipt IDs and honest task outcomes. Correct the final envelope without repeating completed actions.'))
                return dict(iteration=iteration+1, response=None, done=False)
            return dict(response=decision.model_dump(mode='json'), done=True)
        if final:
            raise AppError('AI_PROVIDER_ERROR', 'The response did not finish within its tool budget. Please retry the unfinished part.', 502)
        if len(response.tool_calls) > 6:
            raise AppError('TOOL_BUDGET', 'The provider requested too many tools in one response.', 422)
        return dict(response=response, done=False)

    async def dispatch_round(state):
        nonlocal repairs
        response = state['response']
        if response is None:
            return {}  # A single bounded protocol repair uses the next model round.
        conversation.append(response)

        from langgraph.func import task
        @task
        async def durable_write(call):
            value = await invoke(call)
            return dict(value=value, runtime=runtime.capture())

        async def invoke(call):
            tool = dispatch.get(call['name'])
            if tool is None or not tool_enabled(call['name']):
                budget.call()
                code = 'TOOL_UNKNOWN' if tool is None else 'TOOL_NOT_ENABLED'
                receipt = dict(outcome='rejected', code=code, reason='Unknown capability. Use the available catalog.' if tool is None else 'This capability is not bound. Request its exact tool name through enable_workflow_tools first.', category='invalid_arguments', effect_certainty='not_started')
                from app.core.logging import workflow_logger
                public_name = call['name'] if tool is not None else 'unknown_capability'
                workflow_logger.event('tool.rejected', tool_name=public_name, error_code=code)
                await publisher.emit(call['id'][:80], 'failed', receipt['reason'], tool_name=public_name, tool_call_id=call['id'][:200], error_code=code)
                return receipt
            from .activity import current_tool_call
            token = current_tool_call.set(call.get('id'))
            try:
                # Old conversation/provider snapshots may include announcement
                # literals. Validate and remove them; new schemas omit them.
                arguments = dict(call['args'])
                from .tool_activity import LABELS
                for key, expected in (('tool_name', tool.name), ('user_message', LABELS.get(tool.name))):
                    if key in arguments:
                        if arguments.pop(key) != expected:
                            budget.call()
                            return dict(outcome='rejected', code='TOOL_INVALID_ARGUMENTS', reason='The announcement did not match the selected capability.', category='invalid_arguments', effect_certainty='not_started')
                from app.core.logging import workflow_logger
                async with workflow_logger.step('app.langchain.history_orchestration', 'tool.dispatch', input=dict(tool_name=tool.name), request=arguments) as execution:
                    write_key = sha256((tool_cache_key(tool, tool.name, arguments) + json.dumps(scope.get('resume_instruction') or '')).encode()).hexdigest()
                    committed = scope.setdefault('_committed_tool_results', {})
                    if is_write(tool.name, arguments) and write_key in committed:
                        return copy_result(committed[write_key])
                    result = await executor.execute(tool, arguments)
                    if is_write(tool.name, arguments) and isinstance(result, dict):
                        from .tool_execution import outcome_status
                        if outcome_status(result)[0] not in ('failed','degraded'):
                            committed[write_key] = copy_result(result)
                    scope.setdefault('_selected_operations', []).append(tool.name)
                    execution.response(result.payload if isinstance(result, StagedRead) else result)
                    status = result.get('outcome') if isinstance(result, dict) else None
                    from .tool_execution import outcome_status
                    execution.result(dict(domain_status=status or 'returned'),
                                     outcome_status(result)[1])
                    selection.complete(tool.name)
                    scope['direct_rejected'] = True
                    if tool.name != 'enable_workflow_tools':
                        scope['_domain_tool_used'] = True
                    return result
            finally:
                current_tool_call.reset(token)

        async def capture(call):
            token = staging_reads.set(True)
            try:
                return await invoke(call)
            except Exception as error:
                return error
            finally:
                staging_reads.reset(token)

        def independent(call):
            tool = dispatch.get(call['name'])
            return bool(tool and tool_enabled(call['name']) and not is_write(call['name'], call['args'])
                        and (call['name'] in parallel_reads or (tool.metadata or {}).get('parallel_read')))

        # Reads fetch into isolated packets. Only this loop commits references,
        # citations and result budgets; writes/discovery form ordering barriers.
        pending = {}
        materialized = {}
        for position, call in enumerate(response.tool_calls):
            reserved_bytes = reserved_tokens = 0
            if web is not None and web.enabled:
                from .web_tools import compact_receipt, packet_cost
                minimum = web.envelope('budget_exhausted', searched_at=web.clock())
                size, tokens = packet_cost(compact_receipt(minimum))
                remaining_web = sum(item['name'] in ('web_search', 'web_research') for item in response.tool_calls[position+1:])
                reserved_bytes, reserved_tokens = (size + 128) * remaining_web, (tokens + 32) * remaining_web
            scope['_web_reserved_bytes'], scope['_web_reserved_tokens'] = reserved_bytes, reserved_tokens
            history_count, memory_count = len(scope['history_references']), len(scope['memory_references'])
            evidence_before = set(scope['evidence_ids'])
            visible_before = list(scope['visible_ids'])
            read_scopes = {key: len(scope.get(key, [])) for key in ('study_sources', 'event_references', 'retrieval_warnings')}
            retrieval_before = scope.get('retrieval_status')
            retrieval_context_before = scope.get('retrieval_context_ids')
            accounted = False
            result = None
            staged_identity = None
            try:
                if position not in pending and independent(call):
                    batch = []
                    for index in range(position, len(response.tool_calls)):
                        if not independent(response.tool_calls[index]): break
                        batch.append((index,response.tool_calls[index]))
                    # Identical adjacent reads share one admitted physical call;
                    # each model call ID still receives its own result message.
                    singleflight = {}
                    waiting = []
                    for _, item in batch:
                        key = tool_cache_key(dispatch.get(item['name']), item['name'], item['args'])
                        if key not in singleflight:
                            singleflight[key] = len(waiting)
                            waiting.append(lambda item=item: capture(item))
                    values = await gather_reads(waiting)
                    for index, item in batch:
                        key = tool_cache_key(dispatch.get(item['name']), item['name'], item['args'])
                        pending[index] = values[singleflight[key]]
                if scope.get('_response_checkpoint') and is_write(call['name'], call['args']):
                    saved = await durable_write(call)
                    runtime.restore(saved['runtime'])
                    result = saved['value']
                else:
                    result = pending[position] if position in pending else await invoke(call)
                if isinstance(result, Exception):
                    raise result
                if isinstance(result, StagedRead):
                    identity = id(result)
                    staged_identity = identity
                    if identity not in materialized:
                        materialized[identity] = result.materialize()
                    result = materialized[identity]
                if isinstance(result, dict) and result.get('repeated_failure'):
                    scope['_exhausted_repeat'] = True
                if isinstance(result, dict) and result.get('code') in ('TOOL_INVALID_ARGUMENTS', 'TOOL_UNKNOWN', 'TOOL_NOT_ENABLED'):
                    if repairs >= 1:
                        scope['_repair_exhausted'] = True
                    else:
                        repairs += 1
                full_content = json.dumps(result, ensure_ascii=False, default=str, separators=(',', ':'))
                content = json.dumps(dict(result,receipt_id=receipt_id(scope,call['id'])),ensure_ascii=False,default=str,separators=(',', ':')) if isinstance(result,dict) else full_content
                if full_content in budget.delivered and call['name'] not in ('web_search', 'web_research'):
                    content = json.dumps(dict(same_result_as=budget.delivered[full_content],receipt_id=receipt_id(scope,call['id'])), separators=(',', ':'))
                try:
                    budget.consume(content, reserve_tokens=reserved_tokens, reserve_bytes=reserved_bytes)
                    accounted = True
                    if call['name'] in ('web_search', 'web_research'):
                        from .web_tools import commit_web_result
                        commit_web_result(scope, result)
                except AppError:
                    write = is_write(call['name'], call['args'])
                    from .capabilities import PRESENTATIONS
                    if not write and call['name'] not in PRESENTATIONS:
                        raise
                    # Preserve committed domain effects and validated staged UI.
                    # A compact receipt must not discard any displayed questions.
                    receipt = dict(outcome=result.get('outcome', result.get('status', 'returned')), details_omitted=True)
                    for key in ('event', 'proposal', 'memory', 'assessment'):
                        value = result.get(key)
                        if isinstance(value, dict):
                            receipt[key] = {field:value[field] for field in ('id', 'revision', 'status') if field in value}
                    for key in ('concept_id', 'candidate_id', 'id', 'draft_id', 'assessment_id', 'attempt_id', 'interaction_id'):
                        if result.get(key): receipt[key] = result[key]
                    content = json.dumps(receipt, separators=(',', ':'))
                    # Reserved by ToolBudget.call(write=True), independent of
                    # the optional large details already omitted above.
                    budget.result_characters += len(content.encode('utf-8'))
                    budget.result_tokens += count_tokens_approximately([ToolMessage(content=content, tool_call_id=call['id'])])
                    accounted = True
                budget.delivered.setdefault(full_content, call['id'])
                if not is_write(call['name'], call['args']) and call['name'] not in REVALIDATED_READS | {'web_search', 'web_research'}:
                    key = tool_cache_key(dispatch.get(call['name']), call['name'], call['args'])
                    if key in executor.results:
                        executor.results[key] = copy_result(result)
            except Exception as error:
                if isinstance(error, AppError) and error.code in LIFECYCLE_CODES:
                    raise
                if staged_identity is not None:
                    materialized.pop(staged_identity, None)
                del scope['history_references'][history_count:]
                del scope['memory_references'][memory_count:]
                scope['evidence_ids'] = evidence_before
                scope['visible_ids'] = visible_before
                if not is_write(call['name'], call['args']):
                    for key, length in read_scopes.items():
                        if key in scope:
                            del scope[key][length:]
                    if retrieval_before is None:
                        scope.pop('retrieval_status', None)
                    else:
                        scope['retrieval_status'] = retrieval_before
                    if retrieval_context_before is None:
                        scope.pop('retrieval_context_ids', None)
                    else:
                        scope['retrieval_context_ids'] = retrieval_context_before
                    key = tool_cache_key(dispatch.get(call['name']), call['name'], call['args'])
                    executor.results.pop(key, None)
                    executor.failed[key] = failure(error).model_dump()
                for key in list(budget.cache):
                    if key.startswith(('history:', 'recall:', 'study:')):
                        budget.cache.pop(key)
                receipt = failure(error, write=is_write(call['name'], call['args'])).model_dump()
                if call['name'] in ('web_search', 'web_research'):
                    scope.pop('_web_pending', None)
                    from .web_tools import dated_failure
                    receipt = dated_failure(scope, receipt)
                remember_failure(scope, call['name'], receipt)
                result = receipt
                content = json.dumps(receipt)
            # Error receipts are bounded too. Keep the minimum truthful result if
            # the optional details exhausted the ordinary result packet.
            if not accounted:
                try:
                    budget.consume(content, reserve_tokens=reserved_tokens, reserve_bytes=reserved_bytes)
                except AppError:
                    content = json.dumps(dict(outcome='unavailable', code='TOOL_BUDGET', reason='Result space exhausted. Use available evidence.', effect_certainty='unknown' if is_write(call['name'], call['args']) else 'read_only'))
                    if call['name'] in ('web_search', 'web_research'):
                        from .web_tools import dated_failure
                        content = json.dumps(dated_failure(scope, dict(code='TOOL_BUDGET')))
            record_receipt(scope, call, result if isinstance(result, dict) else json.loads(content))
            conversation.append(ToolMessage(content=content, tool_call_id=call['id'], name=call['name']))
        return dict(iteration=state['iteration']+1)

    from .graphs.tool_coordinator import coordinate
    from .workflow_budget import model_budget
    from .activity import publish_activity
    from .response_runtime import ResponseRuntime
    runtime = ResponseRuntime(conversation, scope, budget, selection, executor)
    with model_budget(), publish_activity(publisher):
        response = await coordinate(model_round, dispatch_round, checkpoint=scope.get('_response_checkpoint'),
            capture=runtime.capture, restore=runtime.restore, amendment=scope.get('resume_instruction'), validate=runtime.validate)
    decision = FinishResponse.model_validate(response) if isinstance(response,dict) else FinishResponse(content=response.content)
    finalize(scope, decision)
    return await completed(AIMessage(content=decision.content))
