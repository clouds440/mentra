from sqlalchemy import Table, Column, Text, Double, Integer, Boolean, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from .common import metadata, identifier, timestamp

learner_concept_state = Table('learner_concept_state', metadata,
    identifier('learner_id', primary_key=True), Column('concept_id', Text, ForeignKey('concept.id'), primary_key=True),
    Column('mastery', Double), Column('estimate_confidence', Double), Column('retention_confidence', Double),
    Column('evidence_count', Integer, nullable=False, server_default='0'),
    Column('independent_successes', Integer, nullable=False, server_default='0'),
    Column('hint_dependency', Double), Column('difficulty_tested', Double),
    timestamp('last_evidence_at', nullable=True), timestamp('last_verified_at', nullable=True),
    timestamp('last_demonstrated_at', nullable=True), timestamp('updated_at'),
    Column('version', Integer, nullable=False), Column('policy_data_json', JSONB, nullable=False, server_default='{}'),
    Column('mastery_policy_version', Text, nullable=False, server_default='legacy'),
    Column('retention_policy_version', Text, nullable=False, server_default='legacy'),
    Column('verification_required', Boolean, nullable=False, server_default='false'),
    *[CheckConstraint(f'{name} BETWEEN 0 AND 1', name=name) for name in
      ('mastery','estimate_confidence','retention_confidence','hint_dependency','difficulty_tested')],
    CheckConstraint('evidence_count >= 0 AND independent_successes >= 0', name='counts'),
    CheckConstraint('version >= 1', name='version'), Index('idx_learner_state_learner','learner_id','updated_at'),
)
