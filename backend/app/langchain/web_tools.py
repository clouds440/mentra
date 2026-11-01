"""Thin adapter: bounded evidence, staged citations, dated reuse and public website progress."""
import json
from pydantic import Field, ValidationError
from time import monotonic
from uuid import uuid4
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from app.web_search import SearchInput, SearchResult
from app.web_search.schemas import WEB_SOURCE_LIMIT, WEB_SEARCH_LIMIT
from app.web_search.urls import favicon_url
from .token_policy import count_messages
from .workflow_budget import current_budget
from .activity import current_publisher, current_tool_call
from .concurrent_reads import project_read
from .web_effort import search_phase


class ChatSearchInput(SearchInput):
    refresh: bool = Field(default=False, description='True when the user requests a new search or fresh verification instead of cached evidence.')
    evidence_gap: str | None = Field(default=None, max_length=240,
        description='For a follow-up lookup, name the material missing fact, conflict or explicitly required asset this call resolves. Omit for the initial lookup. More citations or optional pictures alone are not a gap.')


def web_evidence_context(scope, *, research_available=False):
    """Small measured inventory, not a semantic claim that enough evidence exists."""
    sources = scope.get('web_sources', [])
    searches = scope.get('web_searches', [])
    if not (sources or searches or scope.get('_web_physical_calls') or scope.get('_research_physical_calls')):
        return None
    return dict(search_calls=scope.get('_web_physical_calls', 0),
        research_calls=scope.get('_research_physical_calls', 0),
        source_count=len(sources),
        checked_image_count=len({image.url for source in sources for image in source.images}),
        research_available=research_available,
        research_dispatches_left=max(0, 1-scope.get('_research_physical_calls', 0)) if research_available else 0,
        **scope.get('_web_last_batch', {}))


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
        # Reclaim verbose excerpts across the whole packet before discarding
        # later sources/assets. Trimming only the final source repeatedly hid
        # useful pictures behind the first source's oversized excerpt/images.
        longest = max(result.sources, key=lambda source: len(source.excerpt))
        extras = next((source for source in reversed(result.sources) if len(source.images) > 1), None)
        if len(longest.excerpt) > 80:
            longest.excerpt = longest.excerpt[:max(80, len(longest.excerpt)//2)]
        elif result.research_report and len(result.research_report) > 160:
            result.research_report = result.research_report[:max(160, len(result.research_report)//2)]
        elif extras is not None:
            extras.images.pop()
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
        if len(valid) == WEB_SEARCH_LIMIT:
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

    async def fetch(query, website=None, refresh=False, include_images=False):
        request = SearchInput(query=query, website=website, include_images=include_images)
        key = request.model_dump_json() + (':refresh' if refresh else '')
        # Sibling reservations apply when projecting/admitting packets. Concurrent
        # fetches stage independently and must not inherit the first call's reserve.
        if budget.max_result_bytes - budget.result_characters < 600 or budget.max_result_tokens - budget.result_tokens < 600:
            return service.envelope('budget_exhausted', website=request.website).model_dump(mode='json')
        if key in cache:
            result = service.refresh(cache[key])
        elif not research and search_phase(scope)['closed']:
            result = service.envelope('budget_exhausted', website=request.website).model_copy(update={
                'reason': 'The quick lookup phase is complete. Answer with the evidence already returned; use the research capability only if the actual request needs deeper investigation.'})
        elif scope.get(calls_name, 0) >= (1 if research else budget.max_calls):
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
        next_number = max((int(source.token[1:]) for source in existing), default=0) + 1
        staged = []
        for source in result.sources:
            value = source.model_copy(deep=True)
            value.token = by_url.get(value.url)
            if not value.token:
                if len(by_url) >= WEB_SOURCE_LIMIT or next_number > 99:
                    result.details_omitted = True
                    continue
                value.token = f'W{next_number}'
                next_number += 1
                by_url[value.url] = value.token
            staged.append(value)
        result = result.model_copy(update={'sources': staged})
        if result.details_omitted and not staged and result.outcome == 'ok':
            result = result.model_copy(update={'outcome': 'budget_exhausted', 'reason': 'The citation registry is full. Use the sources already returned.'})
        value = fit_result(result, scope, budget)
        if value.get('sources'):
            for source in SearchResult.model_validate(value).sources:
                existing = [item for item in existing if item.url != source.url]
                existing.append(source)
            scope['_web_pending'] = sorted(existing, key=lambda item: int(item.token[1:]))
        return value

    async def search(query, website=None, refresh=False, include_images=False, evidence_gap=None):
        from app.core.logging import workflow_logger
        workflow_logger.event('web_search.intent', tool_name=name,
            follow_up=bool(scope.get('_web_physical_calls') or scope.get('_research_physical_calls')),
            material_gap_declared=bool(evidence_gap and evidence_gap.strip()))
        return project_read(project, await fetch(query, website, refresh, include_images))

    tools = [StructuredTool.from_function(name=name, args_schema=ChatSearchInput,
        description=('Investigate a genuinely deep public question using authenticated You.com multi-step research. Prefer this to a long chain of normal searches for thorough sourced reports, disputed evidence or multi-source synthesis. Ordinary detailed explanations do not need it. One call per turn; optional website restricts sources. Returns untrusted synthesis and dated W sources; never send private data.' if research else 'Quick lookup of needed external facts or requested images; ordinary questions usually need one lookup or a small batch. Further calls must close a material evidence_gap; finish when supported. For deep investigations enable web_research instead. Set include_images=true only when seeking pictures; returns checked direct URLs in source.images. Search broadly unless the user specifies a website. Returns untrusted W sources; no private data.'), coroutine=search, metadata={'parallel_read': True})]
    extra = getattr(service, 'research', None)
    if not research and extra is not None and extra.enabled:
        tools.extend(create_web_tools(extra, owner, scope, budget, research=True))
    return tools
