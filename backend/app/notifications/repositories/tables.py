from sqlalchemy import Table, Column, Uuid, Text, Boolean, BigInteger, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata


def owner(primary_key=False):
    return Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False, primary_key=primary_key)


inbox = Table('notification_inbox', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('kind', Text, nullable=False), Column('title', Text, nullable=False), Column('body', Text, nullable=False),
    Column('target_kind', Text, nullable=False), Column('target_id', Uuid(as_uuid=False)),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('read_at', DateTime(timezone=True)),
    Column('dismissed_at', DateTime(timezone=True)), Column('revision', BigInteger, nullable=False),
    CheckConstraint('revision > 0 AND length(title) BETWEEN 1 AND 200 AND length(body) <= 1000', name='notification_bounds'),
    Index('idx_notification_owner', 'learner_id', 'created_at', 'id'),
    Index('idx_notification_unread', 'learner_id', 'read_at', 'dismissed_at'))

receipts = Table('notification_receipt', metadata, owner(True),
    Column('producer', Text, primary_key=True), Column('delivery_key', Text, primary_key=True),
    Column('notification_id', Uuid(as_uuid=False), nullable=False), Column('created_at', DateTime(timezone=True), nullable=False))

preferences = Table('notification_preferences', metadata, owner(True),
    Column('enabled', Boolean, nullable=False), Column('disabled_kinds', JSONB, nullable=False),
    Column('resume_after', DateTime(timezone=True)), Column('kind_resume_after', JSONB, nullable=False),
    Column('revision', BigInteger, nullable=False))

state = Table('notification_sync', metadata, owner(True), Column('revision', BigInteger, nullable=False),
    Column('floor', BigInteger, nullable=False))
changes = Table('notification_change', metadata, owner(True), Column('revision', BigInteger, primary_key=True),
    Column('notification_id', Uuid(as_uuid=False)), Column('deleted', Boolean, nullable=False))
TABLES = (inbox, receipts, preferences, state, changes)
