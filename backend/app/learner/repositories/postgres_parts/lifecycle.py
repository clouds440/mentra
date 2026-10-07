"""Ontology changes preserve immutable evidence and every learner's ownership."""

from uuid import uuid4
from sqlalchemy import select, update, delete, or_, func, case
from sqlalchemy.dialects.postgresql import insert
from app.learner.repositories.tables import concept, concept_alias as aliases, concept_relation as relations, concept_redirect as redirects, context_concept as links, learning_evidence as evidence, misconception as misconceptions, learner_concept_state as states
from .base import PostgresRepositoryBase, utcnow


class LifecycleStore(PostgresRepositoryBase):
    def copy_parent_contexts(self, parent_id, child_id):
        """Trusted ontology split: preserve each original link's owner and defaults."""
        with self._session() as session:
            for row in session.execute(select(links.c.context_id, links.c.learner_id).where(links.c.concept_id == parent_id)).mappings().all():
                session.execute(insert(links).values(**dict(row), concept_id=child_id).on_conflict_do_nothing())

    def merge_identity(self, source_id, target_id):
        with self._session() as session:
            old_ids = [source_id, target_id, *session.execute(select(redirects.c.source_id).where(redirects.c.target_id.in_([source_id, target_id]))).scalars()]
            learners = list(session.execute(select(evidence.c.learner_id).where(evidence.c.concept_id.in_(old_ids)).distinct()).scalars())
            session.execute(insert(redirects).values(source_id=source_id, target_id=target_id))
            session.execute(update(redirects).where(redirects.c.target_id == source_id).values(target_id=target_id))
            session.execute(update(concept).where(concept.c.id == source_id).values(status='INACTIVE', updated_at=utcnow()))
            for row in session.execute(select(aliases).where(aliases.c.concept_id == source_id)).mappings().all():
                values = dict(row, id=str(uuid4()), concept_id=target_id, source='concept_merge')
                stmt = insert(aliases).values(**values)
                session.execute(stmt.on_conflict_do_update(index_elements=['concept_id','normalized_alias'],
                    set_={'confidence': func.greatest(aliases.c.confidence, stmt.excluded.confidence)}))
            for row in session.execute(select(links).where(links.c.concept_id == source_id)).mappings().all():
                stmt = insert(links).values(**dict(row, concept_id=target_id))
                session.execute(stmt.on_conflict_do_update(index_elements=['context_id','concept_id'], set_=dict(
                    importance=func.greatest(links.c.importance, stmt.excluded.importance),
                    target_difficulty=func.greatest(links.c.target_difficulty, stmt.excluded.target_difficulty))))
            affected = or_(relations.c.source_concept_id == source_id, relations.c.target_concept_id == source_id)
            rows = session.execute(select(relations).where(affected)).mappings().all()
            session.execute(delete(relations).where(affected))
            for row in rows:
                values = dict(row)
                for key in ('source_concept_id','target_concept_id'):
                    if values[key] == source_id:
                        values[key] = target_id
                if values['source_concept_id'] != values['target_concept_id']:
                    stmt = insert(relations).values(**values)
                    session.execute(stmt.on_conflict_do_update(index_elements=['source_concept_id','target_concept_id','relation_type'],
                        set_={'confidence': func.greatest(relations.c.confidence, stmt.excluded.confidence)}))
            for row in session.execute(select(misconceptions).where(misconceptions.c.concept_id == source_id)).mappings().all():
                stmt = insert(misconceptions).values(**dict(row, id=str(uuid4()), concept_id=target_id))
                session.execute(stmt.on_conflict_do_update(index_elements=['learner_id','concept_id','normalized_description'], set_=dict(
                    confidence=func.greatest(misconceptions.c.confidence, stmt.excluded.confidence),
                    status=case((or_(misconceptions.c.status == 'ACTIVE', stmt.excluded.status == 'ACTIVE'), 'ACTIVE'), else_='RESOLVED'))))
            session.execute(delete(states).where(states.c.concept_id == source_id))
            self._read_cache.clear()
            self._context_links.clear()
        return learners

    def resolve_misconception(self, learner_id, misconception_id):
        with self._session() as session:
            row = session.execute(select(misconceptions).where(misconceptions.c.learner_id == learner_id, misconceptions.c.id == misconception_id)).mappings().first()
            if not row:
                return False
            canonical = self.canonical_id(row['concept_id'])
            ids = select(redirects.c.source_id).where(redirects.c.target_id == canonical)
            result = session.execute(update(misconceptions).where(misconceptions.c.learner_id == learner_id,
                misconceptions.c.normalized_description == row['normalized_description'],
                or_(misconceptions.c.concept_id == canonical, misconceptions.c.concept_id.in_(ids))).values(status='RESOLVED', resolved_at=utcnow()))
            return result.rowcount > 0
