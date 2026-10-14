"""Bounded read recovery; writes retain domain-owned replay/receipts."""
import asyncio
from time import monotonic
from hashlib import sha256
from .concurrent_reads import StagedRead
from .tool_cache import tool_cache_key, REVALIDATED_READS, copy_result
import random
import math
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from uuid import uuid4
import httpx
from pydantic import BaseModel, Field, ValidationError
from app.core.exceptions import AppError
from app.core.logging import workflow_logger
from .tool_policy import is_write, DOMAINS
from .tool_activity import LABELS
from .workflow_budget import current_budget
from .activity import current_tool_call
from app.core.config import settings

LIFECYCLE_CODES = {'CHAT_ATTEMPT_EXPIRED', 'CHAT_STALE_ATTEMPT', 'CHAT_DELETED', 'CHAT_NOT_FOUND'}


class ToolFailure(BaseModel):
    outcome: str = 'unavailable'
    code: str
    reason: str = Field(max_length=240)
    category: str
    retryable: bool = False
    attempts: int = 0
    task_impact: str = 'optional'
    effect_certainty: str = 'read_only'


def failure(error, *, write=False, attempts=0, required=False, execution_started=False):
    code = error.code if isinstance(error, AppError) else 'TOOL_INTERNAL_ERROR'
    status = getattr(error, 'status_code', None) or getattr(getattr(error, 'response', None), 'status_code', None)
    from app.db.errors import database_busy
    if database_busy(error):
        code, status = 'DATABASE_BUSY', 503
    category, retryable = 'internal_error', False
    if isinstance(error, ValidationError):
        code, category = ('TOOL_INVALID_RESULT', 'invalid_result') if execution_started else ('TOOL_INVALID_ARGUMENTS', 'invalid_arguments')
    elif isinstance(error, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.TransportError)):
        code, category, retryable = 'TOOL_TIMEOUT' if isinstance(error, (TimeoutError, httpx.TimeoutException)) else 'TOOL_CONNECTION_ERROR', 'transient_dependency', True
    elif code in LIFECYCLE_CODES:
        category = 'stale_attempt'
    elif 'BUDGET' in code or 'LIMIT' in code:
        category = 'budget_exhausted'
    elif status in (401, 403):
        category = 'authorization'
    elif status == 404:
        category = 'not_found'
    elif 'CONFIRM' in code or 'REVIEW_REQUIRED' in code:
        category = 'confirmation_required'
    elif status == 409:
        category = 'conflict'
    elif status == 429:
        category, retryable = 'rate_limited', True
    elif status in (408, 502, 503, 504) and 'CONFIGURATION' not in code:
        category, retryable = 'transient_dependency', True
    elif status in (400, 422):
        category = 'invalid_arguments'
    # Domain AppError messages are safe public contract text. Never publish raw exceptions.
    reason = error.message[:240] if isinstance(error, AppError) else {
        'invalid_arguments': 'The tool arguments were invalid. Correct them using its schema; do not guess missing user information.',
        'transient_dependency': 'The service could not complete this request in time.',
        'invalid_result': 'This action did not produce a usable result.',
    }.get(category, 'This action could not be completed. Use available evidence or ask for the missing information.')
    certainty = 'unknown' if write else 'read_only'
    if write and category in ('invalid_arguments', 'authorization', 'not_found', 'confirmation_required', 'budget_exhausted'):
        certainty = 'not_committed'
    return ToolFailure(code=code, reason=reason, category=category, retryable=retryable and not write,
                       attempts=attempts, task_impact='required_for_part' if required else 'optional', effect_certainty=certainty)


