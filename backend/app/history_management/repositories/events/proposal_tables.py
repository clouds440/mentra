from sqlalchemy import Table, Column, Uuid, Text, DateTime, BigInteger, Integer, ForeignKeyConstraint, CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata

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
