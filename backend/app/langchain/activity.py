"""Public execution updates. No prompts, tool arguments or reasoning are published."""
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

current_tool_call: ContextVar[str | None] = ContextVar('current_tool_call', default=None)


class ActivityUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    step_id: str = Field(min_length=1, max_length=80)
    status: Literal['planned', 'running', 'completed', 'failed', 'waiting']
    user_message: str = Field(min_length=1, max_length=240)
    tool_name: str | None = Field(default=None, max_length=100)
    tool_call_id: str | None = Field(default=None, max_length=200)
    token_delta: str | None = Field(default=None, max_length=2000)
    token_reset: bool = False


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

    async def emit(self, step_id, status, message, *, tool_name=None, tool_call_id=None, token_delta=None, token_reset=False):
        update = ActivityUpdate(step_id=step_id, status=status, user_message=message,
                                tool_name=tool_name, tool_call_id=tool_call_id, token_delta=token_delta, token_reset=token_reset)
        if self.sink is not None:
            await self.sink.publish(update)

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
