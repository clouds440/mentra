"""Content-free quota records and a separate size-bounded, owner-scoped result cache."""
from sqlalchemy import Table, Column, Text, Uuid, DateTime, ForeignKey, Index, CheckConstraint
from app.db.metadata import metadata
from sqlalchemy.dialects.postgresql import JSONB

guard = Table('web_search_guard', metadata,
    Column('provider', Text, primary_key=True),
)
calls = Table('web_search_call', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True),
    Column('provider', Text, ForeignKey('web_search_guard.provider'), nullable=False),
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='SET NULL')),
    Column('reserved_at', DateTime(timezone=True), nullable=False),
    Column('state', Text, nullable=False),
    CheckConstraint("state IN ('reserved', 'sent', 'completed', 'unknown', 'released')", name='state'),
    Index('idx_web_search_window', 'provider', 'reserved_at'),
    Index('idx_web_search_owner_window', 'learner_id', 'reserved_at'),
)
cache = Table('web_search_cache', metadata,
    Column('id', Text, primary_key=True),
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), nullable=False),
    Column('cached_at', DateTime(timezone=True), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False),
    Column('payload', JSONB, nullable=False),
    CheckConstraint('octet_length(payload::text) <= 32768', name='payload_size'),
    Index('idx_web_search_cache_expiry', 'expires_at'),
)
