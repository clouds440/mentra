"""Bounded web search with dated outcomes and charged ambiguous deliveries."""
import asyncio
import logging
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from time import monotonic
from uuid import uuid5, NAMESPACE_URL
from typing import Callable, Iterable
from zoneinfo import ZoneInfo
from app.core.observability.timing import run_in_threadpool
from .repositories import RepositoryError, UsageStore
from app.core.logging import workflow_logger
from .schemas import SearchInput, SearchResult, WebSource
from .normalization import normalize_results
from .provider import ProviderError, SearchProvider

logger = logging.getLogger('mentra')
REASONS = {
    'disabled': 'Web search is disabled.', 'invalid_input': 'Use a valid query and one public website scope.',
    'budget_exhausted': 'Web search stopped to preserve the answer budget.',
    'quota_exhausted': 'The free search allowance is exhausted. Current facts remain unverified.',
    'rate_limited': 'Web search is temporarily rate limited.',
    'timeout': 'Web search did not finish in time. Current facts remain unverified.',
    'unavailable': 'Web search is unavailable. Current facts remain unverified.',
    'no_results': 'No matching web sources were returned.',
    'partial': 'Some results were discarded or omitted. Use only the returned sources.',
}


@workflow_logger.connect_module(ignore=('envelope', 'refresh'), default_outcome='success', policies={
    'search': {'result': lambda value: dict(domain_status=value.outcome, source_count=len(value.sources)),
               'outcome': lambda value: 'success' if value.outcome in ('ok', 'no_results') else 'degraded'},
})
class WebSearchService:
    def __init__(self, provider: SearchProvider, usage: UsageStore, *, enabled: bool = False, reference_timezone: str = 'UTC', clock: Callable[[], datetime] | None = None, cache_seconds: int = 120, request_timeout: float = 20, namespace: str = 'search'):
        if not 0 <= cache_seconds <= 300:
            raise ValueError('Search cache lifetime must be between 0 and 300 seconds.')
        self.provider, self.usage, self.enabled = provider, usage, enabled
        self.zone = ZoneInfo(reference_timezone)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.semaphore = asyncio.Semaphore(2)
        self.cache_seconds = cache_seconds
        self.request_timeout, self.namespace = request_timeout, namespace
        self._cache_locks = {}

    @asynccontextmanager
    async def _cache_flight(self, key, enabled):
        # Waiters share a cache fill without owning/cancelling another request.
        # Every caller retains its own deadline and normal quota admission.
        if not enabled or key not in self._cache_locks and len(self._cache_locks) >= 128:
            yield
            return
        entry = self._cache_locks.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if not entry[1]:
                self._cache_locks.pop(key, None)

    def envelope(self, outcome: str, *, website: str | None = None, searched_at: datetime | None = None, sources: Iterable[WebSource] = (), reused: bool = False) -> SearchResult:
        now = self.clock().astimezone(self.zone)
        reason = REASONS.get(outcome)
        if self.namespace == 'research' and outcome == 'quota_exhausted':
            reason = 'The research allowance or provider credits are exhausted. Current facts remain unverified.'
        return SearchResult(outcome=outcome, reason=reason, current_date=now.date(),
            current_datetime=now, reference_timezone=self.zone.key, delivered_at=now,
            searched_at=searched_at, website=website, sources=list(sources), reused_within_turn=reused)

    def refresh(self, result: SearchResult | dict, *, within_turn: bool = True) -> SearchResult:
        value = SearchResult.model_validate(result)
        refreshed = self.envelope(value.outcome, website=value.website, searched_at=value.searched_at,
                             sources=value.sources, reused=within_turn)
        return refreshed.model_copy(update={'reason': value.reason, 'cache_hit': value.cache_hit, 'cache_expires_at': value.cache_expires_at,
                                           'research_report': value.research_report, 'details_omitted': value.details_omitted})

    async def search(self, request: SearchInput, *, owner: str, attempt_id: str, deadline: float, bypass_cache: bool = False) -> SearchResult:
        if not self.enabled:
            return self.envelope('disabled', website=request.website)
        remaining = min(self.request_timeout, deadline - monotonic())
        if remaining <= .1:
            return self.envelope('budget_exhausted', website=request.website)
        started = monotonic()
        context = {'searched_at': None}
        try:
            async with asyncio.timeout(remaining):
                key = hashlib.sha256(f'{self.namespace}:{owner}:{self.clock().astimezone(self.zone).date()}:{request.model_dump_json()}'.encode('utf-8')).hexdigest()
                async with self._cache_flight(key, self.cache_seconds and not bypass_cache):
                    if self.cache_seconds and not bypass_cache:
                        try:
                            cached = await run_in_threadpool(self.usage.cached, owner, key, self.clock())
                        except RepositoryError:
                            # Cache is optional; quota admission must still succeed before dispatch.
                            logger.warning('Web search result cache read unavailable.')
                            cached = None
                        if cached:
                            value = self.refresh(cached['payload'], within_turn=False)
                            workflow_logger.event('web_search.cache_hit', source_count=len(value.sources))
                            return value.model_copy(update={'cache_hit': True, 'cache_expires_at': cached['expires_at']})
                    return await self._search(request, owner, attempt_id, context, key)
        except TimeoutError:
            return self.envelope('timeout', website=request.website, searched_at=context['searched_at'])
        except (ProviderError, RepositoryError, ValueError) as error:
            outcome = error.outcome if isinstance(error, ProviderError) else 'unavailable'
            workflow_logger.event('web_search.failed', level=logging.WARNING, error_code=outcome, latency_ms=int((monotonic()-started)*1000))
            return self.envelope(outcome, website=request.website, searched_at=context['searched_at'])

    async def _search(self, request, owner, attempt_id, context, cache_key):
        acquired = False
        try:
            async with asyncio.timeout(1):
                await self.semaphore.acquire()
                acquired = True
        except TimeoutError:
            return self.envelope('rate_limited', website=request.website)
        operation = str(uuid5(NAMESPACE_URL, f'mentra-web:{self.namespace}:{owner}:{attempt_id}:{request.model_dump_json()}'))
        sent, reserved, searched = False, False, None
        # Shield repository admission: cancellation cannot abandon an unobserved thread.
        task = asyncio.create_task(run_in_threadpool(self.usage.reserve, owner, operation, self.clock()))
        try:
            try:
                admission = await asyncio.shield(task)
            except asyncio.CancelledError:
                admission = await task
                if admission == 'reserved':
                    await run_in_threadpool(self.usage.mark, operation, 'released')
                raise
            if admission != 'reserved':
                return self.envelope('unavailable' if admission == 'duplicate' else admission, website=request.website)
            reserved = True
            await run_in_threadpool(self.usage.mark, operation, 'sent')
            # Charge before handing control to the transport; any ambiguity consumes allowance.
            sent = True
            searched = self.clock().astimezone(timezone.utc)
            context['searched_at'] = searched
            payload = await self.provider.search(request)
            sources, dropped = normalize_results(payload, request.website, searched)
            await run_in_threadpool(self.usage.mark, operation, 'completed')
            outcome = 'partial' if dropped and sources else 'unavailable' if dropped else 'ok' if sources else 'no_results'
            workflow_logger.event('web_search.result', outcome=outcome, source_count=len(sources), discarded=dropped)
            result = self.envelope(outcome, website=request.website, searched_at=searched, sources=sources)
            if isinstance(payload.get('research_report'), str):
                report = payload['research_report']
                result = result.model_copy(update={'research_report': report[:6000], 'details_omitted': len(report) > 6000})
            if self.cache_seconds and sources and outcome in ('ok', 'partial'):
                now = self.clock()
                try:
                    await run_in_threadpool(self.usage.cache_result, owner, cache_key, now, now + timedelta(seconds=self.cache_seconds), result.model_dump(mode='json'))
                except RepositoryError:
                    # Cache is optional; already retrieved evidence remains useful.
                    logger.warning('Web search result cache unavailable.')
            return result
        except BaseException:
            if reserved:
                try:
                    await asyncio.shield(run_in_threadpool(self.usage.mark, operation, 'unknown' if sent else 'released'))
                except RepositoryError:
                    logger.warning('Web search reservation reconciliation unavailable.')
            raise
        finally:
            if acquired:
                self.semaphore.release()

    async def close(self) -> None:
        await self.provider.close()
        if hasattr(self, 'research'):
            await self.research.close()
