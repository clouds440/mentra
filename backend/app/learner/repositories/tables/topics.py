"""Owned topic membership; canonical skill/evidence IDs remain unchanged."""
from sqlalchemy import Table, Column, Text, Integer, Boolean, ForeignKeyConstraint, UniqueConstraint, Index
from .common import metadata, identifier, timestamp

learning_topic = Table('learning_topic', metadata,
    identifier(primary_key=True), identifier('learner_id'), identifier('context_id'),
    Column('name', Text, nullable=False), Column('normalized_name', Text, nullable=False),
    Column('scope_key', Text, nullable=False),
    Column('scope', Text, nullable=False), Column('revision', Integer, nullable=False, server_default='1'),
    timestamp('created_at'),
    UniqueConstraint('learner_id', 'id', name='uq_learning_topic_owner_identity'),
    UniqueConstraint('learner_id', 'context_id', 'normalized_name', 'scope_key', name='uq_learning_topic_context_name'),
    ForeignKeyConstraint(['learner_id', 'context_id'], ['learning_context.learner_id', 'learning_context.id']),
    Index('idx_learning_topic_owner', 'learner_id', 'context_id', 'normalized_name'))

topic_skill = Table('topic_skill', metadata,
    identifier('learner_id', primary_key=True), identifier('concept_id', primary_key=True),
    identifier('topic_id', nullable=True), Column('label', Text, nullable=False), Column('ability', Text, nullable=False),
    Column('published', Boolean, nullable=False, server_default='false'),
    Column('phrases', Text, nullable=False, server_default=''),
    Column('resolver_version', Text, nullable=False), timestamp('created_at'),
    ForeignKeyConstraint(['learner_id', 'topic_id'], ['learning_topic.learner_id', 'learning_topic.id']),
    ForeignKeyConstraint(['concept_id'], ['concept.id']),
    Index('idx_topic_skill_parent', 'learner_id', 'topic_id', 'published'))

skill_resolution_binding = Table('skill_resolution_binding', metadata,
    identifier('learner_id', primary_key=True), identifier('context_id', primary_key=True),
    Column('subject_key', Text, primary_key=True), Column('label_key', Text, primary_key=True),
    identifier('concept_id'), identifier('topic_id'), timestamp('created_at'),
    ForeignKeyConstraint(['learner_id','context_id'], ['learning_context.learner_id','learning_context.id'], ondelete='CASCADE'),
    ForeignKeyConstraint(['learner_id','concept_id'], ['topic_skill.learner_id','topic_skill.concept_id'], ondelete='CASCADE'),
    ForeignKeyConstraint(['learner_id','topic_id'], ['learning_topic.learner_id','learning_topic.id'], ondelete='CASCADE'))
