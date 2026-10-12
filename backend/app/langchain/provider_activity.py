"""Observe the SDK's existing retries; never add a second retry loop."""
from contextvars import ContextVar
from time import monotonic
from app.core.logging import workflow_logger
from .activity import current_publisher

provider_attempt_scope = ContextVar('provider_attempt_scope', default=None)


async def observe_request(request):
    try:
        retry = int(request.headers.get('x-stainless-retry-count', '0'))
    except (TypeError, ValueError):
        return
    scope = provider_attempt_scope.get()
    if not scope:
        return
    if hasattr(request, 'extensions'):
        request.extensions['mentra_started'] = monotonic()
    workflow_logger.event('provider.attempt', attempt=retry + 1, provider_call_id=scope[0])
    if retry:
        publisher = current_publisher.get()
        if publisher:
            step, maximum = scope
            await publisher.emit(step, 'retry_wait', f'The AI request failed. Retrying, attempt {retry + 1} of {maximum}.')


async def observe_response(response):
    started = response.request.extensions.get('mentra_started')
    scope = provider_attempt_scope.get()
    if started is not None and scope:
        workflow_logger.event('provider.headers', duration_ms=round((monotonic()-started)*1000, 3),
            http_status=response.status_code, provider_call_id=scope[0])
