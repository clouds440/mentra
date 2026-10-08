"""A bounded tool loop compatible with this checkout's LangChain 0.3 APIs."""
import json
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from app.core.config import settings
from app.core.exceptions import AppError
from app.langchain.prompts import PromptSource, get_system_prompt
from app.history_management.budgets import ToolBudget
from app.history_management.tools import create_history_tools


async def tool_reply(llm, conversation, service, owner, scope, additional_sources, context):
    budget = ToolBudget()
    tools = create_history_tools(service, owner, scope, budget)
    dispatch = {tool.name: tool for tool in tools}
    instructions = '\n\n'.join(get_system_prompt(x) for x in (PromptSource.CHAT, *additional_sources, PromptSource.HISTORY_MANAGEMENT))
    tool_schema = json.dumps([tool.args_schema.model_json_schema() for tool in tools])
    context = dict(context, history_scope=dict(current_user_message_id=scope['current_user_message_id'],
        visible_user_messages=[dict(id=x.id, excerpt=str(x.content)[:100]) for x in conversation if x.type == 'human' and x.id][-8:]))
    system_context = json.dumps(context, ensure_ascii=False, default=str)
    system_cost = count_tokens_approximately([SystemMessage(content=instructions + system_context + tool_schema)])
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
    for iteration in range(5):
        # Tool results are never trimmed into orphan messages.
        if system_cost + count_tokens_approximately(conversation) + settings.chat_output_token_reserve + 256 > settings.chat_context_window_tokens:
            raise AppError('CHAT_CONTEXT_LIMIT', 'Tool execution exceeded the configured context budget.', 422)
        final = iteration == 4 or budget.calls >= 6
        try:
            response = await llm.ainvoke_messages(PromptSource.CHAT, conversation,
                additional_sources=sources, system_context=system_context, tools=None if final else tools)
        except Exception as error:
            from openai import BadRequestError
            unsupported = isinstance(error, (NotImplementedError, AttributeError)) or (isinstance(error, BadRequestError)
                and any(word in str(error).lower() for word in ('tools', 'function'))
                and any(word in str(error).lower() for word in ('not supported', 'unsupported', 'unknown parameter')))
            if not unsupported:
                raise
            # Providers without tool binding still support ordinary grounded chat.
            response = await llm.ainvoke_messages(PromptSource.CHAT, conversation,
                additional_sources=additional_sources, system_context=system_context + '\nHistory and memory tools are unavailable. Do not claim to have retrieved or saved personal information.')
        if isinstance(response, AIMessage) and response.invalid_tool_calls:
            raise AppError('AI_PROVIDER_ERROR', 'The provider returned malformed tool arguments. Retry this message.', 502)
        if not isinstance(response, AIMessage) or not response.tool_calls:
            return response
        if final:
            raise AppError('AI_PROVIDER_ERROR', 'The provider did not produce a final answer within the tool limit.', 502)
        if len(response.tool_calls) > 6:
            raise AppError('TOOL_BUDGET', 'The provider requested too many tools in one response.', 422)
        conversation.append(response)
        # Serialized dispatch avoids conflicting writes and keeps admission order
        # deterministic; retrieval itself expands windows in a single SQL query.
        for call in response.tool_calls:
            history_count, memory_count = len(scope['history_references']), len(scope['memory_references'])
            evidence_before = set(scope['evidence_ids'])
            visible_before = list(scope['visible_ids'])
            try:
                tool = dispatch.get(call['name'])
                if tool is None:
                    budget.call()
                    result = dict(outcome='rejected', reason='Unknown tool.')
                else:
                    result = await tool.ainvoke(call['args'])
                content = json.dumps(result, ensure_ascii=False, default=str, separators=(',', ':'))
                budget.consume(content)
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
    raise AppError('TOOL_BUDGET', 'Tool execution could not produce a final answer.', 502)
