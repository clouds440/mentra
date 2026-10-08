from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class MemoryCreate(Contract):
    content: str = Field(min_length=1, max_length=500)
    category: Literal['preference', 'fact', 'goal'] = 'fact'
    expires_at: datetime | None = None
    pinned: bool = False
    client_request_id: UUID

    @model_validator(mode='after')
    def dates(self):
        if self.expires_at and self.expires_at.tzinfo is None:
            raise ValueError('Expiration must include a timezone.')
        return self


class MemoryEdit(Contract):
    expected_revision: int = Field(ge=1)
    content: str | None = Field(default=None, min_length=1, max_length=500)
    pinned: bool | None = None
    confirm: bool = False
    expires_at: datetime | None = None
    clear_expiration: bool = False
    resolve_conflict: bool = False
    conflict_revisions: dict[UUID, PositiveInt] | None = Field(default=None, max_length=5)

    @model_validator(mode='after')
    def dates(self):
        if self.expires_at and self.expires_at.tzinfo is None:
            raise ValueError('Expiration must include a timezone.')
        if self.clear_expiration and self.expires_at is not None:
            raise ValueError('Choose an expiration date or clear it, not both.')
        if self.conflict_revisions is not None and not self.resolve_conflict:
            raise ValueError('Conflict revisions require explicit conflict resolution.')
        return self


class PreferencesEdit(Contract):
    automatic_memory: bool
    expected_revision: int = Field(ge=0)


class HistoryLookup(Contract):
    scope: Literal['current_chat', 'selected_chats', 'all_chats'] = 'current_chat'
    query: str = Field(default='', max_length=300)
    chat_ids: list[UUID] = Field(default_factory=list, max_length=10)
    before_sequence: int | None = Field(default=None, ge=1)
    after_sequence: int | None = Field(default=None, ge=0)
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(default=3, ge=1, le=3)

    @model_validator(mode='after')
    def scope_query(self):
        if self.before_sequence is not None and self.after_sequence is not None:
            raise ValueError('Choose one sequence pagination direction.')
        if (self.before_sequence is not None or self.after_sequence is not None) and self.scope != 'current_chat':
            raise ValueError('Sequence anchors require current_chat scope.')
        if any(value and value.tzinfo is None for value in (self.created_before, self.created_after)):
            raise ValueError('Dates must include a timezone.')
        if self.created_before and self.created_after and self.created_after >= self.created_before:
            raise ValueError('Start date must precede end date.')
        if self.scope != 'current_chat' and not self.query:
            raise ValueError('Keywords are required for searching multiple chats.')
        if self.scope == 'selected_chats' and not self.chat_ids:
            raise ValueError('Select at least one chat.')
        if self.scope != 'selected_chats' and self.chat_ids:
            raise ValueError('Chat IDs are only accepted for selected_chats.')
        return self


class MemoryToolInput(Contract):
    action: Literal['recall', 'remember', 'revise']
    query: str = Field(default='', max_length=300)
    content: str = Field(default='', max_length=500)
    category: Literal['preference', 'fact', 'goal'] = 'fact'
    evidence_message_id: UUID | None = None
    evidence_quote: str = Field(default='', max_length=1000)
    memory_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def action_fields(self):
        if self.action == 'recall' and not self.query:
            raise ValueError('Recall requires keywords.')
        if self.action != 'recall' and (not self.content or not self.evidence_message_id or not self.evidence_quote):
            raise ValueError('Writes require content and exact user-message evidence.')
        if self.action == 'revise' and (not self.memory_id or self.expected_revision is None):
            raise ValueError('Revisions require the memory ID and expected revision.')
        return self
