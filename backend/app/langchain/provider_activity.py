"""Observe the SDK's existing retries; never add a second retry loop."""
from contextvars import ContextVar
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
    workflow_logger.event('provider.attempt', attempt=retry + 1)
    if retry:
        publisher = current_publisher.get()
        if publisher:
            step, maximum = scope
            await publisher.emit(step, 'retry_wait', f'The AI request failed. Retrying, attempt {retry + 1} of {maximum}.')
