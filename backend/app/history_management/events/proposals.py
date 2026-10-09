"""Durable domain proposals; checkpoint state is never the business record."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .schemas import Contract, EventDraft, EventStatus


class EventCandidate(Contract):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=1000)
    kind: Literal['quiz', 'exam', 'assignment', 'deadline', 'study', 'other'] = 'other'
    context_id: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=100)
    local_date: str | None = Field(default=None, max_length=10)
    starts_at: str | None = Field(default=None, max_length=50)
    ends_at: str | None = Field(default=None, max_length=50)


class EventManage(Contract):
    action: Literal['create', 'edit', 'status'] = 'create'
    message_id: UUID
    quote: str = Field(min_length=1, max_length=500)
    candidate: EventCandidate | None = None
    target_id: UUID | None = None
    target_revision: int | None = Field(default=None, ge=1)
    status: EventStatus | None = None
    uncertainty: str = Field(default='Please review these event details.', max_length=240)

    @model_validator(mode='after')
    def shape(self):
        if self.action in ('create', 'edit') and self.candidate is None:
            raise ValueError('Event details are required.')
        if self.action != 'create' and (self.target_id is None or self.target_revision is None):
            raise ValueError('Updates require a target and its current revision.')
        if self.action == 'status' and self.status is None:
            raise ValueError('A lifecycle status is required.')
        if self.action == 'create' and (self.target_id is not None or self.target_revision is not None):
            raise ValueError('New events cannot select a target.')
        return self


class ProposalDecision(Contract):
    expected_revision: int = Field(ge=1)
    decision: Literal['approve', 'dismiss']
    details: EventDraft | None = None


class EventProposal(Contract):
    id: UUID
    revision: int
    state: Literal['pending', 'deciding', 'approved', 'dismissed', 'cancelled', 'expired']
    action: Literal['create', 'edit', 'status']
    candidate: EventCandidate | None
    target_id: UUID | None
    target_revision: int | None
    status: EventStatus | None
    uncertainty: str
    quote: str
    source_date: datetime
    conversation_id: UUID
    expires_at: datetime
    event_id: UUID | None
    workflow_version: Literal['event-confirmation-v1'] = 'event-confirmation-v1'

class EventAdmission(Contract):
    supported: bool
    first_party: bool
    actual_event: bool
    complete_unambiguous: bool
    timezone_supported: bool
    confidence: float = Field(ge=0,le=1)
