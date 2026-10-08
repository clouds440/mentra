from sqlalchemy import Table, Column, Text, BigInteger, Integer, DateTime, Uuid, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import MetaData
metadata = MetaData(naming_convention={
    'ix': 'ix_%(table_name)s_%(column_0_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
})
Table('learner', metadata, Column('id', Uuid(as_uuid=False), primary_key=True))


def owner(primary_key=False):
    return Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False, primary_key=primary_key)


conversations = Table('chat_conversation', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('title', Text, nullable=False), Column('selection', JSONB, nullable=False),
    Column('revision', BigInteger, nullable=False), Column('message_count', BigInteger, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('updated_at', DateTime(timezone=True), nullable=False),
    Column('deleted_at', DateTime(timezone=True)), UniqueConstraint('learner_id', 'id'),
    CheckConstraint('revision >= 1 AND message_count >= 0', name='chat_revision'),
    Index('idx_chat_recent', 'learner_id', 'updated_at', 'id'))

messages = Table('chat_message', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('conversation_id', Uuid(as_uuid=False), nullable=False), Column('sequence', BigInteger, nullable=False),
    Column('role', Text, nullable=False), Column('content', Text, nullable=False),
    Column('metadata', JSONB, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
    UniqueConstraint('conversation_id', 'sequence'), CheckConstraint('sequence > 0', name='chat_sequence'),
    CheckConstraint("role IN ('user', 'assistant', 'tool')", name='chat_role'),
    Index('idx_chat_messages_owner', 'learner_id', 'conversation_id', 'sequence'))

turns = Table('chat_turn', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('conversation_id', Uuid(as_uuid=False), nullable=False), Column('request_hash', Text, nullable=False),
    Column('user_sequence', BigInteger, nullable=False), Column('assistant_sequence', BigInteger),
    Column('state', Text, nullable=False), Column('error', Text), Column('attempt', Integer, nullable=False),
    Column('lease_until', DateTime(timezone=True)), Column('selection', JSONB, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
    CheckConstraint("state IN ('RUNNING','SUCCEEDED','FAILED')", name='chat_turn_state'),
    Index('idx_chat_turn_active', 'learner_id', 'conversation_id', 'state'))

sync_state = Table('chat_sync_state', metadata, owner(True),
    Column('revision', BigInteger, nullable=False), Column('floor', BigInteger, nullable=False),
    CheckConstraint('revision >= 0 AND floor >= 0 AND floor <= revision', name='chat_sync_revision'))

changes = Table('chat_change', metadata, owner(True), Column('revision', BigInteger, primary_key=True),
    Column('conversation_id', Uuid(as_uuid=False), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    CheckConstraint('revision > 0', name='chat_change_revision'))

TABLES = (conversations, messages, turns, sync_state, changes)

from alembic import op
from sqlalchemy.schema import CreateTable, CreateIndex
revision = '20261008_0005'
down_revision = '20261008_0004'
branch_labels = None
depends_on = None


def upgrade():
    for table in TABLES:
        op.get_bind().execute(CreateTable(table))
        for index in table.indexes:
            op.get_bind().execute(CreateIndex(index))


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table.name)
