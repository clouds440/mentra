from sqlalchemy import Table, Column, Text, BigInteger, Boolean, DateTime, Uuid, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, func, literal_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata
from app.auth.repositories.tables import learner  # noqa: F401 - Register the referenced learner table.


def owner(primary_key=False):
    return Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False, primary_key=primary_key)


memories = Table('hm_memory', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('content', Text, nullable=False), Column('fingerprint', Text, nullable=False),
    Column('category', Text, nullable=False), Column('status', Text, nullable=False),
    Column('origin', Text, nullable=False), Column('revision', BigInteger, nullable=False),
    Column('conflicts', JSONB, nullable=False),
    Column('pinned', Boolean, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False), Column('confirmed_at', DateTime(timezone=True)),
    Column('expires_at', DateTime(timezone=True)), UniqueConstraint('learner_id', 'id'),
    UniqueConstraint('learner_id', 'fingerprint', name='uq_hm_memory_fingerprint'),
    CheckConstraint("status IN ('active','pending','conflict')", name='memory_status'),
    CheckConstraint("category IN ('preference','fact','goal')", name='memory_category'),
    CheckConstraint('revision >= 1 AND length(content) BETWEEN 1 AND 500', name='memory_bounds'),
    Index('idx_hm_memory_recent', 'learner_id', 'updated_at', 'id'))

evidence = Table('hm_memory_evidence', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('memory_id', Uuid(as_uuid=False), nullable=False),
    # Source IDs are deliberately snapshots, not FKs into destructible chat rows.
    Column('conversation_id', Uuid(as_uuid=False)), Column('message_id', Uuid(as_uuid=False)),
    Column('quote', Text, nullable=False), Column('source_date', DateTime(timezone=True), nullable=False),
    Column('source_deleted', Boolean, nullable=False), Column('explicit_consent', Boolean, nullable=False),
    ForeignKeyConstraint(['learner_id', 'memory_id'], ['hm_memory.learner_id', 'hm_memory.id'], ondelete='CASCADE'),
    Index('idx_hm_evidence_source', 'learner_id', 'conversation_id'))

revisions = Table('hm_memory_revision', metadata, owner(True),
    Column('memory_id', Uuid(as_uuid=False), primary_key=True), Column('revision', BigInteger, primary_key=True),
    Column('actor', Text, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(['learner_id', 'memory_id'], ['hm_memory.learner_id', 'hm_memory.id'], ondelete='CASCADE'))

preferences = Table('hm_preferences', metadata, owner(True), Column('automatic_memory', Boolean, nullable=False),
    Column('revision', BigInteger, nullable=False))

suppression = Table('hm_suppression', metadata, owner(True), Column('fingerprint', Text, primary_key=True),
    Column('created_at', DateTime(timezone=True), nullable=False))

receipts = Table('hm_tool_receipt', metadata, owner(True), Column('operation_key', Text, primary_key=True),
    Column('turn_id', Uuid(as_uuid=False)), Column('conversation_id', Uuid(as_uuid=False)),
    Column('memory_id', Uuid(as_uuid=False)), Column('outcome', Text, nullable=False),
    Column('request_hash', Text, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Index('idx_hm_receipt_source', 'learner_id', 'conversation_id'))

TABLES = (memories, evidence, revisions, preferences, suppression, receipts)

summary_state = Table('hm_memory_summary_state', metadata,
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
    Column('source_revision', BigInteger, nullable=False, server_default='0'),
    Column('published_source_revision', BigInteger, nullable=False, server_default='0'),
    Column('summary_revision', BigInteger, nullable=False, server_default='0'),
    Column('blocks', JSONB, nullable=False, server_default='[]'),
    Column('prompt_version', Text, nullable=False, server_default=''),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('reconciled_at', DateTime(timezone=True)),
    Column('reconciled_revision', BigInteger, nullable=False, server_default='0'),
    Column('next_expiry_at', DateTime(timezone=True)),
    CheckConstraint('source_revision >= published_source_revision AND published_source_revision >= 0 AND summary_revision >= 0', name='memory_summary_revisions'),
    CheckConstraint("jsonb_typeof(blocks) = 'array' AND octet_length(blocks::text) <= 32768", name='memory_summary_blocks'),
    Index('idx_memory_summary_expiry', 'next_expiry_at'))

summary_changes = Table('hm_memory_summary_change', metadata,
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('hm_memory_summary_state.learner_id', ondelete='CASCADE'), primary_key=True),
    Column('source_revision', BigInteger, primary_key=True),
    Column('memory_id', Uuid(as_uuid=False), nullable=False),
    Column('after', JSONB),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint('source_revision > 0', name='memory_summary_change_revision'))

summary_jobs = Table('hm_memory_summary_job', metadata,
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('hm_memory_summary_state.learner_id', ondelete='CASCADE'), primary_key=True),
    Column('available_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('queued_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('lease_token', Uuid(as_uuid=False)), Column('lease_until', DateTime(timezone=True)),
    Column('attempts', BigInteger, nullable=False, server_default='0'),
    Column('failed', Boolean, nullable=False, server_default='false'), Column('error_code', Text),
    Column('rebuild', Boolean, nullable=False, server_default='false'),
    Column('checkpoint', JSONB, nullable=False, server_default='{}'),
    CheckConstraint('attempts >= 0 AND ((lease_token IS NULL) = (lease_until IS NULL))', name='memory_summary_lease'),
    CheckConstraint('octet_length(checkpoint::text) <= 32768', name='memory_summary_checkpoint'),
    Index('idx_memory_summary_claim', 'failed', 'available_at', 'lease_until'))

TABLES = (*TABLES, summary_state, summary_changes, summary_jobs)
memories.append_constraint(Index('idx_hm_memory_fts', func.to_tsvector(literal_column("'simple'"), memories.c.content), postgresql_using='gin'))
Index('idx_hm_memory_trgm', memories.c.content, postgresql_using='gin', postgresql_ops={'content': 'public.gin_trgm_ops'})

# Quiet capture jobs contain source pointers only, never unvalidated candidate text.
capture_jobs = Table('hm_memory_capture_job', metadata,
    Column('message_id', Uuid(as_uuid=False), ForeignKey('chat_message.id', ondelete='CASCADE'), primary_key=True), owner(),
    Column('conversation_id', Uuid(as_uuid=False), nullable=False),
    Column('turn_id', Uuid(as_uuid=False), ForeignKey('chat_turn.id', ondelete='CASCADE'), nullable=False),
    Column('source_attempt', BigInteger, nullable=False), Column('preference_revision', BigInteger, nullable=False),
    Column('content_offset', BigInteger, nullable=False, server_default='0'),
    Column('queued_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('available_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('lease_token', Uuid(as_uuid=False)), Column('lease_until', DateTime(timezone=True)),
    Column('attempts', BigInteger, nullable=False, server_default='0'),
    Column('failed', Boolean, nullable=False, server_default='false'), Column('error_code', Text),
    Column('completed_at', DateTime(timezone=True)),
    ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
    CheckConstraint('content_offset >= 0 AND attempts >= 0 AND source_attempt >= 1 AND preference_revision >= 1', name='memory_capture_bounds'),
    CheckConstraint('(lease_token IS NULL) = (lease_until IS NULL)', name='memory_capture_lease'),
    Index('idx_memory_capture_claim', 'completed_at', 'failed', 'available_at', 'lease_until'))
