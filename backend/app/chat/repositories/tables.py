from sqlalchemy import Table, Column, Text, BigInteger, Integer, DateTime, Uuid, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, func, literal_column, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata
from app.auth.repositories.tables import learner


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
    UniqueConstraint('learner_id', 'id'),
    Column('attachment_ids', JSONB, nullable=False, server_default='[]'),
    Index('idx_chat_turn_active', 'learner_id', 'conversation_id', 'state'))

sync_state = Table('chat_sync_state', metadata, owner(True),
    Column('revision', BigInteger, nullable=False), Column('floor', BigInteger, nullable=False),
    CheckConstraint('revision >= 0 AND floor >= 0 AND floor <= revision', name='chat_sync_revision'))

changes = Table('chat_change', metadata, owner(True), Column('revision', BigInteger, primary_key=True),
    Column('conversation_id', Uuid(as_uuid=False), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    CheckConstraint('revision > 0', name='chat_change_revision'))

TABLES = (conversations, messages, turns, sync_state, changes)
activity = Table('chat_activity', metadata,
    Column('learner_id', Uuid(as_uuid=False), nullable=False),
    Column('turn_id', Uuid(as_uuid=False), primary_key=True),
    ForeignKeyConstraint(['learner_id', 'turn_id'], ['chat_turn.learner_id', 'chat_turn.id'], ondelete='CASCADE'),
    Column('attempt', Integer, primary_key=True), Column('sequence', Integer, primary_key=True),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('payload', JSONB, nullable=False),
    CheckConstraint('attempt > 0 AND sequence > 0 AND sequence <= 256', name='chat_activity_sequence'),
    Index('idx_chat_activity_retention', 'learner_id', 'created_at'))
TABLES = (*TABLES, activity)
attachments = Table('chat_attachment', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), owner(),
    Column('conversation_id', Uuid(as_uuid=False)), Column('filename', Text, nullable=False),
    Column('data', LargeBinary, nullable=False), Column('extraction', JSONB),
    Column('library_result', JSONB), Column('extraction_error', Text),
    Column('size_bytes', BigInteger, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
    CheckConstraint('size_bytes > 0 AND size_bytes <= 26214400', name='chat_attachment_size'),
    Index('idx_chat_attachment_owner', 'learner_id', 'conversation_id'))
TABLES = (*TABLES, attachments)
messages.append_constraint(Index('idx_chat_history_fts', func.to_tsvector(literal_column("'simple'"), messages.c.content), postgresql_using='gin'))
Index('idx_chat_history_trgm', messages.c.content, postgresql_using='gin', postgresql_ops={'content': 'public.gin_trgm_ops'})
