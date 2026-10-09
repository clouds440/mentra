from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class NotificationDraft(Contract):
    producer: str = Field(min_length=1, max_length=60)
    delivery_key: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default='', max_length=1000)
    target_kind: Literal['event', 'assessment', 'none'] = 'none'
    target_id: UUID | None = None
    due_at: AwareDatetime


class InboxEdit(Contract):
    expected_revision: int = Field(ge=1)
    action: Literal['read', 'dismiss']


class NotificationPreferencesEdit(Contract):
    expected_revision: int = Field(ge=0)
    enabled: bool
    disabled_kinds: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(default_factory=list, max_length=20)
