"""Frozen event proposals and pinned PostgresSaver schema."""
from alembic import op
revision = "20261009_0011"
down_revision = "20261009_0010"
branch_labels = depends_on = None
from sqlalchemy import Table, Column, Text, Integer, LargeBinary, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import MetaData
metadata = MetaData(naming_convention={'ix': 'ix_%(table_name)s_%(column_0_name)s', 'uq': 'uq_%(table_name)s_%(column_0_name)s', 'ck': 'ck_%(table_name)s_%(constraint_name)s', 'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s', 'pk': 'pk_%(table_name)s'})

migrations = Table('checkpoint_migrations', metadata, Column('v', Integer, primary_key=True))
checkpoints = Table('checkpoints', metadata,
    Column('thread_id', Text, primary_key=True), Column('checkpoint_ns', Text, primary_key=True, server_default=''),
    Column('checkpoint_id', Text, primary_key=True), Column('parent_checkpoint_id', Text), Column('type', Text),
    Column('checkpoint', JSONB, nullable=False), Column('metadata', JSONB, nullable=False, server_default='{}'),
    Index('checkpoints_thread_id_idx', 'thread_id'))
blobs = Table('checkpoint_blobs', metadata,
    Column('thread_id', Text, primary_key=True), Column('checkpoint_ns', Text, primary_key=True, server_default=''),
    Column('channel', Text, primary_key=True), Column('version', Text, primary_key=True),
    Column('type', Text, nullable=False), Column('blob', LargeBinary), Index('checkpoint_blobs_thread_id_idx', 'thread_id'))
writes = Table('checkpoint_writes', metadata,
    Column('thread_id', Text, primary_key=True), Column('checkpoint_ns', Text, primary_key=True, server_default=''),
    Column('checkpoint_id', Text, primary_key=True), Column('task_id', Text, primary_key=True), Column('idx', Integer, primary_key=True),
    Column('channel', Text, nullable=False), Column('type', Text), Column('blob', LargeBinary, nullable=False),
    Column('task_path', Text, nullable=False, server_default=''), Index('checkpoint_writes_thread_id_idx', 'thread_id'))

from sqlalchemy import Table, Column, Uuid, Text, DateTime, BigInteger, Integer, ForeignKeyConstraint, CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy import UniqueConstraint
Table('chat_conversation', metadata, Column('learner_id', Uuid(as_uuid=False)), Column('id', Uuid(as_uuid=False)), UniqueConstraint('learner_id', 'id'))

proposals = Table('hm_event_proposal', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True),
    Column('learner_id', Uuid(as_uuid=False), nullable=False),
    Column('conversation_id', Uuid(as_uuid=False), nullable=False),
    Column('message_id', Uuid(as_uuid=False), nullable=False),
    Column('turn_id', Uuid(as_uuid=False), nullable=False), Column('attempt', Integer, nullable=False),
    Column('fingerprint', Text, nullable=False), Column('payload', JSONB, nullable=False),
    Column('quote', Text, nullable=False), Column('source_date', DateTime(timezone=True), nullable=False),
    Column('source_timezone', Text), Column('workflow_version', Text, nullable=False),
    Column('state', Text, nullable=False), Column('revision', BigInteger, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('expires_at', DateTime(timezone=True), nullable=False),
    Column('decision', JSONB), Column('claim_id', Uuid(as_uuid=False)), Column('claim_until', DateTime(timezone=True)),
    Column('event_id', Uuid(as_uuid=False)),
    UniqueConstraint('learner_id', 'fingerprint'),
    ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
    CheckConstraint("state IN ('pending','deciding','approved','dismissed','cancelled','expired') AND revision >= 1 AND attempt >= 1", name='event_proposal_state'),
    CheckConstraint('length(quote) BETWEEN 1 AND 500 AND length(fingerprint) = 64', name='event_proposal_bounds'),
    Index('idx_event_proposal_owner', 'learner_id', 'state', 'created_at'),
    Index('idx_event_proposal_source', 'learner_id', 'conversation_id'))

TABLES = (migrations, checkpoints, blobs, writes, proposals)

def upgrade():
    for table in TABLES: table.create(op.get_bind())
    op.get_bind().execute(migrations.insert(), [{"v":v} for v in range(10)])

def downgrade():
    for table in reversed(TABLES): table.drop(op.get_bind())
