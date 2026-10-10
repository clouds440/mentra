from sqlalchemy import Table, Column, Uuid, Text, Integer, DateTime, ForeignKeyConstraint, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata

jobs=Table('chat_evidence_job',metadata,
    Column('log_context',JSONB,nullable=True),
    Column('turn_id',Uuid(as_uuid=False),primary_key=True),Column('learner_id',Uuid(as_uuid=False),nullable=False),
    Column('attempt',Integer,nullable=False),Column('state',Text,nullable=False),Column('attempts',Integer,nullable=False),
    Column('created_at',DateTime(timezone=True),nullable=False),Column('retry_at',DateTime(timezone=True)),
    Column('claim_id',Uuid(as_uuid=False)),Column('claim_until',DateTime(timezone=True)),Column('receipt',JSONB),
    ForeignKeyConstraint(['learner_id','turn_id'],['chat_turn.learner_id','chat_turn.id'],ondelete='CASCADE'),
    CheckConstraint("attempt > 0 AND attempts BETWEEN 0 AND 3 AND state IN ('queued','running','applied','ignored','failed')",name='chat_evidence_job_state'),
    Index('idx_chat_evidence_queue','state','retry_at','claim_until'))
