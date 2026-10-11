"""Thin adapter: bounded evidence, staged citations, dated reuse and public website progress."""
import json
import re
from time import monotonic
from uuid import uuid4
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from app.web_search import SearchInput, SearchResult
from app.web_search.urls import favicon_url
from .token_policy import count_messages
from .workflow_budget import current_budget
from .activity import current_publisher, current_tool_call


def compact_receipt(result):
    value = result.model_dump(mode='json')
    return {key: value[key] for key in ('outcome', 'current_date', 'current_datetime', 'reference_timezone', 'delivered_at', 'searched_at')}


def packet_cost(value):
    content = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return len(content.encode('utf-8')), count_messages([HumanMessage(content=content)])


def fit_result(result, scope, budget):
    result = result.model_copy(deep=True)
    byte_limit = min(4800, 12800 - budget.result_characters - scope.get('_web_reserved_bytes', 0))
    token_limit = min(1200, 3200 - budget.result_tokens - scope.get('_web_reserved_tokens', 0))
    had_sources = bool(result.sources)
    value = result.model_dump(mode='json', exclude_none=True)
    size, tokens = packet_cost(value)
    while result.sources and (size > byte_limit or tokens > token_limit):
        last = result.sources[-1]
        if len(last.excerpt) > 80:
            last.excerpt = last.excerpt[:max(80, len(last.excerpt)//2)]
        else:
            result.sources.pop()
        result.outcome = 'partial'
        result.reason = 'Some evidence was omitted to fit the answer budget.'
        value = result.model_dump(mode='json', exclude_none=True)
        size, tokens = packet_cost(value)
    if not result.sources and had_sources:
        result.outcome = 'budget_exhausted'
        value = compact_receipt(result)
    elif size > byte_limit or tokens > token_limit:
        value = compact_receipt(result)
    return value


def dated_failure(scope, receipt):
    service = scope.get('web_search_service')
    if service is None:
        return receipt
    if 'current_datetime' in receipt:
        value = service.refresh({key: value for key, value in receipt.items() if key in SearchResult.model_fields})
    else:
        code = receipt.get('code', '')
        outcome = 'invalid_input' if 'ARGUMENT' in code else 'budget_exhausted' if 'BUDGET' in code else 'timeout' if 'TIMEOUT' in code else 'unavailable'
        value = service.envelope(outcome)
    budget = scope.get('_tool_budget')
    return fit_result(value, scope, budget) if budget else value.model_dump(mode='json', exclude_none=True)


def commit_web_result(scope, result):
    """Called only after the coordinator admitted the exact serialized tool packet."""
    staged = scope.pop('_web_pending', None)
    if staged is not None:
        scope['web_sources'] = staged
    records = scope.setdefault('web_searches', [])
    if len(records) < 6:
        records.append({key: value for key, value in result.items() if key != 'sources'})


def create_web_tools(service, owner, scope, budget):
    scope.setdefault('_tool_budget', budget)
    cache = scope.setdefault('_web_cache', {})
    attempt_id = ':'.join(str(scope.get(key, '')) for key in ('conversation_id', 'turn_id', 'attempt'))
    if not attempt_id.strip(':'):
        attempt_id = scope.setdefault('_web_ephemeral_attempt', uuid4().hex)

    async def search(query, website=None):
        request = SearchInput(query=query, website=website)
        key = request.model_dump_json()
        if 12800 - budget.result_characters - scope.get('_web_reserved_bytes', 0) < 600 or 3200 - budget.result_tokens - scope.get('_web_reserved_tokens', 0) < 600:
            return fit_result(service.envelope('budget_exhausted', website=request.website), scope, budget)
        if key in cache:
            result = service.refresh(cache[key])
        elif scope.get('_web_physical_calls', 0) >= 2:
            result = service.envelope('budget_exhausted', website=request.website)
        else:
            scope['_web_physical_calls'] = scope.get('_web_physical_calls', 0) + 1
            envelope = current_budget.get()
            deadline = monotonic() + min(20, envelope.tool_remaining if envelope else 20)
            publisher = current_publisher.get() or scope.get('activity')
            step = current_tool_call.get() or 'web-search'
            if publisher:
                sites = [dict(domain=request.website, favicon_url=favicon_url(request.website))] if request.website else []
                await publisher.ensure_active()
                await publisher.emit(step[:76] + '-web', 'running',
                    f'Searching {request.website}' if request.website else 'Searching the web with You.com',
                    tool_name='web_search', websites=sites)
            bypass = bool(re.search(r"\b(search again|fresh search|recheck|bypass (?:the )?cache|(?:do not|don't) use (?:the )?cache)\b", scope.get('current_answer_text', ''), re.I))
            result = await service.search(request, owner=owner, attempt_id=attempt_id, deadline=deadline, bypass_cache=bypass)
            cache[key] = result.model_dump(mode='json')
            if publisher:
                sites = list({source.domain: dict(domain=source.domain, favicon_url=source.favicon_url) for source in result.sources}.values())
                status = 'completed' if result.outcome in ('ok', 'no_results') else 'degraded'
                await publisher.emit(step[:76] + '-web', status,
                    'Using recently cached web results' if result.cache_hit else 'Web search completed' if result.sources else result.reason or 'Web search completed',
                    tool_name='web_search', websites=sites)
        existing = [source.model_copy(deep=True) for source in scope.get('web_sources', [])]
        by_url = {source.url: source.token for source in existing}
        staged = []
        for source in result.sources:
            value = source.model_copy(deep=True)
            value.token = by_url.get(value.url) or f'W{len(existing) + len(staged) + 1}'
            staged.append(value)
        result = result.model_copy(update={'sources': staged})
        value = fit_result(result, scope, budget)
        if value.get('sources'):
            for source in SearchResult.model_validate(value).sources:
                existing = [item for item in existing if item.url != source.url]
                existing.append(source)
            scope['_web_pending'] = sorted(existing, key=lambda item: int(item.token[1:]))[:10]
        return value

    return [StructuredTool.from_function(name='web_search', args_schema=SearchInput,
        description='Search external knowledge only when needed for accuracy/current facts or explicitly requested. Optional website restricts results. Returns dated untrusted sources with W citation tokens; no private data in queries.', coroutine=search)]
