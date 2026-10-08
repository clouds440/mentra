from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

EventKind = Literal['quiz', 'exam', 'assignment', 'deadline', 'study', 'other']
EventStatus = Literal['scheduled', 'completed', 'cancelled']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


def validate_zone(value):
    if value is None:
        return value
    if value in {'localtime', 'posixrules'}:
        raise ValueError('Choose an explicit IANA timezone, not a host timezone key.')
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Choose a supported IANA timezone.') from None
    return value


def bounded_date(value):
    if value is not None and not 1900 <= value.year <= 2200:
        raise ValueError('Event dates must be between 1900 and 2200.')
    return value


class ReminderRule(Contract):
    mode: Literal['default', 'disabled', 'at'] = 'default'
    at: datetime | None = None

    _bounds = field_validator('at')(bounded_date)

    @model_validator(mode='after')
    def valid(self):
        if (self.mode == 'at') != (self.at is not None):
            raise ValueError('Only an explicit reminder accepts a delivery instant.')
        if self.at is not None and (self.at.tzinfo is None or self.at.utcoffset() is None):
            raise ValueError('Reminder delivery must include a UTC offset.')
        return self


class EventDraft(Contract):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=1000)
    kind: EventKind = 'other'
    context_id: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str = Field(min_length=1, max_length=100)
    local_date: date | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reminder: ReminderRule = Field(default_factory=ReminderRule)

    _zone = field_validator('timezone')(validate_zone)
    _bounds = field_validator('local_date', 'starts_at', 'ends_at')(bounded_date)

    @model_validator(mode='after')
    def temporal(self):
        if (self.local_date is None) == (self.starts_at is None):
            raise ValueError('Choose exactly one of a local date or a timed start.')
        for stamp in (self.starts_at, self.ends_at):
            if stamp is not None and (stamp.tzinfo is None or stamp.utcoffset() is None):
                raise ValueError('Timed events must include a UTC offset.')
        if self.ends_at is not None and (self.starts_at is None or self.ends_at.astimezone(timezone.utc) <= self.starts_at.astimezone(timezone.utc)):
            raise ValueError('End must follow a timed start.')
        return self


class EventCreate(EventDraft):
    client_request_id: UUID


class EventEdit(Contract):
    expected_revision: int = Field(ge=1)
    client_request_id: UUID
    # Full replacement of editable details keeps date-mode switches atomic.
    details: EventDraft | None = None
    status: EventStatus | None = None

    @model_validator(mode='after')
    def not_empty(self):
        if self.details is None and self.status is None:
            raise ValueError('Supply event details or a lifecycle status.')
        return self


class PreferencesEdit(Contract):
    expected_revision: int = Field(ge=0)
    automatic_events: bool | None = None
    reminders_enabled: bool | None = None
    timezone: str | None = Field(default=None, max_length=100)
    timed_offset_minutes: int | None = Field(default=None, ge=1, le=43200)
    date_days_before: int | None = Field(default=None, ge=0, le=30)
    date_hour: int | None = Field(default=None, ge=0, le=23)
    date_minute: int | None = Field(default=None, ge=0, le=59)

    _zone = field_validator('timezone')(validate_zone)

    @model_validator(mode='after')
    def changes(self):
        fields = self.model_fields_set - {'expected_revision'}
        if not fields:
            raise ValueError('Supply at least one preference.')
        if any(getattr(self, name) is None for name in fields - {'timezone'}):
            raise ValueError('Preferences cannot be null except the account timezone.')
        return self


class TemporalPreview(Contract):
    timezone: str = Field(min_length=1, max_length=100)
    local_date: date | None = None
    local_start: datetime | None = None
    local_end: datetime | None = None
    reminder: ReminderRule = Field(default_factory=ReminderRule)

    _zone = field_validator('timezone')(validate_zone)
    _bounds = field_validator('local_date', 'local_start', 'local_end')(bounded_date)

    @model_validator(mode='after')
    def local(self):
        if (self.local_date is None) == (self.local_start is None):
            raise ValueError('Choose a local date or a local start.')
        if self.local_end is not None and self.local_start is None:
            raise ValueError('A local end requires a timed start.')
        if any(value is not None and value.tzinfo is not None for value in (self.local_start, self.local_end)):
            raise ValueError('Preview local times must not contain a UTC offset.')
        return self


class TemporalChoice(Contract):
    starts_at: datetime | None
    ends_at: datetime | None
    reminder_due_at: datetime | None
    reminder_state: Literal['pending', 'skipped', 'cancelled']


class TemporalIssue(Contract):
    field: str
    code: str
    message: str


class TemporalPreviewResult(Contract):
    timezone: str
    local_date: date | None
    start_choices: list[datetime]
    end_choices: list[datetime]
    requires_choice: bool
    choices: list[TemporalChoice]
    field_errors: list[TemporalIssue]


class EventRecord(EventDraft):
    id: UUID
    status: EventStatus
    origin: Literal['manual', 'ai']
    revision: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    bucket: Literal['upcoming', 'in_progress', 'overdue', 'past', 'completed', 'cancelled']
    reminder_state: Literal['pending', 'skipped', 'cancelled', 'delivered']
    reminder_due_at: datetime | None
    reminder_delivered_at: datetime | None


class EventOutcome(Contract):
    outcome: Literal['saved', 'updated', 'deleted']
    event: EventRecord | None = None
    event_id: UUID
    sync_revision: int


class EventPage(Contract):
    items: list[EventRecord]
    next_cursor: str | None
    has_more: bool
    sync_revision: int
    server_time: datetime


class EventPreferences(Contract):
    automatic_events: bool
    reminders_enabled: bool
    timezone: str | None
    timed_offset_minutes: int
    date_days_before: int
    date_hour: int
    date_minute: int
    revision: int
    disabled_since: datetime | None
    sync_revision: int


class EventSummary(Contract):
    upcoming: int
    sync_revision: int
    server_time: datetime


class EventChange(Contract):
    revision: int
    entity: Literal['event', 'preferences']
    id: UUID | None
    deleted: bool
    event: EventRecord | None = None
    preferences: EventPreferences | None = None


class EventSync(Contract):
    items: list[EventChange]
    next_cursor: int
    has_more: bool
    reset: bool
    floor: int
    server_time: datetime


class EventEvidence(Contract):
    quote: str
    source_date: datetime
    source_timezone: str
    source_deleted: bool
    conversation_id: UUID | None
    message_id: UUID | None


class EventDetail(EventRecord):
    evidence: list[EventEvidence]
