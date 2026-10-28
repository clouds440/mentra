from sqlalchemy import Table, Column, Uuid, Text, BigInteger, DateTime, Integer, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, Boolean
from sqlalchemy.dialects.postgresql import JSONB, ENUM
from app.db.metadata import metadata

assistance_kind = ENUM('unknown', 'independent', 'assisted', name='assessment_assistance_kind', create_type=False)

practice_operations = Table('assessment_practice_operation', metadata,
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
    Column('operation_id', Uuid(as_uuid=False), primary_key=True),
    Column('assessment_id', Uuid(as_uuid=False), nullable=False), Column('fingerprint', Text, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False))

assessments = Table('assessment', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False),
    Column('context_id', Text, nullable=False), Column('title', Text, nullable=False), Column('purpose', Text, nullable=False),
    Column('revision', BigInteger, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('questions', JSONB, nullable=False), Column('sources', JSONB, nullable=False), Column('paper', JSONB),
    Column('preferences', JSONB, nullable=False, server_default='{}'),
    Column('practice_lineage', JSONB(none_as_null=True)),
    Column('operation_id', Uuid(as_uuid=False), nullable=False), Column('fingerprint', Text, nullable=False),
    UniqueConstraint('learner_id', 'id'), UniqueConstraint('learner_id', 'operation_id', name='uq_assessment_owner_operation'),
    ForeignKeyConstraint(['learner_id', 'context_id'], ['learning_context.learner_id', 'learning_context.id']),
    CheckConstraint("revision >= 1 AND purpose IN ('practice','verification','calibration')", name='assessment_revision'),
    Index('idx_assessment_owner', 'learner_id', 'created_at'))

attempts = Table('assessment_attempt', metadata,
    Column('log_context', JSONB, nullable=True),
    Column('id', Uuid(as_uuid=False), primary_key=True), Column('learner_id', Uuid(as_uuid=False), nullable=False),
    Column('assessment_id', Uuid(as_uuid=False), nullable=False), Column('operation_id', Uuid(as_uuid=False), nullable=False),
    Column('attempt_number', Integer, nullable=False), Column('revision', BigInteger, nullable=False),
    Column('state', Text, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('submitted_at', DateTime(timezone=True)), Column('answers', JSONB, nullable=False), Column('grades', JSONB),
    Column('extraction', JSONB), Column('source_file_id', Uuid(as_uuid=False)), Column('filename', Text),
    Column('submission_id', Uuid(as_uuid=False)), Column('submission_hash', Text),
    Column('grading_progress', JSONB, nullable=False, server_default='{}'),
    Column('retry_request_id', Uuid(as_uuid=False)),
    Column('manual_retries', Integer, nullable=False, server_default='0'),
    Column('claim_id', Uuid(as_uuid=False)), Column('claim_until', DateTime(timezone=True)),
    Column('worker_attempts', Integer, nullable=False), Column('retry_at', DateTime(timezone=True)), Column('error', Text),
    Column('evidence_status', Text, nullable=False), Column('evidence_receipt', JSONB),
    Column('grade_revision', Integer, nullable=False, server_default='1'),
    Column('grade_history', JSONB, nullable=False, server_default='[]'),
    Column('assistance', assistance_kind, nullable=False, server_default='unknown'),
    Column('reported_assistance', assistance_kind, nullable=False, server_default='unknown'),
    Column('scoring', JSONB),
    Column('profile_context_version', BigInteger),
    Column('start_fingerprint', Text),
    Column('chat_inputs', JSONB, nullable=False, server_default='{}'),
    ForeignKeyConstraint(['learner_id', 'assessment_id'], ['assessment.learner_id', 'assessment.id'], ondelete='CASCADE'),
    UniqueConstraint('learner_id', 'operation_id'),
    ForeignKeyConstraint(['learner_id', 'source_file_id'], ['file_asset.learner_id', 'file_asset.id']),
    UniqueConstraint('learner_id','id',name='uq_assessment_attempt_owner_id'),
    CheckConstraint("revision >= 1 AND attempt_number >= 1 AND worker_attempts BETWEEN 0 AND 3 AND state IN ('draft','pending_transcription','submitted','grading','graded','failed')", name='assessment_attempt_state'),
    CheckConstraint("evidence_status IN ('pending','applied','partial','unavailable','none')", name='assessment_evidence_state'),
    CheckConstraint("assistance IN ('unknown','independent','assisted')", name='assessment_assistance'),
    Index('idx_assessment_grading_queue', 'state', 'retry_at', 'claim_until'),
    Index('idx_assessment_attempt_owner', 'learner_id', 'assessment_id'))

evidence_jobs = Table('assessment_evidence_job', metadata,
    Column('attempt_id', Uuid(as_uuid=False), ForeignKey('assessment_attempt.id', ondelete='CASCADE'), primary_key=True),
    Column('grade_revision', Integer, primary_key=True),
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), nullable=False),
    Column('state', Text, nullable=False), Column('attempts', Integer, nullable=False, server_default='0'),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('retry_at', DateTime(timezone=True)),
    Column('claim_id', Uuid(as_uuid=False)), Column('claim_until', DateTime(timezone=True)),
    CheckConstraint("state IN ('queued','running','applied','skipped','failed') AND attempts BETWEEN 0 AND 3 AND grade_revision >= 1", name='assessment_evidence_job_state'),
    Index('idx_assessment_evidence_queue', 'state', 'retry_at', 'claim_until'))

