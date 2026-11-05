"""Coalesced durable learner maintenance; never stores source answer text."""
from sqlalchemy import Table, Column, Text, Integer, CheckConstraint, ForeignKeyConstraint, Index
from .common import metadata, identifier, timestamp

maintenance_jobs = Table('learner_maintenance_job', metadata,
    identifier('learner_id', primary_key=True), identifier('context_id', primary_key=True),
    Column('kind', Text, primary_key=True), Column('state', Text, nullable=False),
    Column('attempts', Integer, nullable=False, server_default='0'),
    Column('claim_id', Text), timestamp('claim_until', nullable=True), timestamp('retry_at', nullable=True),
    timestamp('created_at'), timestamp('updated_at'),
    CheckConstraint("kind IN ('organization','policy_replay') AND state IN ('queued','running','completed','failed') AND attempts BETWEEN 0 AND 3", name='learner_maintenance_state'),
    ForeignKeyConstraint(['learner_id', 'context_id'], ['learning_context.learner_id', 'learning_context.id'], ondelete='CASCADE'),
    Index('idx_learner_maintenance_queue', 'state', 'retry_at', 'claim_until', 'created_at'))
