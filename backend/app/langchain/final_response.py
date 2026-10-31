"""One bounded answer-only repair; never dispatch actions after tool closure."""
import json
from urllib.parse import quote
from pydantic import ValidationError
from openai import APIConnectionError, InternalServerError, RateLimitError
from app.core.exceptions import AppError
from app.core.logging import workflow_logger
from .decision_schemas import FinishResponse
from .prompts import PromptSource
from .provider_protocol import ProviderProtocolError
from .task_outcomes import finalize


FINAL_INSTRUCTION = ('Tool execution is closed. No more searches, discovery or actions may run. '
    'Use the evidence and receipts already returned. Return only FinishResponse, with useful supported '
    'content and honest partial/failed outcomes for anything unfinished. Do not invent image URLs, '
    'citations, facts or completed actions. A request for another tool is not a result.')


def parse_final(response, validate):
    if response is None or getattr(response, 'invalid_tool_calls', None):
        raise ValueError('invalid_final_protocol')
    calls = getattr(response, 'tool_calls', [])
    if calls:
        if len(calls) != 1 or calls[0]['name'] not in ('FinishResponse', 'NewChatReply', 'DirectAnswer', 'DirectNewChatReply'):
            raise ValueError('actions_after_tool_closure')
        return validate({key: value for key, value in calls[0]['args'].items() if key not in ('general_query', 'needs_tools', 'uncertain')})
    content = getattr(response, 'content', '')
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        payload = None
    return validate(payload) if isinstance(payload, dict) else FinishResponse(content=content if isinstance(content, str) else '')


def limited_response(scope):
    links = []
    for source in scope.get('web_sources', [])[:5]:
        # Only domain-validated public evidence becomes a fallback link.
        from app.web_search import WebSource
        try:
            item = WebSource.model_validate(source)
        except ValidationError:
            continue
        label = item.title.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('\n', ' ')
        url = quote(item.url, safe=':/?#[]@!$&\'()*+,;=%-._~')
        links.append(f'- [{label}](<{url}>)')
    content = 'I couldn’t finish the full response.'
    if links:
        content += ' Here are the sources I found:\n\n' + '\n'.join(links)
    elif any(scope.get(key) for key in ('interactions', 'assessment_cards', 'event_proposals')):
        content += ' The available items are shown below.'
    content += '\n\nYou can retry the unfinished part.'
    usable = bool(links) or any(scope.get(key) for key in ('interactions', 'assessment_cards', 'event_proposals')) or any(
        item.get('state') in ('completed', 'in_progress', 'awaiting_input') for item in scope.get('_task_receipts', {}).values())
    decision = FinishResponse(content=content, outcome='partial' if usable else 'failed')
    finalize(scope, decision)
    workflow_logger.event('model.finalization_fallback', outcome=decision.outcome, source_count=len(links))
    return decision


async def finish_only(llm, response, *, conversation, scope, sources, context, validate):
    for attempt in range(2):
        try:
            decision = parse_final(response, validate)
            if not decision.content.strip() and not any(scope.get(key) for key in ('interactions', 'assessment_cards', 'event_proposals')):
                raise ValueError('empty_final_answer')
            finalize(scope, decision)
            return decision
        except (ValueError, ValidationError, ProviderProtocolError, AppError) as error:
            if isinstance(error, AppError) and error.code not in ('CHAT_INVALID_RECEIPT', 'CHAT_MISSING_EVIDENCE'):
                raise
            if attempt:
                return limited_response(scope)
            workflow_logger.event('model.finalization_repair', error_type=type(error).__name__)
        try:
            response = await llm.ainvoke_messages(PromptSource.CHAT, conversation, additional_sources=sources,
                system_context=context + '\n' + FINAL_INSTRUCTION, tools=[FinishResponse], tool_choice='FinishResponse', on_delta=None)
        except (ProviderProtocolError, ValidationError, TimeoutError, APIConnectionError, InternalServerError, RateLimitError):
            return limited_response(scope)
        except AppError as error:
            if error.code not in ('AI_WORKFLOW_BUDGET', 'AI_CONTEXT_LIMIT', 'CHAT_CONTEXT_LIMIT', 'AI_INPUT_BUDGET'):
                raise
            return limited_response(scope)
