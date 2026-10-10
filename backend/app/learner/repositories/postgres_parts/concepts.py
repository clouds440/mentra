from uuid import uuid4

from sqlalchemy import select, update, or_, func, literal_column
from sqlalchemy.dialects.postgresql import insert

from app.learner.normalization import normalize
from .base import PostgresRepositoryBase, utcnow
from app.learner.repositories.tables import concept, concept_alias, concept_relation, concept_redirect, candidate_concept, learning_context


class ConceptsStore(PostgresRepositoryBase):
    def get_concept(self, concept_id):
        def read():
            with self._session() as session:
                return self._concept_from_row(session.execute(select(concept).where(concept.c.id == concept_id)).mappings().first())
        return self._remember('concept', concept_id, read)

    def get_concept_by_normalized_name(self, normalized_name):
        with self._session() as session:
            return self._concept_from_row(session.execute(select(concept).where(
                concept.c.normalized_name == normalized_name, concept.c.status == 'ACTIVE')).mappings().first())

    def find_by_normalized_alias(self, normalized_alias, min_confidence=0.9):
        with self._session() as session:
            rows = session.execute(select(concept, func.lower(concept.c.canonical_name).label('name_order')).join(concept_alias).where(
                concept_alias.c.normalized_alias == normalized_alias, concept_alias.c.confidence >= min_confidence,
                concept.c.status == 'ACTIVE').distinct().order_by(func.lower(concept.c.canonical_name))).mappings()
            return [self._concept_from_row(row) for row in rows]

    def list_concepts(self, limit=500):
        with self._session() as session:
            return [self._concept_from_row(row) for row in session.execute(select(concept).where(
                concept.c.status == 'ACTIVE').order_by(func.lower(concept.c.canonical_name)).limit(limit)).mappings()]

    def search_concepts(self, normalized_query, limit=20):
        aliases = select(concept_alias.c.concept_id).where(concept_alias.c.normalized_alias.contains(normalized_query, autoescape=True))
        with self._session() as session:
            return [self._concept_from_row(row) for row in session.execute(select(concept).where(
                concept.c.status == 'ACTIVE', or_(concept.c.normalized_name.contains(normalized_query, autoescape=True),
                                                concept.c.id.in_(aliases))).order_by(concept.c.canonical_name).limit(limit)).mappings()]

    def create_concept(self, value):
        with self._session() as session:
            session.execute(insert(concept).values(id=value.id, canonical_name=value.canonical_name.strip(),
                          normalized_name=normalize(value.canonical_name), description=value.description))
            self._read_cache.pop(('concept', value.id), None)

    def add_alias(self, concept_id, alias, normalized_alias, source, confidence):
        stmt = insert(concept_alias).values(id=str(uuid4()), concept_id=concept_id, alias=alias,
                                           normalized_alias=normalized_alias, source=source, confidence=confidence)
        with self._session() as session:
            session.execute(stmt.on_conflict_do_update(index_elements=['concept_id','normalized_alias'],
                set_=dict(alias=stmt.excluded.alias, source=stmt.excluded.source,
                          confidence=func.greatest(concept_alias.c.confidence, stmt.excluded.confidence))))

    def add_relation(self, source_concept_id, target_concept_id, relation_type, confidence):
        stmt = insert(concept_relation).values(id=str(uuid4()), source_concept_id=source_concept_id,
                    target_concept_id=target_concept_id, relation_type=relation_type, confidence=confidence)
        with self._session() as session:
            session.execute(stmt.on_conflict_do_update(index_elements=['source_concept_id','target_concept_id','relation_type'],
                            set_={'confidence': func.greatest(concept_relation.c.confidence, stmt.excluded.confidence)}))

    def list_related_concepts(self, concept_id, relation_type=None, limit=20, min_confidence=0):
        filters = [concept_relation.c.confidence >= min_confidence]
        if relation_type:
            filters.append(concept_relation.c.relation_type == relation_type)
        related = select(concept_relation.c.target_concept_id.label('id')).where(
            concept_relation.c.source_concept_id == concept_id, *filters).union(select(concept_relation.c.source_concept_id).where(
            concept_relation.c.target_concept_id == concept_id, *filters)).subquery()
        with self._session() as session:
            return [self._concept_from_row(row) for row in session.execute(select(concept).join(related, related.c.id == concept.c.id).where(
                concept.c.status == 'ACTIVE').order_by(func.lower(concept.c.canonical_name)).limit(limit)).mappings()]

    def canonical_id(self, concept_id):
        def read():
            with self._session() as session:
                return session.execute(select(concept_redirect.c.target_id).where(concept_redirect.c.source_id == concept_id)).scalar_one_or_none() or concept_id
        return self._remember('canonical', concept_id, read)

    def save_candidate(self, candidate_id, proposed_name, normalized_name, context_id, metadata, *, learner_id):
        with self._session() as session:
            stmt = insert(candidate_concept).values(id=candidate_id, proposed_name=proposed_name, normalized_name=normalized_name,
                       learner_id=learner_id, context_id=context_id, metadata_json=metadata)
            from sqlalchemy import case
            fields = [candidate_concept.c.normalized_name]
            if learner_id is not None:
                fields = [candidate_concept.c.learner_id, *fields,
                          func.coalesce(candidate_concept.c.context_id, literal_column("''"))]
            condition = candidate_concept.c.learner_id.is_not(None) if learner_id is not None else candidate_concept.c.learner_id.is_(None)
            return session.execute(stmt.on_conflict_do_update(index_elements=fields, index_where=condition, set_=dict(
                       proposed_name=stmt.excluded.proposed_name, last_seen_at=utcnow(), metadata_json=metadata,
                       occurrence_count=candidate_concept.c.occurrence_count + 1,
                       resolution_status=case((candidate_concept.c.resolution_status == 'DISCARDED', 'DISCARDED'), else_='UNRESOLVED'),
                       resolved_concept_id=None)).returning(candidate_concept.c.id)).scalar_one()

    def get_candidate(self, candidate_id, *, learner_id):
        with self._session() as session:
            row = session.execute(select(candidate_concept).where(candidate_concept.c.id == candidate_id,
                candidate_concept.c.learner_id == learner_id)).mappings().first()
            return dict(row) if row else None

    def get_candidate_for_review(self, candidate_id):
        """Trusted ontology curation only; unavailable from learner tools/routes."""
        with self._session() as session:
            row = session.execute(select(candidate_concept).where(candidate_concept.c.id == candidate_id)).mappings().first()
            return dict(row) if row else None

    def list_candidates(self, limit=100):
        with self._session() as session:
            return [dict(row) for row in session.execute(select(candidate_concept).where(candidate_concept.c.resolution_status == 'UNRESOLVED').order_by(
                candidate_concept.c.occurrence_count.desc(), candidate_concept.c.last_seen_at.desc()).limit(limit)).mappings()]

    def list_owned_candidates(self, learner_id, limit=20):
        with self._session() as session:
            return [dict(row) for row in session.execute(select(candidate_concept).where(
                candidate_concept.c.learner_id == learner_id, candidate_concept.c.resolution_status == 'UNRESOLVED')
                .order_by(candidate_concept.c.last_seen_at.desc(), candidate_concept.c.id).limit(limit)).mappings()]

    def resolve_candidate(self, candidate_id, resolution_status, concept_id=None):
        with self._session() as session:
            result = session.execute(update(candidate_concept).where(candidate_concept.c.id == candidate_id,
                candidate_concept.c.resolution_status == 'UNRESOLVED').values(resolution_status=resolution_status, resolved_concept_id=concept_id))
            if result.rowcount != 1:
                raise LookupError('Unresolved candidate not found')
