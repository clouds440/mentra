from sqlalchemy import (Table, Column, Text, BigInteger, Boolean, Date, DateTime,
                        Uuid, ForeignKey, ForeignKeyConstraint, UniqueConstraint,
                        CheckConstraint, Index)
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata
from app.auth.repositories.tables import learner


def owner(primary_key=False):
    return Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False, primary_key=primary_key)


events = Table('hm_event', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('title', Text, nullable=False), Column('description', Text, nullable=False),
    Column('kind', Text, nullable=False), Column('status', Text, nullable=False),
    Column('context_id', Text),
    Column('timezone', Text, nullable=False), Column('local_date', Date),
    Column('starts_at', DateTime(timezone=True)), Column('ends_at', DateTime(timezone=True)),
    Column('sort_at', DateTime(timezone=True), nullable=False), Column('cutoff_at', DateTime(timezone=True), nullable=False),
    Column('reminder_rule', JSONB, nullable=False), Column('origin', Text, nullable=False),
    Column('revision', BigInteger, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('updated_at', DateTime(timezone=True), nullable=False),
    Column('completed_at', DateTime(timezone=True)), UniqueConstraint('learner_id', 'id'),
    ForeignKeyConstraint(['learner_id', 'context_id'], ['learning_context.learner_id', 'learning_context.id']),
    CheckConstraint("kind IN ('quiz','exam','assignment','deadline','study','other')", name='event_kind'),
    CheckConstraint("status IN ('scheduled','completed','cancelled')", name='event_status'),
    CheckConstraint("origin IN ('manual','ai')", name='event_origin'),
    CheckConstraint('revision >= 1 AND length(title) BETWEEN 1 AND 200 AND length(description) <= 1000 AND length(timezone) BETWEEN 1 AND 100', name='event_bounds'),
    CheckConstraint('(local_date IS NOT NULL AND starts_at IS NULL AND ends_at IS NULL) OR (local_date IS NULL AND starts_at IS NOT NULL AND (ends_at IS NULL OR ends_at > starts_at))', name='event_temporal'),
    CheckConstraint('cutoff_at >= sort_at', name='event_cutoff'),
    CheckConstraint("COALESCE(jsonb_typeof(reminder_rule) = 'object' AND reminder_rule->>'mode' IN ('default','disabled','at') AND ((reminder_rule->>'mode' = 'at' AND jsonb_typeof(reminder_rule->'at') = 'string') OR (reminder_rule->>'mode' IN ('default','disabled') AND reminder_rule->'at' = 'null'::jsonb)), false)", name='event_reminder_rule'),
    CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name='event_completion'),
    Index('idx_hm_event_agenda', 'learner_id', 'status', 'sort_at', 'id'),
    Index('idx_hm_event_cutoff', 'learner_id', 'status', 'cutoff_at'))


def event_fk():
    return ForeignKeyConstraint(['learner_id', 'event_id'], ['hm_event.learner_id', 'hm_event.id'], ondelete='CASCADE')


evidence = Table('hm_event_evidence', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(), Column('event_id', Uuid(as_uuid=False), nullable=False),
    Column('quote', Text, nullable=False), Column('source_date', DateTime(timezone=True), nullable=False),
    Column('source_timezone', Text, nullable=False), Column('source_deleted', Boolean, nullable=False),
    # Destructible source identities are snapshots, not restricting chat FKs.
    Column('conversation_id', Uuid(as_uuid=False)), Column('message_id', Uuid(as_uuid=False)),
    Column('policy_version', Text, nullable=False), event_fk(),
    CheckConstraint('length(quote) BETWEEN 1 AND 500 AND length(source_timezone) BETWEEN 1 AND 100', name='event_evidence_bounds'),
    Index('idx_hm_event_evidence_source', 'learner_id', 'conversation_id'))

revisions = Table('hm_event_revision', metadata, owner(True),
    Column('event_id', Uuid(as_uuid=False), primary_key=True), Column('revision', BigInteger, primary_key=True),
    Column('actor', Text, nullable=False), Column('changed_fields', JSONB, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False), event_fk(),
    CheckConstraint('revision >= 1', name='event_revision_bounds'))

preferences = Table('hm_event_preferences', metadata, owner(True),
    Column('automatic_events', Boolean, nullable=False), Column('reminders_enabled', Boolean, nullable=False),
    Column('timezone', Text), Column('timed_offset_minutes', BigInteger, nullable=False),
    Column('date_days_before', BigInteger, nullable=False), Column('date_hour', BigInteger, nullable=False),
    Column('date_minute', BigInteger, nullable=False), Column('revision', BigInteger, nullable=False),
    Column('disabled_since', DateTime(timezone=True)),
    CheckConstraint('revision >= 1 AND timed_offset_minutes BETWEEN 1 AND 43200 AND date_days_before BETWEEN 0 AND 30 AND date_hour BETWEEN 0 AND 23 AND date_minute BETWEEN 0 AND 59', name='event_preferences_bounds'))

receipts = Table('hm_event_receipt', metadata, owner(True),
    Column('operation_id', Uuid(as_uuid=False), primary_key=True), Column('request_hash', Text, nullable=False),
    Column('event_id', Uuid(as_uuid=False), nullable=False), Column('outcome', Text, nullable=False),
    Column('sync_revision', BigInteger, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    # Retained content-free outcome cannot restore a deleted event.
    CheckConstraint("length(request_hash) = 64 AND outcome IN ('saved','updated','deleted') AND sync_revision > 0", name='event_receipt_bounds'),
    Index('idx_hm_event_receipt_target', 'learner_id', 'event_id'))

suppression = Table('hm_event_suppression', metadata, owner(True),
    Column('fingerprint', Text, primary_key=True), Column('created_at', DateTime(timezone=True), nullable=False),
    CheckConstraint('length(fingerprint) = 64', name='event_suppression_bounds'))

reminders = Table('hm_event_reminder', metadata, owner(True),
    Column('event_id', Uuid(as_uuid=False), primary_key=True), Column('due_at', DateTime(timezone=True)),
    Column('schedule_version', BigInteger, nullable=False), Column('state', Text, nullable=False),
    Column('delivered_at', DateTime(timezone=True)), Column('receipt_id', Uuid(as_uuid=False)), event_fk(),
    CheckConstraint("state IN ('pending','skipped','cancelled','delivered') AND schedule_version >= 1", name='event_reminder_state'),
    CheckConstraint("(state = 'delivered') = (delivered_at IS NOT NULL) AND (state = 'delivered') = (receipt_id IS NOT NULL) AND (state <> 'pending' OR due_at IS NOT NULL)", name='event_reminder_delivery'),
    Index('idx_hm_event_reminder_due', 'state', 'due_at', 'learner_id'))

sync_state = Table('hm_event_sync', metadata, owner(True),
    Column('revision', BigInteger, nullable=False), Column('floor', BigInteger, nullable=False),
    CheckConstraint('revision >= 0 AND floor BETWEEN 0 AND revision', name='event_sync_bounds'))

changes = Table('hm_event_change', metadata, owner(True), Column('revision', BigInteger, primary_key=True),
    Column('entity', Text, nullable=False), Column('entity_id', Uuid(as_uuid=False)), Column('deleted', Boolean, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    CheckConstraint("revision > 0 AND entity IN ('event','preferences') AND ((entity = 'event' AND entity_id IS NOT NULL) OR (entity = 'preferences' AND entity_id IS NULL))", name='event_change_bounds'))

TABLES = (events, evidence, revisions, preferences, receipts, suppression, reminders, sync_state, changes)