def retry_delay(error, attempt):
    headers = getattr(error, 'headers', None) or getattr(getattr(error, 'response', None), 'headers', None) or {}
    after = headers.get('retry-after')
    if after is not None:
        try:
            return max(0, float(after))
        except (TypeError, ValueError):
            try:
                return max(0, (parsedate_to_datetime(after) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return (.5 if attempt == 1 else 1.5) * random.uniform(.75, 1)


def outcome_status(result):
    value = result.get('outcome', result.get('status')) if isinstance(result, dict) else None
    if value in ('unavailable', 'answer_preparation_failed', 'failed', 'rejected', 'conflict', 'quota_exhausted', 'rate_limited', 'timeout', 'invalid_input', 'budget_exhausted', 'disabled'):
        return 'failed', 'rejected' if value in ('rejected', 'conflict', 'invalid_input', 'failed') else 'degraded'
    if value in ('pending', 'awaiting_confirmation', 'confirmation_required', 'candidate', 'ambiguous'):
        return 'waiting', 'deferred'
    if value in ('partial', 'degraded'):
        return 'degraded', 'degraded'
    return 'completed', 'success'


def remember_failure(scope, name, receipt):
    if isinstance(receipt, ToolFailure):
        receipt = receipt.model_dump(mode='json')
    warnings = scope.setdefault('tool_warnings', [])
    warning = dict(tool_name=name, code=receipt.get('code', 'TOOL_UNAVAILABLE'),
                   message=receipt.get('reason', 'This capability was unavailable.')[:240],
                   task_impact=receipt.get('task_impact', 'optional'),
                   effect_certainty=receipt.get('effect_certainty', 'read_only'))
    if warning not in warnings and len(warnings) < 16:
        warnings.append(warning)


class ToolExecutor:
    def __init__(self, budget, scope, publisher):
        self.budget, self.scope, self.publisher = budget, scope, publisher
        state = scope.setdefault('_tool_execution_state', {'failed': {}, 'results': {}, 'outages': {}})
        self.failed, self.results, self.outages = state['failed'], state['results'], state['outages']

    def invalidate_written_domain(self, domain):
        # Both cache layers must expire together after a mutation, including an
        # uncertain mutation outcome. Keep write-failure receipts for replay safety.
        affected = {'learner': {'learner', 'rag', 'profile'},
                    'assessment': {'assessment', 'learner', 'profile'},
                    'memory': {'memory', 'profile'}}.get(domain, {domain})
        for key in list(self.results):
            name = key.split(':', 1)[0]
            if DOMAINS.get(name, 'profile' if name == 'profile_context' else name) in affected:
                self.results.pop(key, None)
        for key, receipt in list(self.failed.items()):
            if DOMAINS.get(key.split(':', 1)[0]) in affected and receipt.get('effect_certainty') == 'read_only':
                self.failed.pop(key, None)
        for name in affected:
            self.outages.pop(name, None)
        prefixes = tuple(prefix for name in affected for prefix in
                         {'learner': ('learner:',), 'memory': ('recall:',), 'rag': ('study:',)}.get(name, ()))
        for key in list(self.budget.cache):
            if prefixes and key.startswith(prefixes):
                self.budget.cache.pop(key, None)
        if 'learner' in affected:
            self.scope.pop('_initial_learner_context', None)
        if 'rag' in affected:
            self.scope.pop('_initial_search', None)

    async def execute(self, tool, arguments, *, required=False, max_attempts=None, timeout=None):
        started = monotonic()
        max_attempts = max_attempts or settings.tool_read_max_attempts
        timeout = timeout or settings.tool_read_timeout_seconds
        name = tool.name
        web = name in ('web_search', 'web_research')
        if web:
            max_attempts, timeout = 1, 46 if name == 'web_research' else 21
        def project(value):
            if web and isinstance(value, StagedRead):
                return StagedRead(value.project, dict(value.payload, reused_within_turn=True))
            if web:
                from .web_tools import dated_failure
                return dated_failure(self.scope, value)
            return value
        write = is_write(name, arguments)
        key = tool_cache_key(tool, name, arguments)
        if not write and name not in REVALIDATED_READS and key in self.results:
            workflow_logger.event('tool.cache_hit', tool_name=name, cache_layer='turn',
                duration_ms=round((monotonic()-started)*1000, 3), tool_call_id=current_tool_call.get())
            return project(copy_result(self.results[key]))
        if key in self.failed:
            workflow_logger.event('tool.exhausted_skip', tool_name=name, error_code=self.failed[key].get('code', 'TOOL_UNAVAILABLE'))
            receipt = dict(self.failed[key], repeated_failure=True, task_impact='required_for_part' if required else 'optional')
            remember_failure(self.scope, name, receipt)
            return project(receipt)
        domain = (tool.metadata or {}).get('domain', name)
        if not write and domain in self.outages:
            workflow_logger.event('tool.exhausted_skip', tool_name=name, domain=domain, error_code=self.outages[domain].get('code', 'TOOL_UNAVAILABLE'))
            receipt = dict(self.outages[domain], repeated_failure=True, task_impact='required_for_part' if required else 'optional')
            remember_failure(self.scope, name, receipt)
            return project(receipt)
        workflow_logger.event('tool.started', tool_name=name, arguments_fingerprint=sha256(key.encode()).hexdigest()[:16], tool_call_id=current_tool_call.get())
        step = uuid4().hex
        label = LABELS.get(name, 'Processing your request')
        call_id = current_tool_call.get()
        await self.publisher.emit(step, 'planned', label, tool_name=name, tool_call_id=call_id)
        attempts = 0
        for attempt in range(1, (1 if write else max_attempts) + 1):
            attempts = attempt
            execution_started = False
            try:
                self.budget.call(write)
                envelope = current_budget.get()
                if envelope and envelope.remaining <= envelope.answer_reserve:
                    raise AppError('TOOL_BUDGET', 'Tool work stopped to leave time for your answer.', 422)
                await self.publisher.emit(step, 'running', label, tool_name=name, tool_call_id=call_id,
                                          tool_attempt=attempt, max_attempts=1 if write else max_attempts)
                if write:
                    await self.publisher.ensure_active()
                # Validate before invoking; never retry validation or permit guessed IDs.
                validated_arguments = tool.args_schema.model_validate(arguments)
                with self.budget.admitted():
                    execution_started = True
                    async with workflow_logger.step('app.langchain.tool_execution', 'tool.attempt', input=dict(tool_name=name, attempt=attempt), request=validated_arguments) as observed_attempt:
                        attempt_started = monotonic()
                        try:
                            invocation = tool.ainvoke(arguments)
                            result = await invocation if write else await asyncio.wait_for(invocation, min(timeout, envelope.tool_remaining if envelope else timeout))
                        finally:
                            observed_attempt.executed(attempt_started)
                        observed_attempt.response(result.payload if isinstance(result, StagedRead) else result)
                        observed_attempt.result(dict(tool_name=name, attempt=attempt), outcome_status(result.payload if isinstance(result, StagedRead) else result)[1])
                if write:
                    self.invalidate_written_domain(domain)
                observed = result.payload if isinstance(result, StagedRead) and isinstance(result.payload, dict) else result
                status, semantic = outcome_status(observed)
                message = label
                if status == 'failed':
                    message = 'The assessment is saved, but answer preparation failed.' if isinstance(result, dict) and result.get('assessment_saved') else 'This action could not be completed.'
                    if isinstance(result, dict) and not web:
                        result = dict(result, task_impact='required_for_part' if required else 'optional',
                                      effect_certainty='committed' if result.get('assessment_saved') else 'unknown' if write else 'read_only')
                        observed = result
                    remember_failure(self.scope, name, observed if isinstance(observed, dict) else {})
                    self.failed[key] = observed
                elif status == 'waiting':
                    message = 'This action needs your review or more information.'
                await self.publisher.emit(step, status, message, tool_name=name, tool_call_id=call_id,
                                          tool_attempt=attempt, max_attempts=1 if write else max_attempts)
                workflow_logger.event('tool.result', tool_name=name, outcome=semantic, attempts=attempt, duration_ms=round((monotonic()-started)*1000, 3), tool_call_id=call_id)
                if not write:
                    if status != 'failed' and name not in REVALIDATED_READS:
                        self.results[key] = copy_result(result)
                return result
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if isinstance(error, AppError) and error.code in LIFECYCLE_CODES:
                    raise
                receipt = failure(error, write=write, attempts=attempt, required=required, execution_started=execution_started).model_dump()
                if write and not execution_started:
                    receipt['effect_certainty'] = 'not_started'
                elif write:
                    self.invalidate_written_domain(domain)
                envelope = current_budget.get()
                delay = retry_delay(error, attempt)
                retry_window = min(60, envelope.tool_remaining if envelope else timeout)
                can_retry = receipt['retryable'] and not write and attempt < max_attempts and self.budget.calls < self.budget.max_calls and math.isfinite(delay) and retry_window > delay + .1
                if can_retry:
                    await self.publisher.emit(step, 'retry_wait', f'{label} failed. Retrying, attempt {attempt + 1} of {max_attempts}.',
                        tool_name=name, tool_call_id=call_id, tool_attempt=attempt + 1, max_attempts=max_attempts, error_code=receipt['code'])
                    workflow_logger.event('tool.retry_scheduled', tool_name=name, attempt=attempt, next_attempt=attempt+1, error_code=receipt['code'])
                    await asyncio.sleep(delay)
                    continue
                self.failed[key] = receipt
                if receipt['retryable']:
                    self.outages[domain] = receipt
                remember_failure(self.scope, name, receipt)
                from app.core.observability.sanitization import error_metadata
                workflow_logger.event('tool.failed', level=logging.WARNING, tool_name=name, error_code=receipt['code'], category=receipt['category'],
                                      attempts=attempt, duration_ms=round((monotonic()-started)*1000, 3), tool_call_id=call_id, task_impact=receipt['task_impact'], effect_certainty=receipt['effect_certainty'], error=error_metadata(error))
                await self.publisher.emit(step, 'failed', receipt['reason'], tool_name=name, tool_call_id=call_id,
                    tool_attempt=attempt, max_attempts=1 if write else max_attempts, error_code=receipt['code'])
                await self.publisher.emit(step + '-recovery', 'degraded', 'Continuing with available information; this action remains unverified.' if receipt['effect_certainty'] == 'unknown' else 'Continuing with available information; missing information will be identified.', tool_name=name)
                return project(receipt)
        raise AssertionError(f'No terminal result after {attempts} attempts')
