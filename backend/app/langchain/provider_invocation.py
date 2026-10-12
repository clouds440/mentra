"""Deadline-bound provider invocation, including buffered stream aggregation."""
import asyncio
import time
from uuid import uuid4
from langchain_core.messages import AIMessageChunk
from langchain_core.messages.utils import message_chunk_to_message
from .workflow_budget import current_budget
from app.core.logging import workflow_logger
from .provider_activity import provider_attempt_scope


async def invoke_provider(model, prepared, *, on_delta=None, maximum_attempts=3):
    started = time.monotonic()
    callback_seconds = 0
    first_chunk = first_text = None
    outcome = "success"
    async def delta(value):
        nonlocal callback_seconds
        before = time.monotonic()
        try:
            await on_delta(value)
        finally:
            callback_seconds += time.monotonic() - before
    envelope = current_budget.get()
    provider_call_id = 'provider-' + uuid4().hex
    token = provider_attempt_scope.set((provider_call_id, maximum_attempts))
    try:
        async with asyncio.timeout(envelope.remaining if envelope else None):
            if on_delta is None or not hasattr(model, 'astream'):
                return await model.ainvoke(prepared)
            aggregate, pending = None, ''
            emitted = time.monotonic()
            async for chunk in model.astream(prepared):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                if first_chunk is None:
                    first_chunk = time.monotonic()-started
                    workflow_logger.event('provider.first_chunk', duration_ms=round(first_chunk*1000, 3), provider_call_id=provider_call_id)
                if first_text is None and isinstance(chunk.content, str) and chunk.content:
                    first_text = time.monotonic()-started
                    workflow_logger.event('provider.first_text', duration_ms=round(first_text*1000, 3), provider_call_id=provider_call_id)
                aggregate = chunk if aggregate is None else aggregate + chunk
                if isinstance(chunk.content, str):
                    pending += chunk.content
                if pending and (len(pending) >= 512 or time.monotonic() - emitted >= .2):
                    for start in range(0, len(pending), 1000):
                        await delta(pending[start:start+1000])
                    pending, emitted = '', time.monotonic()
            if aggregate is None:
                raise ValueError('Provider returned no response chunks')
            result = message_chunk_to_message(aggregate)
            if getattr(result, 'tool_calls', None):
                await delta(None)
            elif pending:
                for start in range(0, len(pending), 1000):
                    await delta(pending[start:start+1000])
            return result
    except BaseException as error:
        outcome = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'timeout' if isinstance(error, TimeoutError) else 'failed'
        raise
    finally:
        workflow_logger.event('provider.completed', duration_ms=round((time.monotonic()-started)*1000, 3),
            callback_ms=round(callback_seconds*1000, 3), streaming=on_delta is not None, outcome=outcome, provider_call_id=provider_call_id)
        provider_attempt_scope.reset(token)
