from sqlalchemy import Table, Column, Text, Double, ForeignKey, ForeignKeyConstraint, CheckConstraint, UniqueConstraint, Index
from .common import metadata, identifier, timestamp

learning_context = Table('learning_context', metadata,
    identifier(primary_key=True), identifier('learner_id'), Column('name', Text, nullable=False),
    Column('normalized_name', Text, nullable=False), Column('description', Text), Column('status', Text, nullable=False),
    Column('relevance_score', Double), timestamp('created_at'), timestamp('last_activity_at'),
    timestamp('activated_at', nullable=True), timestamp('dormant_at', nullable=True), timestamp('archived_at', nullable=True),
    UniqueConstraint('learner_id','id', name='uq_learning_context_learner_identity'),
    UniqueConstraint('learner_id','normalized_name', name='uq_learning_context_learner_name'),
    CheckConstraint("status IN ('ACTIVE','RELATED','DORMANT','ARCHIVED')", name='status'),
    CheckConstraint('relevance_score BETWEEN 0 AND 1', name='relevance'),
    Index('idx_learning_context_learner_status', 'learner_id','status','last_activity_at'),
)
context_concept = Table('context_concept', metadata,
    identifier('context_id', primary_key=True), Column('concept_id', Text, ForeignKey('concept.id'), primary_key=True),
    identifier('learner_id'), timestamp('created_at'),
    Column('importance', Double, nullable=False, server_default='0.5'),
    Column('target_difficulty', Double, nullable=False, server_default='0.5'),
    ForeignKeyConstraint(['learner_id','context_id'], ['learning_context.learner_id','learning_context.id']),
    CheckConstraint('importance BETWEEN 0 AND 1', name='importance'),
    CheckConstraint('target_difficulty BETWEEN 0 AND 1', name='target_difficulty'),
    Index('idx_context_concept_concept','concept_id','context_id'), Index('idx_context_concept_learner','learner_id','concept_id'),
)
