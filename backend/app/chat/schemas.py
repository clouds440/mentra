from uuid import UUID
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.rag.schemas import ChatSelection


from .interactions import InteractionResponse

class SendTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID
    client_turn_id: UUID
    expected_revision: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=4000)
    retrieval: ChatSelection = Field(default_factory=ChatSelection)
    interaction_response: InteractionResponse | None = None
    retry: bool = False
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=4)
    timezone: str | None = Field(default=None, max_length=100)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        from app.history_management.events.schemas import validate_zone
        return validate_zone(value) if value else value


class EditConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)


class StopTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attempt: int = Field(ge=1)


class ChatSearchHit(BaseModel):
    conversation_id: UUID
    title: str
    matched_message_id: UUID
    sequence: int
    role: Literal['user', 'assistant']
    snippet: str = Field(max_length=260)
    created_at: datetime
    matched_in: Literal['message', 'title']


class ChatSearchPage(BaseModel):
    items: list[ChatSearchHit] = Field(max_length=20)
    next_offset: int | None = None
    truncated: bool = False


class SavedExchangeMessage(BaseModel):
    id: UUID
    role: Literal['user', 'assistant']
    content: str
    created_at: datetime


class SavedExchange(BaseModel):
    conversation_id: UUID
    title: str
    matched_message_id: UUID
    messages: list[SavedExchangeMessage] = Field(max_length=3)
