"""Thin adapter: bounded evidence, staged citations, dated reuse and public website progress."""
import json
from pydantic import Field, ValidationError
from time import monotonic
from uuid import uuid4
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from app.web_search import SearchInput, SearchResult
from app.web_search.urls import favicon_url
from .token_policy import count_messages
from .workflow_budget import current_budget
from .activity import current_publisher, current_tool_call
from .concurrent_reads import project_read


class ChatSearchInput(SearchInput):
    refresh: bool = Field(default=False, description='True when the user requests a new search or fresh verification instead of cached evidence.')


def compact_receipt(result):
    value = result.model_dump(mode='json')
    return {key: value[key] for key in ('outcome', 'current_date', 'current_datetime', 'reference_timezone', 'delivered_at', 'searched_at')}


def packet_cost(value):
    content = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return len(content.encode('utf-8')), count_messages([HumanMessage(content=content)])


def fit_result(result, scope, budget):
    result = result.model_copy(deep=True)
    byte_limit = min(9000 if result.research_report else 4800, budget.max_result_bytes - budget.result_characters - scope.get('_web_reserved_bytes', 0))
    token_limit = min(2400 if result.research_report else 1200, budget.max_result_tokens - budget.result_tokens - scope.get('_web_reserved_tokens', 0))
    had_sources = bool(result.sources)
    value = result.model_dump(mode='json', exclude_none=True)
    size, tokens = packet_cost(value)
    while result.sources and (size > byte_limit or tokens > token_limit):
        last = result.sources[-1]
        if result.research_report and len(result.research_report) > 160:
            result.research_report = result.research_report[:max(160, len(result.research_report)//2)]
        elif len(last.excerpt) > 80:
            last.excerpt = last.excerpt[:max(80, len(last.excerpt)//2)]
        else:
            result.sources.pop()
        result.details_omitted = True
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


def validated_web_searches(records):
    """Keep actual search envelopes, not generic dispatch/recovery receipts."""
    valid = []
    for record in records:
        try:
            result = SearchResult.model_validate(record)
        except ValidationError:
            continue
        valid.append(result.model_dump(mode='json', exclude={'sources', 'research_report'}, exclude_none=True))
        if len(valid) == 6:
            break
    return valid


def commit_web_result(scope, result):
    """Only admitted, validated search packets can publish citations/metadata."""
    staged = scope.pop('_web_pending', None)
    records = validated_web_searches([result])
    if not records:
        # Dispatch failures are still returned to the model as tool receipts.
        # They did not execute a search and must not become public SearchResult.
        return
    if staged is not None:
        scope['web_sources'] = staged
    scope['web_searches'] = validated_web_searches([*scope.get('web_searches', []), *records])


def create_web_tools(service, owner, scope, budget, *, research=False):
    name = 'web_research' if research else 'web_search'
    cache_name = '_research_cache' if research else '_web_cache'
    calls_name = '_research_physical_calls' if research else '_web_physical_calls'
    scope.setdefault('_tool_budget', budget)
    cache = scope.setdefault(cache_name, {})
    attempt_id = ':'.join(str(scope.get(key, '')) for key in ('conversation_id', 'turn_id', 'attempt'))
    if not attempt_id.strip(':'):
        attempt_id = scope.setdefault('_web_ephemeral_attempt', uuid4().hex)

    async def fetch(query, website=None, refresh=False):
        request = SearchInput(query=query, website=website)
        key = request.model_dump_json() + (':refresh' if refresh else '')
        if budget.max_result_bytes - budget.result_characters - scope.get('_web_reserved_bytes', 0) < 600 or budget.max_result_tokens - budget.result_tokens - scope.get('_web_reserved_tokens', 0) < 600:
            return service.envelope('budget_exhausted', website=request.website).model_dump(mode='json')
        if key in cache:
            result = service.refresh(cache[key])
        elif scope.get(calls_name, 0) >= (1 if research else 2):
            result = service.envelope('budget_exhausted', website=request.website)
        else:
            scope[calls_name] = scope.get(calls_name, 0) + 1
            envelope = current_budget.get()
            timeout = 45 if research else 20
            deadline = monotonic() + min(timeout, envelope.tool_remaining if envelope else timeout)
            publisher = current_publisher.get() or scope.get('activity')
            step = current_tool_call.get() or 'web-search'
            if publisher:
                sites = [dict(domain=request.website, favicon_url=favicon_url(request.website))] if request.website else []
                await publisher.ensure_active()
                await publisher.emit(step[:76] + '-web', 'running',
                    'Researching the web with You.com' if research else f'Searching {request.website}' if request.website else 'Searching the web with You.com',
                    tool_name=name, websites=sites)
            result = await service.search(request, owner=owner, attempt_id=attempt_id, deadline=deadline, bypass_cache=refresh)
            cache[key] = result.model_dump(mode='json')
            if publisher:
                sites = list({source.domain: dict(domain=source.domain, favicon_url=source.favicon_url) for source in result.sources}.values())
                status = 'completed' if result.outcome in ('ok', 'no_results') else 'degraded'
                await publisher.emit(step[:76] + '-web', status,
                    'Using recently cached web results' if result.cache_hit else 'Web search completed' if result.sources else result.reason or 'Web search completed',
                    tool_name=name, websites=sites)
        return result.model_dump(mode='json')

    def project(payload):
        result = service.refresh(payload, within_turn=payload.get('reused_within_turn', False))
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

    async def search(query, website=None, refresh=False):
        return project_read(project, await fetch(query, website, refresh))

    tools = [StructuredTool.from_function(name=name, args_schema=ChatSearchInput,
        description=('Research a complex public question using authenticated You.com multi-step research. One call per turn; optional website restricts sources. Returns untrusted research synthesis and dated W sources; never send private data.' if research else 'Search external knowledge only when needed for accuracy/current facts or explicitly requested. Optional website restricts results. Returns dated untrusted sources with W citation tokens; no private data in queries.'), coroutine=search, metadata={'parallel_read': True})]
    extra = getattr(service, 'research', None)
    if not research and extra is not None and extra.enabled:
        tools.extend(create_web_tools(extra, owner, scope, budget, research=True))
    return tools
