from sqlalchemy import Table, Column, Text, Double, Integer, ForeignKey, ForeignKeyConstraint, CheckConstraint, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from .common import metadata, identifier, timestamp

concept = Table('concept', metadata,
    identifier(primary_key=True), Column('canonical_name', Text, nullable=False),
    Column('normalized_name', Text, nullable=False, unique=True), Column('description', Text),
    Column('status', Text, nullable=False, server_default='ACTIVE'),
    timestamp('created_at'), timestamp('updated_at'),
    CheckConstraint("status IN ('ACTIVE','INACTIVE')", name='status'),
)
concept_alias = Table('concept_alias', metadata,
    identifier(primary_key=True), Column('concept_id', Text, ForeignKey('concept.id'), nullable=False),
    Column('alias', Text, nullable=False), Column('normalized_alias', Text, nullable=False),
    Column('source', Text, nullable=False), Column('confidence', Double, nullable=False), timestamp('created_at'),
    UniqueConstraint('concept_id', 'normalized_alias'), CheckConstraint('confidence BETWEEN 0 AND 1', name='confidence'),
    Index('idx_concept_alias_normalized', 'normalized_alias'),
)
concept_relation = Table('concept_relation', metadata,
    identifier(primary_key=True), Column('source_concept_id', Text, ForeignKey('concept.id'), nullable=False),
    Column('target_concept_id', Text, ForeignKey('concept.id'), nullable=False),
    Column('relation_type', Text, nullable=False), Column('confidence', Double, nullable=False), timestamp('created_at'),
    UniqueConstraint('source_concept_id', 'target_concept_id', 'relation_type'),
    CheckConstraint("relation_type IN ('PARENT_OF','PREREQUISITE_OF','RELATED_TO')", name='type'),
    CheckConstraint('source_concept_id != target_concept_id', name='distinct_concepts'),
    CheckConstraint('confidence BETWEEN 0 AND 1', name='confidence'),
    Index('idx_concept_relation_source', 'source_concept_id', 'relation_type'),
    Index('idx_concept_relation_target', 'target_concept_id', 'relation_type'),
)
concept_redirect = Table('concept_redirect', metadata,
    Column('source_id', Text, ForeignKey('concept.id'), primary_key=True),
    Column('target_id', Text, ForeignKey('concept.id'), nullable=False), timestamp('created_at'),
    CheckConstraint('source_id != target_id', name='distinct_concepts'), Index('idx_redirect_target', 'target_id'),
)
candidate_concept = Table('candidate_concept', metadata,
    identifier(primary_key=True), Column('proposed_name', Text, nullable=False),
    Column('normalized_name', Text, nullable=False), identifier('learner_id', nullable=True), identifier('context_id', nullable=True),
    timestamp('first_seen_at'), timestamp('last_seen_at'),
    Column('occurrence_count', Integer, nullable=False, server_default='1'),
    Column('resolution_status', Text, nullable=False, server_default='UNRESOLVED'),
    Column('resolved_concept_id', Text, ForeignKey('concept.id')), Column('metadata_json', JSONB, nullable=False),
    ForeignKeyConstraint(['learner_id','context_id'], ['learning_context.learner_id','learning_context.id']),
    CheckConstraint('context_id IS NULL OR learner_id IS NOT NULL', name='owner_scope'),
    CheckConstraint('occurrence_count > 0', name='occurrence_count'),
    CheckConstraint("resolution_status IN ('UNRESOLVED','PROMOTED','MERGED','DISCARDED')", name='status'),
)
Index('uq_candidate_concept_name_context', candidate_concept.c.learner_id, candidate_concept.c.normalized_name,
      func.coalesce(candidate_concept.c.context_id, ''), unique=True,
      postgresql_where=candidate_concept.c.learner_id.is_not(None))
Index('uq_candidate_concept_global_name', candidate_concept.c.normalized_name, unique=True,
      postgresql_where=candidate_concept.c.learner_id.is_(None))
