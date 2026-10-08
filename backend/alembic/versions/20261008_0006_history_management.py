from sqlalchemy import Table, Column, Text, BigInteger, Boolean, DateTime, Uuid, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, func, literal_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import MetaData
metadata = MetaData(naming_convention={'ix':'ix_%(table_name)s_%(column_0_name)s','uq':'uq_%(table_name)s_%(column_0_name)s','ck':'ck_%(table_name)s_%(constraint_name)s','fk':'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s','pk':'pk_%(table_name)s'})
Table('learner', metadata, Column('id', Uuid(as_uuid=False), primary_key=True))


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

from alembic import op
from sqlalchemy.schema import CreateTable, CreateIndex
revision = '20261008_0006'
down_revision = '20261008_0005'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public')
    # Build existing-history indexes before new tables, outside the transaction.
    # A failed/cancelled concurrent build can be retried without partial memory
    # tables or a long write-blocking chat_message lock.
    with op.get_context().autocommit_block():
        from sqlalchemy import text
        for name, expression in [('idx_chat_history_fts', "to_tsvector('simple', content)"), ('idx_chat_history_trgm', 'content public.gin_trgm_ops')]:
            valid = op.get_bind().execute(text('SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname=:name AND n.nspname=current_schema()'), {'name':name}).scalar()
            if valid is False:
                op.execute(f'DROP INDEX CONCURRENTLY {name}')
            op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON chat_message USING gin ({expression})')
    for table in TABLES:
        op.get_bind().execute(CreateTable(table))
        for index in table.indexes:
            op.get_bind().execute(CreateIndex(index))


def downgrade():
    op.drop_index('idx_chat_history_trgm', table_name='chat_message')
    op.drop_index('idx_chat_history_fts', table_name='chat_message')
    for table in reversed(TABLES):
        op.drop_table(table.name)
    # pg_trgm may be shared with other schemas/features; never remove it here.
