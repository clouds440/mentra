from sqlalchemy import Table, Column, Text, BigInteger, Boolean, DateTime, Uuid, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, func, literal_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata
from app.auth.repositories.tables import learner


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
memories.append_constraint(Index('idx_hm_memory_fts', func.to_tsvector(literal_column("'simple'"), memories.c.content), postgresql_using='gin'))
Index('idx_hm_memory_trgm', memories.c.content, postgresql_using='gin', postgresql_ops={'content': 'public.gin_trgm_ops'})
