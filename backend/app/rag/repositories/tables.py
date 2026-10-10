"""PostgreSQL metadata with composite ownership constraints."""
from sqlalchemy import Table, Column, Text, Integer, Boolean, DateTime, Uuid, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, func, literal_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata
from app.learner.repositories.tables import learning_context


def owner():
    return Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False)


def owned_parent(parent, child_fields, parent_fields):
    return ForeignKeyConstraint(['learner_id', *child_fields], [f'{parent}.learner_id', *[f'{parent}.{f}' for f in parent_fields]])


documents = Table('rag_document', metadata,
    Column('id', Text, primary_key=True), owner(), Column('title', Text, nullable=False),
    Column('filename', Text, nullable=False), Column('context_ids', JSONB, nullable=False),
    Column('concept_ids', JSONB, nullable=False, server_default='[]'),
    Column('archived', Boolean, nullable=False), Column('deleted_at', DateTime(timezone=True)),
    Column('purged_at', DateTime(timezone=True)), Column('active_generation_id', Text),
    Column('revision', Integer, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False), Column('last_used_at', DateTime(timezone=True)),
    UniqueConstraint('learner_id', 'id'), CheckConstraint('revision >= 1', name='revision'),
    CheckConstraint("jsonb_array_length(context_ids) BETWEEN 1 AND 20", name='contexts'),
    Index('idx_rag_document_owner', 'learner_id', 'created_at', 'id'))

associations = Table('rag_document_context', metadata,
    owner(), Column('document_id', Text, primary_key=True), Column('context_id', Text, primary_key=True),
    owned_parent('rag_document', ['document_id'], ['id']),
    ForeignKeyConstraint(['learner_id', 'context_id'], ['learning_context.learner_id', 'learning_context.id']))

versions = Table('rag_document_version', metadata,
    Column('id', Text, primary_key=True), owner(), Column('document_id', Text, nullable=False),
    Column('file_hash', Text, nullable=False), Column('media_type', Text, nullable=False),
    Column('size_bytes', Integer, nullable=False), Column('storage_key', Text, nullable=False),
    Column('filename', Text, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('extracted_content', JSONB),
    owned_parent('rag_document', ['document_id'], ['id']), UniqueConstraint('learner_id', 'document_id', 'id'),
    CheckConstraint('size_bytes > 0', name='size'))

generations = Table('rag_generation', metadata,
    Column('id', Text, primary_key=True), owner(), Column('document_id', Text, nullable=False),
    Column('version_id', Text, nullable=False), Column('state', Text, nullable=False),
    Column('config', JSONB, nullable=False), Column('warnings', JSONB, nullable=False),
    Column('chunk_count', Integer, nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('indexed_at', DateTime(timezone=True)), Column('reconciled_at', DateTime(timezone=True)),
    owned_parent('rag_document_version', ['document_id', 'version_id'], ['document_id', 'id']),
    UniqueConstraint('learner_id', 'document_id', 'id'),
    CheckConstraint("state IN ('PENDING','PROCESSING','READY','FAILED','SUPERSEDED')", name='state'),
    Index('idx_rag_generation_cleanup', 'state', 'reconciled_at', 'created_at'))

documents.append_constraint(ForeignKeyConstraint(
    ['learner_id', 'id', 'active_generation_id'],
    ['rag_generation.learner_id', 'rag_generation.document_id', 'rag_generation.id'],
    use_alter=True, name='fk_rag_document_active_generation', deferrable=True, initially='DEFERRED'))

chunks = Table('rag_chunk', metadata,
    Column('id', Text, primary_key=True), owner(), Column('document_id', Text, nullable=False),
    Column('generation_id', Text, nullable=False), Column('ordinal', Integer, nullable=False),
    Column('content', Text, nullable=False), Column('content_hash', Text, nullable=False),
    Column('heading_path', JSONB, nullable=False), Column('spans', JSONB, nullable=False),
    Column('token_count', Integer, nullable=False), Column('concept_ids', JSONB, nullable=False),
    owned_parent('rag_generation', ['document_id', 'generation_id'], ['document_id', 'id']),
    UniqueConstraint('generation_id', 'ordinal'), Index('idx_rag_chunk_generation', 'learner_id', 'generation_id'))

Index('idx_rag_chunk_lexical', func.to_tsvector(literal_column("'simple'::regconfig"), chunks.c.content), postgresql_using='gin')

chunk_concepts = Table('rag_chunk_concept', metadata,
    Column('chunk_id', Text, ForeignKey('rag_chunk.id', ondelete='CASCADE'), primary_key=True),
    Column('concept_id', Text, ForeignKey('concept.id'), primary_key=True))

document_concepts = Table('rag_document_concept', metadata,
    Column('document_id', Text, ForeignKey('rag_document.id'), primary_key=True),
    Column('concept_id', Text, ForeignKey('concept.id'), primary_key=True))

jobs = Table('rag_job', metadata,
    Column('log_context', JSONB, nullable=True),
    Column('id', Text, primary_key=True), owner(), Column('document_id', Text, nullable=False),
    Column('generation_id', Text), Column('operation', Text, nullable=False), Column('state', Text, nullable=False),
    Column('idempotency_key', Text, nullable=False), Column('request_hash', Text, nullable=False),
    Column('expected_revision', Integer, nullable=False), Column('attempts', Integer, nullable=False),
    Column('stage', Text, nullable=False), Column('error', Text), Column('lease_token', Text),
    Column('lease_until', DateTime(timezone=True)), Column('next_attempt_at', DateTime(timezone=True), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('updated_at', DateTime(timezone=True), nullable=False),
    owned_parent('rag_document', ['document_id'], ['id']),
    owned_parent('rag_generation', ['document_id', 'generation_id'], ['document_id', 'id']),
    UniqueConstraint('learner_id', 'idempotency_key'),
    CheckConstraint("operation IN ('INGEST','DELETE','RECONCILE')", name='operation'),
    CheckConstraint("state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','FAILED','CANCELLED')", name='state'),
    Index('idx_rag_job_due', 'state', 'next_attempt_at', 'lease_until'))