generation_claims = Table('assessment_generation_claim', metadata,
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
    Column('operation_id', Uuid(as_uuid=False), primary_key=True),
    Column('claim_id', Uuid(as_uuid=False), nullable=False),
    Column('fingerprint', Text, nullable=False),
    Column('claim_until', DateTime(timezone=True), nullable=False))

chat_drafts = Table('chat_assessment_draft', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True),
    Column('learner_id', Uuid(as_uuid=False), nullable=False),
    Column('conversation_id', Uuid(as_uuid=False), nullable=False),
    Column('operation_id', Uuid(as_uuid=False), nullable=False),
    Column('assessment_id', Uuid(as_uuid=False)),
    Column('payload', JSONB, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
    UniqueConstraint('learner_id', 'operation_id'), Index('idx_chat_assessment_recent', 'learner_id', 'conversation_id', 'created_at'))

preferences = Table('assessment_preferences', metadata,
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
    Column('auto_add', Boolean, nullable=False, server_default='false'),
    Column('revision', BigInteger, nullable=False), CheckConstraint('revision >= 1', name='assessment_preferences_revision'))

generation_jobs = Table('assessment_generation_job', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True),
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), nullable=False),
    Column('operation_id', Uuid(as_uuid=False), nullable=False), Column('fingerprint', Text, nullable=False),
    Column('conversation_id', Uuid(as_uuid=False)), Column('request', JSONB, nullable=False),
    Column('source_turn_id', Uuid(as_uuid=False)),
    Column('revision', Integer, nullable=False, server_default='1'), Column('resume_until', DateTime(timezone=True)),
    Column('state', Text, nullable=False), Column('progress', JSONB, nullable=False), Column('result', JSONB),
    Column('error', Text), Column('attempts', Integer, nullable=False), Column('claim_id', Uuid(as_uuid=False)),
    Column('claim_until', DateTime(timezone=True)), Column('created_at', DateTime(timezone=True), nullable=False),
    UniqueConstraint('learner_id', 'operation_id'),
    ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
    ForeignKeyConstraint(['learner_id', 'source_turn_id'], ['chat_turn.learner_id', 'chat_turn.id'], name='fk_generation_source_turn', ondelete='CASCADE'),
    CheckConstraint("state IN ('queued','running','completed','failed','stopped')", name='assessment_generation_job_state'),
    Index('idx_generation_stopped_expiry', 'state', 'resume_until'),
    Index('idx_assessment_generation_queue', 'state', 'created_at'))
