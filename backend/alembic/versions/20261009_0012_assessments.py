"""Frozen canonical assessment and durable grading schema."""
from alembic import op
revision="20261009_0012"
down_revision="20261009_0011"
branch_labels=depends_on=None
from sqlalchemy import Table, Column, Uuid, Text, BigInteger, DateTime, Integer, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import MetaData
metadata = MetaData(naming_convention={'ix': 'ix_%(table_name)s_%(column_0_name)s', 'uq': 'uq_%(table_name)s_%(column_0_name)s', 'ck': 'ck_%(table_name)s_%(constraint_name)s', 'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s', 'pk': 'pk_%(table_name)s'})
Table('learner', metadata, Column('id', Uuid(as_uuid=False), primary_key=True))
Table('learning_context', metadata, Column('learner_id', Uuid(as_uuid=False)), Column('id', Text), UniqueConstraint('learner_id','id'))

assessments = Table('assessment', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False),
    Column('context_id', Text, nullable=False), Column('title', Text, nullable=False), Column('purpose', Text, nullable=False),
    Column('revision', BigInteger, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('questions', JSONB, nullable=False), Column('sources', JSONB, nullable=False),
    Column('operation_id', Uuid(as_uuid=False), nullable=False), Column('fingerprint', Text, nullable=False),
    UniqueConstraint('learner_id', 'id'), UniqueConstraint('learner_id', 'operation_id', name='uq_assessment_owner_operation'),
    ForeignKeyConstraint(['learner_id', 'context_id'], ['learning_context.learner_id', 'learning_context.id']),
    CheckConstraint("revision >= 1 AND purpose IN ('practice','verification','calibration')", name='assessment_revision'),
    Index('idx_assessment_owner', 'learner_id', 'created_at'))

attempts = Table('assessment_attempt', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), Column('learner_id', Uuid(as_uuid=False), nullable=False),
    Column('assessment_id', Uuid(as_uuid=False), nullable=False), Column('operation_id', Uuid(as_uuid=False), nullable=False),
    Column('attempt_number', Integer, nullable=False), Column('revision', BigInteger, nullable=False),
    Column('state', Text, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('submitted_at', DateTime(timezone=True)), Column('answers', JSONB, nullable=False), Column('grades', JSONB),
    Column('extraction', JSONB), Column('source', LargeBinary), Column('filename', Text),
    Column('submission_id', Uuid(as_uuid=False)), Column('submission_hash', Text),
    Column('claim_id', Uuid(as_uuid=False)), Column('claim_until', DateTime(timezone=True)),
    Column('worker_attempts', Integer, nullable=False), Column('retry_at', DateTime(timezone=True)), Column('error', Text),
    Column('evidence_status', Text, nullable=False), Column('evidence_receipt', JSONB),
    Column('grade_revision', Integer, nullable=False, server_default='1'),
    Column('grade_history', JSONB, nullable=False, server_default='[]'),
    ForeignKeyConstraint(['learner_id', 'assessment_id'], ['assessment.learner_id', 'assessment.id'], ondelete='CASCADE'),
    UniqueConstraint('learner_id', 'operation_id'),
    CheckConstraint("revision >= 1 AND attempt_number >= 1 AND worker_attempts BETWEEN 0 AND 3 AND state IN ('draft','pending_transcription','submitted','grading','graded','failed')", name='assessment_attempt_state'),
    CheckConstraint("evidence_status IN ('pending','applied','unavailable','none')", name='assessment_evidence_state'),
    Index('idx_assessment_grading_queue', 'state', 'retry_at', 'claim_until'),
    Index('idx_assessment_attempt_owner', 'learner_id', 'assessment_id'))


def upgrade():
    for table in (assessments, attempts): table.create(op.get_bind())

def downgrade():
    for table in (attempts, assessments): table.drop(op.get_bind())
