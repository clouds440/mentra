from uuid import UUID, uuid4
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.rag.schemas import ChatSelection
from app.workspace.schemas import SourceAnnotation


from .interactions import InteractionResponse
from app.challenge.schemas import ChallengeAction

class SendTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID
    client_turn_id: UUID
    expected_revision: int = Field(ge=0)
    content: str = Field(max_length=4000)
    source_annotations: list[SourceAnnotation] = Field(default_factory=list, max_length=4)
    retrieval: ChatSelection = Field(default_factory=ChatSelection)
    interaction_response: InteractionResponse | None = None
    challenge_action: ChallengeAction | None = None
    retry: bool = False
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=4)
    timezone: str | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def isolated_challenge_action(self):
        if self.challenge_action and (self.interaction_response or self.source_annotations or self.attachment_ids):
            raise ValueError('Send difficulty actions separately from attachments, selections and other interactions.')
        return self

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        from app.history_management.events.schemas import validate_zone
        return validate_zone(value) if value else value


class EditConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)


class OrganizeConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    pinned: bool | None = None
    archived: bool | None = None

    @model_validator(mode='after')
    def one_change(self):
        if (self.pinned is None) == (self.archived is None):
            raise ValueError('Choose exactly one pin or archive change.')
        return self


class ManagedChat(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID
    expected_revision: int = Field(ge=1)


class BulkChatAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    action: Literal['archive', 'unarchive', 'delete']
    items: list[ManagedChat] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def distinct_chats(self):
        if len({item.conversation_id for item in self.items}) != len(self.items):
            raise ValueError('Choose each chat only once.')
        return self


class StopTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attempt: int = Field(ge=1)


class ResumeTurn(StopTurn):
    expected_revision: int = Field(ge=1)
    instruction: str | None = Field(default=None, min_length=1, max_length=4000)
    client_request_id: UUID = Field(default_factory=uuid4)


class ChatSearchHit(BaseModel):
    archived_at: datetime | None = None
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
    source_annotations: list[SourceAnnotation] = Field(default_factory=list, max_length=4)
    id: UUID
    role: Literal['user', 'assistant']
    content: str
    created_at: datetime


class SavedExchange(BaseModel):
    conversation_id: UUID
    title: str
    matched_message_id: UUID
    messages: list[SavedExchangeMessage] = Field(max_length=3)
