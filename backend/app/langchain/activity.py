"""Public execution updates. No prompts, tool arguments or reasoning are published."""
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
import logging
from app.core.exceptions import AppError

current_tool_call: ContextVar[str | None] = ContextVar('current_tool_call', default=None)
current_publisher = ContextVar('current_activity_publisher', default=None)


@contextmanager
def publish_activity(publisher):
    token = current_publisher.set(publisher)
    try:
        yield
    finally:
        current_publisher.reset(token)


class ActivityUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    step_id: str = Field(min_length=1, max_length=80)
    status: Literal['planned', 'running', 'completed', 'failed', 'waiting', 'retry_wait', 'degraded', 'cancelled']
    user_message: str = Field(min_length=1, max_length=240)
    tool_name: str | None = Field(default=None, max_length=100)
    tool_call_id: str | None = Field(default=None, max_length=200)
    token_delta: str | None = Field(default=None, max_length=2000)
    token_reset: bool = False
    tool_attempt: int | None = Field(default=None, ge=1, le=3)
    max_attempts: int | None = Field(default=None, ge=1, le=3)
    error_code: str | None = Field(default=None, max_length=100)


class ActivityEvent(ActivityUpdate):
    schema_version: Literal[1] = 1
    event_id: UUID
    conversation_id: UUID
    turn_id: UUID
    attempt: int = Field(ge=1)
    sequence: int = Field(ge=1)
    occurred_at: datetime


class ActivitySink(Protocol):
    async def publish(self, update: ActivityUpdate) -> None: ...


class ActivityPublisher:
    def __init__(self, sink: ActivitySink | None = None):
        self.sink = sink
        self.reporting_unavailable = False

    async def emit(self, step_id, status, message, *, tool_name=None, tool_call_id=None, token_delta=None, token_reset=False, tool_attempt=None, max_attempts=None, error_code=None):
        update = ActivityUpdate(step_id=step_id, status=status, user_message=message,
                                tool_name=tool_name, tool_call_id=tool_call_id, token_delta=token_delta, token_reset=token_reset,
                                tool_attempt=tool_attempt, max_attempts=max_attempts, error_code=error_code)
        if self.sink is not None and not self.reporting_unavailable:
            try:
                await self.sink.publish(update)
            except AppError as error:
                if error.code in ('CHAT_ATTEMPT_EXPIRED', 'CHAT_STALE_ATTEMPT', 'CHAT_DELETED', 'CHAT_NOT_FOUND'):
                    raise
                self.reporting_unavailable = True
                logging.getLogger('mentra').warning('Activity publication unavailable (%s)', error.code)
            except Exception as error:
                self.reporting_unavailable = True
                logging.getLogger('mentra').warning('Activity publication unavailable (%s)', type(error).__name__)

    async def ensure_active(self):
        """Writes fail closed if the independent canonical-attempt guard cannot run."""
        if self.sink is not None and hasattr(self.sink, 'ensure_active'):
            await self.sink.ensure_active()

    @asynccontextmanager
    async def step(self, message, *, tool_name=None, tool_call_id=None, step_id=None):
        step_id = step_id or uuid4().hex
        await self.emit(step_id, 'running', message, tool_name=tool_name, tool_call_id=tool_call_id)
        try:
            yield
        except BaseException:
            await self.emit(step_id, 'failed', 'This step could not be completed.', tool_name=tool_name, tool_call_id=tool_call_id)
            raise
        else:
            await self.emit(step_id, 'completed', message, tool_name=tool_name, tool_call_id=tool_call_id)
