"""Bounded LangGraph coordinator over trusted domain tools."""
import asyncio
import json
import re
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
    budget = scope.setdefault('_tool_budget', ToolBudget())
    from .activity import ActivityPublisher
    from .tool_execution import ToolExecutor, failure, remember_failure, LIFECYCLE_CODES
    from .tool_policy import DOMAINS, is_write, DirectAnswer, DirectNewChatReply, approved_direct
    from .tool_selection import ToolSelection
    from .planning import general_query, direct_content_safe
    publisher = scope.get('activity', ActivityPublisher())
    executor = ToolExecutor(budget, scope, publisher)
    tools = create_history_tools(service, owner, scope, budget) if service is not None else []
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
    additional_sources = tuple(dict.fromkeys((*additional_sources, PromptSource.TOOL_RECOVERY)))
    if getattr(scope.get('execution_plan'), 'edit_source_id', None):
        additional_sources = (*additional_sources, PromptSource.RESPONSE_EDIT)
    def prompt_sources(available_tools):
        from .prompts.chat_ui import UI_TOPICS
        topics = set(scope.get('_ui_topics', ()))
        if any(getattr(tool, 'name', '') == 'present_visuals' for tool in available_tools):
            topics.add('bars')
        ui_sources = tuple(PromptSource('chat_ui_' + topic) for topic in UI_TOPICS if topic in topics)
        personal = any(domains.get(getattr(tool, 'name', '')) in ('history', 'memory') for tool in available_tools)
        rag = any(domains.get(getattr(tool, 'name', '')) == 'rag' for tool in available_tools) or bool(scope.get('study_sources'))
        assessment = any(domains.get(getattr(tool, 'name', '')) == 'assessment' for tool in available_tools) or any(domains.get(name) == 'assessment' for name in selection.active) or bool(scope.get('chat_assessments'))
        external = any(domains.get(getattr(tool, 'name', '')) == 'web' for tool in available_tools) or bool(scope.get('web_sources') or scope.get('web_searches'))
        return tuple(dict.fromkeys((*ui_sources, *additional_sources, *([PromptSource.WEB_SEARCH] if external else []), *([PromptSource.CHAT_ASSESSMENT] if assessment else []), *([PromptSource.RAG_CONTEXT] if rag else []), *([PromptSource.HISTORY_MANAGEMENT] if personal or scope['history_references'] or scope['memory_references'] else []))))
    instructions = '\n\n'.join(get_system_prompt(x) for x in (PromptSource.CHAT, *prompt_sources(selected())))
    from .token_policy import schema_tokens
    plan = scope.get('execution_plan')
    required_outcome = getattr(plan, 'required_outcome', None)
    initial_cards = len(scope.get('assessment_cards', []))
    initial_interactions = len(scope.get('interactions', []))
    def missing_assessment():
        return required_outcome == 'assessment' and len(scope.get('assessment_cards', [])) <= initial_cards
    def check_completion(response, iteration, final):
        attempted = scope.get('_attempted_domains', set())
        required = set(getattr(plan, 'required_domains', []))
        if scope.get('_captured_events'):
            required.discard('events')
        missing = required - attempted
        pending_input = [card for card in scope.get('interactions', [])[initial_interactions:]
                         if card.get('kind') in ('single_choice', 'multiple_choice', 'text_input', 'form', 'questionnaire')]
        if (missing or missing_assessment()) and pending_input and not (
                missing_assessment() and scope.get('_assessment_attempted')):
            # A native clarification defers assessment creation just as it
            # defers a lookup. Static visuals and old cards are not a request
            # for input, and a failed generation still needs its honest receipt.
            content = ('Choose an option below so I can continue with your request.'
                       if all(card['kind'] in ('single_choice', 'multiple_choice') for card in pending_input)
                       else 'Answer below so I can continue with your request.')
            return dict(response=AIMessage(content=content), done=True)
        if missing:
            candidates = [tool for tool in tools if domains.get(tool.name) in missing
                          and domains.get(tool.name) not in executor.outages
                          and tool.name in getattr(plan, 'tool_names', [])]
            binding_unavailable = any(warning.get('tool_name') == 'tool_binding' for warning in scope.get('tool_warnings', []))
            if not final and not binding_unavailable and not scope.get('_outcome_repaired') and candidates:
                if admit_schemas([*selection.selected(), *[tool for tool in candidates if tool.name not in selection.active]]):
                    scope['_outcome_repaired'] = True
                    selection.active.update(tool.name for tool in candidates)
                    selection.pending.update(tool.name for tool in candidates)
                    conversation.append(SystemMessage(content='The requested lookup or action has no execution receipt. Use the relevant bound capability, or report that it is unavailable; do not substitute an unverified answer or promise.'))
                    from app.core.logging import workflow_logger
                    workflow_logger.event('routing.outcome_repair', required_domains=sorted(missing))
                    return dict(iteration=iteration+1, response=None, done=False)
            remember_failure(scope, 'request_completion', dict(code='REQUEST_OUTCOME_INCOMPLETE',
                reason='A requested lookup or action could not be verified.',task_impact='required_for_part',effect_certainty='not_started'))
            # Preserve every completed domain card/receipt while refusing to
            # publish fabricated personal/current facts or action claims.
            return dict(response=AIMessage(content='I couldn’t complete all the requested lookups or actions. Any saved results are shown below; please try the unfinished part again.'), done=True)
        if not missing_assessment():
            return None
        if scope.get('_assessment_attempted'):
            # A failed/uncertain generation is not permission to substitute a
            # prose quiz. Keep other saved results and never retry the write.
            return dict(response=AIMessage(content='I couldn’t create the requested assessment. Please try again; any completed results are preserved below.'), done=True)
        generator = 'assessment_revise' if getattr(plan, 'assessment_edit', False) else next((name for name in getattr(plan, 'tool_names', [])
                          if name in ('assessment_generate', 'assessment_generate_advanced') and name in selection.by_name), 'assessment_generate')
        binding_unavailable = any(warning.get('tool_name') == 'tool_binding' for warning in scope.get('tool_warnings', []))
        if not final and not binding_unavailable and not scope.get('_outcome_repaired') and generator in selection.by_name:
            candidates = [*selection.selected(), *([] if generator in selection.active else [selection.by_name[generator]])]
            if not admit_schemas(candidates):
                raise AppError('CHAT_CONTEXT_LIMIT', 'This request needs a little more room for the quiz. Please shorten it and try again.', 422)
            scope['_outcome_repaired'] = True
            selection.active.add(generator)
            selection.pending.add(generator)
            # The next round budgets the real schema before invoking the model.
            conversation.append(SystemMessage(content=f'The requested assessment has not been created. Use {generator} to provide a native assessment card; a prose quiz does not complete this request.'))
            from app.core.logging import workflow_logger
            workflow_logger.event('routing.outcome_repair', required_outcome='assessment')
            return dict(iteration=iteration+1, response=None, done=False)
        raise AppError('ASSESSMENT_UNAVAILABLE', 'I couldn’t open the quiz controls. Please try again.', 503)
    direct_candidate = bool(plan and plan.direct_candidate)
    answer_schema = DirectNewChatReply if direct_candidate and output_schema else DirectAnswer if direct_candidate else output_schema
    context = dict(context, capabilities=selection.catalog)
    if scope.get('_captured_events'):
        context['event_capture'] = dict(results=scope['_captured_events'],
            guidance='Acknowledge saved events using these canonical receipts. Review pending details when needed. Offer preparation advice and ask whether practice is wanted; an event announcement alone is not a request to create an assessment. Do not recreate captured events.')
    summary = scope.get('conversation_summary')
    if summary and summary['through_sequence'] < scope['user_sequence']:
        context['conversation_summary'] = dict(summary, state='ready')
    if scope.get('retrieval_selection'):
        selection_scope = scope['retrieval_selection']
        context['study_source_selection'] = dict(mode=selection_scope.mode, document_count=len(selection_scope.document_ids or []), context_count=len(selection_scope.context_ids or []))
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
    edit_source_id = getattr(plan, 'edit_source_id', None)
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
    input_limit = settings.chat_input_tokens if minimum + 600 <= settings.chat_input_tokens else max(settings.chat_input_tokens, settings.chat_recovery_input_tokens)
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
    if edit_source_id and not any(message.id == edit_source_id for message in conversation):
        raise AppError('CHAT_CONTEXT_LIMIT', 'The complete response is too large to revise safely here. Please paste the part you want changed.', 422)
    scope['visible_ids'] = [message.id for message in conversation if message.id]
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
        if required > input_limit and required <= settings.chat_recovery_input_tokens:
            input_limit = settings.chat_recovery_input_tokens
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
            validated = answer_schema.model_validate(arguments)
            if direct_candidate and not scope.get('_domain_tool_used'):
                query = scope.get('current_answer_text', '')
                if not approved_direct(validated) or not (general_query(query) or edit_source_id) or not direct_content_safe(validated.content):
                    if len(validated.content) <= 300 and validated.content.strip().endswith('?') and direct_content_safe(validated.content):
                        return validated  # A clarification is not approval of a general answer.
                    raise AppError('DIRECT_ANSWER_REJECTED', 'The answer needs tools or clarification. Select the needed capability; do not bypass missing evidence.', 422)
            return validated
        except ValidationError:
            # A bad title must not discard an otherwise valid answer.
            content = arguments.get('content') if isinstance(arguments, dict) else None
            if isinstance(content, str) and content.strip():
                if direct_candidate and not scope.get('_domain_tool_used'):
                    # Ignore only a title error, never missing eligibility fields.
                    try:
                        direct = DirectAnswer.model_validate({key: value for key, value in arguments.items() if key != 'conversation_title'})
                    except ValidationError:
                        direct = None
                    if direct and approved_direct(direct) and (general_query(scope.get('current_answer_text', '')) or edit_source_id) and direct_content_safe(content):
                        return AIMessage(content=content)
                else:
                    return AIMessage(content=content)
            raise AppError('AI_PROVIDER_ERROR', 'Mentra couldn’t finish this response. Please try again.', 502)

    async def model_round(state):
        nonlocal repairs, answer_schema
        iteration = state['iteration']
        receipt = scope.get('_assessment_receipt')
        if (receipt and receipt.get('title') and required_outcome == 'assessment'
                and getattr(plan, 'intent', None) == 'assessment' and not scope.get('tool_warnings')
                and not getattr(plan, 'required_domains', [])
                and not re.search(r'\b(?:explain|also|why|compare|research|then|summari[sz]e|translate|list|show|calculate|search|save|remember|and (?:tell|write|draft|create|generate))\b', scope.get('current_answer_text', ''), re.I)):
            # The native card is the complete result. Its validated public title
            # supplies acknowledgment/title without paying for another model pass.
            from app.chat.titles import NewChatReply, provisional_title
            response = NewChatReply(content=receipt['title'], conversation_title=provisional_title(receipt['title'])) if output_schema else AIMessage(content=receipt['title'])
            from app.core.logging import workflow_logger
            workflow_logger.event('routing.outcome_complete', outcome_kind='assessment', state=receipt['state'], final_model_skipped=True)
            return dict(response=response, done=True)
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
        if direct_candidate and scope.get('_domain_tool_used'):
            answer_schema = output_schema
        available_tools = [] if final else selected()
        if answer_schema is not None:
            available_tools = [*available_tools, answer_schema]
        if scope.get('tool_warnings'):
            context['missing_context'] = scope['tool_warnings']
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
                on_delta=None if answer_schema or scope.get('tool_warnings') or required_outcome or getattr(plan, 'required_domains', []) else scope.get('on_delta'))
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
            unsupported = isinstance(error, (NotImplementedError, AttributeError)) or (isinstance(error, BadRequestError)
                and any(word in str(error).lower() for word in ('tools', 'function', 'tool_choice'))
                and any(word in str(error).lower() for word in ('not supported', 'unsupported', 'unknown parameter')))
            if not unsupported:
                raise
            if not direct_candidate or scope.get('_domain_tool_used'):
                remember_failure(scope, 'tool_binding', dict(code='TOOL_BINDING_UNAVAILABLE', reason='This model provider cannot run the requested tools. Lookups and actions remain unverified.', task_impact='required_for_part'))
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
            if answer_schema and isinstance(response.content, str):
                try:
                    payload = json.loads(response.content)
                except (ValueError, TypeError):
                    payload = None
                if isinstance(payload, dict):
                    try:
                        response = validate_output(payload)
                    except AppError as error:
                        if direct_candidate and error.code in ('DIRECT_ANSWER_REJECTED', 'AI_PROVIDER_ERROR') and not final and repairs < 1:
                            repairs += 1
                            budget.call()
                            scope['direct_rejected'] = True
                            conversation.append(SystemMessage(content='Direct-answer eligibility was not established. Use the capability catalog and tools or ask for clarification.'))
                            return dict(iteration=iteration+1, response=None, done=False, repair=True)
                        raise
                elif direct_candidate and not scope.get('_domain_tool_used'):
                    if final or scope.get('direct_rejected'):
                        raise AppError('AI_PROVIDER_ERROR', 'Mentra couldn’t finish this response. Please try again.', 502)
                    scope['direct_rejected'] = True
                    repairs += 1
                    budget.call()
                    conversation.append(SystemMessage(content='No-tool approval fields were missing. Select the required capability or clarify; do not treat the prior candidate as verified.'))
                    return dict(iteration=iteration+1, response=None, done=False, repair=True)
            completion = check_completion(response, iteration, final)
            return completion or dict(response=response, done=True)
        if answer_schema:
            outputs = [call for call in response.tool_calls if call['name'] == answer_schema.__name__]
            if outputs:
                if len(response.tool_calls) != 1:
                    if repairs >= 1 or final:
                        raise AppError('AI_PROVIDER_ERROR', 'Mentra couldn’t finish this response. Please try again.', 502)
                    repairs += 1
                    budget.call()
                    conversation.append(SystemMessage(content='The final answer was mixed with pending actions and nothing executed. Return only the needed tool calls or only the final answer schema.'))
                    await publisher.emit('protocol-repair', 'failed', 'The response mixed pending actions with an answer. Correcting it once.', error_code='TOOL_PROTOCOL_INVALID')
                    return dict(iteration=iteration+1, response=None, done=False)
                try:
                    validated = validate_output(outputs[0]['args'])
                    completion = check_completion(validated, iteration, final)
                    return completion or dict(response=validated, done=True)
                except AppError as error:
                    if direct_candidate and error.code in ('DIRECT_ANSWER_REJECTED', 'AI_PROVIDER_ERROR') and not final and repairs < 1:
                        repairs += 1
                        budget.call()
                        scope['direct_rejected'] = True
                        conversation.append(SystemMessage(content='Direct-answer approval failed. Use relevant tools or clarify the missing information.'))
                        return dict(iteration=iteration+1, response=None, done=False, repair=True)
                    raise
        if final:
            raise AppError('AI_PROVIDER_ERROR', 'Mentra couldn’t finish this response. Please try again.', 502)
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
                    required = bool(plan and any(step.required and step.module == domains.get(tool.name) for step in plan.steps))
                    result = await executor.execute(tool, arguments, required=required)
                    if not isinstance(result, dict) or result.get('category') != 'invalid_arguments' and result.get('code') not in ('TOOL_INVALID_ARGUMENTS', 'TOOL_UNKNOWN', 'TOOL_NOT_ENABLED'):
                        domain = domains.get(tool.name)
                        # A read in the same domain does not fulfill a requested
                        # mutation. Count a relevant attempted operation, including
                        # its honest failure/review receipt, never a different tool.
                        from .planning import fulfills_domain_attempt
                        if domain and fulfills_domain_attempt(plan, domain, tool.name, arguments, scope.get('current_answer_text', '')):
                            scope.setdefault('_attempted_domains', set()).add(domain)
                        if tool.name in ('assessment_generate', 'assessment_generate_advanced', 'assessment_revise'):
                            scope['_assessment_attempted'] = True
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
                content = json.dumps(result, ensure_ascii=False, default=str, separators=(',', ':'))
                full_content = content
                if content in budget.delivered and call['name'] not in ('web_search', 'web_research'):
                    content = json.dumps(dict(same_result_as=budget.delivered[content]), separators=(',', ':'))
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
            conversation.append(ToolMessage(content=content, tool_call_id=call['id'], name=call['name']))
        return dict(iteration=state['iteration']+1)

    from .graphs.tool_coordinator import coordinate
    from .workflow_budget import model_budget
    from .activity import publish_activity
    from .response_runtime import ResponseRuntime
    runtime = ResponseRuntime(conversation, scope, budget, selection, executor)
    with model_budget(), publish_activity(publisher):
        response = await coordinate(model_round, dispatch_round, checkpoint=scope.get('_response_checkpoint'),
            capture=runtime.capture, restore=runtime.restore, amendment=scope.get('resume_instruction'))
    return await completed(response)
