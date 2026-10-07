from sqlalchemy import Table, Column, Text, Double, Integer, BigInteger, Identity, ForeignKey, ForeignKeyConstraint, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from .common import metadata, identifier, timestamp

learning_evidence = Table('learning_evidence', metadata,
    identifier(primary_key=True), identifier('learner_id'), Column('concept_id', Text, ForeignKey('concept.id'), nullable=False),
    identifier('context_id', nullable=True), Column('source_type', Text, nullable=False), Column('source_id', Text),
    Column('result', Text, nullable=False), Column('score', Double), Column('max_score', Double),
    Column('difficulty', Double), Column('independence', Double), Column('hint_count', Integer, nullable=False),
    Column('attempt_number', Integer), Column('evidence_confidence', Double, nullable=False), Column('extraction_confidence', Double),
    timestamp('occurred_at'), timestamp('created_at'), Column('metadata_json', JSONB, nullable=False),
    identifier('supersedes_evidence_id', nullable=True), Column('item_id', Text), Column('session_id', Text),
    Column('item_revision', Integer, nullable=False, server_default='1'),
    UniqueConstraint('learner_id','id'),
    ForeignKeyConstraint(['learner_id','context_id'], ['learning_context.learner_id','learning_context.id']),
    ForeignKeyConstraint(['learner_id','supersedes_evidence_id'], ['learning_evidence.learner_id','learning_evidence.id']),
    CheckConstraint("result IN ('CORRECT','PARTIAL','INCORRECT','UNKNOWN')", name='result'),
    CheckConstraint("source_type IN ('CHAT','QUIZ','MOCK_EXAM','HANDWRITTEN_ASSESSMENT','EXERCISE','CALIBRATION','MANUAL_CONFIRMATION')", name='source_type'),
    CheckConstraint("(score IS NULL AND max_score IS NULL) OR (score IS NOT NULL AND max_score IS NOT NULL AND score >= 0 AND max_score > 0 AND score <= max_score AND max_score < 'Infinity'::float8)", name='scores'),
    CheckConstraint("score IS NULL OR result='UNKNOWN' OR (result='CORRECT' AND score=max_score) OR (result='INCORRECT' AND score=0) OR (result='PARTIAL' AND score>0 AND score<max_score)", name='score_result'),
    *[CheckConstraint(f'{name} BETWEEN 0 AND 1', name=name) for name in
      ('difficulty','independence','evidence_confidence','extraction_confidence')],
    CheckConstraint('hint_count >= 0 AND (attempt_number IS NULL OR attempt_number >= 1) AND item_revision >= 1', name='attempts'),
    Index('idx_learning_evidence_learner_concept_time','learner_id','concept_id','occurred_at'),
    Index('idx_learning_evidence_provenance','source_type','source_id'),
    Index('idx_evidence_item','learner_id','item_id','concept_id','source_type','occurred_at'),
    Index('idx_evidence_session','learner_id','session_id','concept_id'),
)
Index('uq_learning_evidence_source', learning_evidence.c.learner_id, learning_evidence.c.source_type,
      learning_evidence.c.source_id, learning_evidence.c.concept_id, unique=True,
      postgresql_where=learning_evidence.c.source_id.is_not(None))

evidence_decision = Table('evidence_decision', metadata,
    Column('sequence', BigInteger, Identity(), primary_key=True), identifier('learner_id'),
    identifier('evidence_id'), Column('status', Text, nullable=False), Column('reason', Text, nullable=False),
    timestamp('decided_at'), timestamp('confirmed_at', nullable=True), Column('confirmation_source', Text),
    UniqueConstraint('evidence_id'), ForeignKeyConstraint(['learner_id','evidence_id'], ['learning_evidence.learner_id','learning_evidence.id']),
    CheckConstraint("status IN ('ACCEPTED','PENDING','REJECTED','SUPERSEDED')", name='status'),
    Index('idx_decision_learner_status','learner_id','status','sequence'),
)
misconception = Table('misconception', metadata,
    identifier(primary_key=True), identifier('learner_id'), Column('concept_id', Text, ForeignKey('concept.id'), nullable=False),
    identifier('context_id', nullable=True), Column('description', Text, nullable=False),
    Column('normalized_description', Text, nullable=False), Column('confidence', Double, nullable=False),
    Column('status', Text, nullable=False), timestamp('first_observed_at'), timestamp('last_observed_at'), timestamp('resolved_at', nullable=True),
    ForeignKeyConstraint(['learner_id','context_id'], ['learning_context.learner_id','learning_context.id']),
    UniqueConstraint('learner_id','concept_id','normalized_description'),
    CheckConstraint("status IN ('ACTIVE','RESOLVED')", name='status'), CheckConstraint('confidence BETWEEN 0 AND 1', name='confidence'),
    Index('idx_misconception_learner_concept','learner_id','concept_id','status'),
)
learner_audit = Table('learner_audit', metadata,
    Column('id', BigInteger, Identity(), primary_key=True), identifier('learner_id', nullable=True),
    Column('concept_id', Text, ForeignKey('concept.id')), Column('action', Text, nullable=False),
    Column('details_json', JSONB, nullable=False), timestamp('created_at'),
    Index('idx_learner_audit_subject','learner_id','concept_id','id'),
)
