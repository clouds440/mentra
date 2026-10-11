"""Deadline-bound provider invocation, including buffered stream aggregation."""
import asyncio
import time
from uuid import uuid4
from langchain_core.messages import AIMessageChunk
from langchain_core.messages.utils import message_chunk_to_message
from .workflow_budget import current_budget
from .provider_activity import provider_attempt_scope


async def invoke_provider(model, prepared, *, on_delta=None, maximum_attempts=3):
    envelope = current_budget.get()
    token = provider_attempt_scope.set(('provider-' + uuid4().hex, maximum_attempts))
    try:
        async with asyncio.timeout(envelope.remaining if envelope else None):
            if on_delta is None or not hasattr(model, 'astream'):
                return await model.ainvoke(prepared)
            aggregate, pending = None, ''
            emitted = time.monotonic()
            async for chunk in model.astream(prepared):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                aggregate = chunk if aggregate is None else aggregate + chunk
                if isinstance(chunk.content, str):
                    pending += chunk.content
                if pending and (len(pending) >= 512 or time.monotonic() - emitted >= .2):
                    for start in range(0, len(pending), 1000):
                        await on_delta(pending[start:start+1000])
                    pending, emitted = '', time.monotonic()
            if aggregate is None:
                raise ValueError('Provider returned no response chunks')
            result = message_chunk_to_message(aggregate)
            if getattr(result, 'tool_calls', None):
                await on_delta(None)
            elif pending:
                for start in range(0, len(pending), 1000):
                    await on_delta(pending[start:start+1000])
            return result
    finally:
        provider_attempt_scope.reset(token)
