"""Content-free timings for the waits surrounding domain operations."""
from time import monotonic
from starlette.concurrency import run_in_threadpool as dispatch
from .events import emit


async def run_in_threadpool(action, *args, **kwargs):
    queued = monotonic()
    name = getattr(action, '__qualname__', type(action).__name__)
    def invoke():
        started = monotonic()
        emit('thread.started', operation=name, queue_ms=round((started-queued)*1000, 3))
        try:
            return action(*args, **kwargs)
        finally:
            emit('thread.completed', operation=name, duration_ms=round((monotonic()-started)*1000, 3))
    return await dispatch(invoke)
