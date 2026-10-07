from sqlalchemy import select, case, func
from sqlalchemy.dialects.postgresql import insert

from app.learner.normalization import normalize
from app.learner.repositories.tables import learning_context as contexts, context_concept as links
from .base import PostgresRepositoryBase, utcnow
from app.core.identifiers import canonical_learner_id


class ContextsStore(PostgresRepositoryBase):
    def get_context(self, learner_id, context_id):
        def read():
            with self._session() as session:
                return self._context_from_row(session.execute(select(contexts).where(
                    contexts.c.learner_id == learner_id, contexts.c.id == context_id)).mappings().first())
        return self._remember('context', (learner_id, context_id), read, learner_id=learner_id)

    def find_context(self, learner_id, normalized_name):
        with self._session() as session:
            return self._context_from_row(session.execute(select(contexts).where(
                contexts.c.learner_id == learner_id, contexts.c.normalized_name == normalized_name)).mappings().first())

    def list_for_learner(self, learner_id):
        order = case((contexts.c.status == 'ACTIVE', 0), (contexts.c.status == 'RELATED', 1),
                     (contexts.c.status == 'DORMANT', 2), else_=3)
        with self._session() as session:
            return [self._context_from_row(row) for row in session.execute(select(contexts).where(
                contexts.c.learner_id == learner_id).order_by(order, contexts.c.last_activity_at.desc(), contexts.c.id)).mappings()]

    def save_context(self, value):
        now = utcnow()
        values = self._owned_values(value)
        values.update(name=value.name.strip(), normalized_name=normalize(value.name), last_activity_at=value.last_activity_at or now,
                      activated_at=now if value.status == 'ACTIVE' else None, dormant_at=now if value.status == 'DORMANT' else None,
                      archived_at=now if value.status == 'ARCHIVED' else None)
        stmt = insert(contexts).values(**values)
        updates = {key: stmt.excluded[key] for key in ('name','normalized_name','description','status','relevance_score','last_activity_at')}
        updates.update({key: func.coalesce(stmt.excluded[key], contexts.c[key]) for key in ('activated_at','dormant_at','archived_at')})
        with self._session() as session:
            result = session.execute(stmt.on_conflict_do_update(index_elements=['id'], set_=updates,
                    where=contexts.c.learner_id == stmt.excluded.learner_id).returning(contexts.c.id)).first()
            if result is None:
                raise ValueError('Learning context belongs to another learner')
            if self._cache_allowed(value.learner_id):
                self._read_cache[('context', (canonical_learner_id(value.learner_id), value.id))] = self._context_from_row(values)

    def add_context_concept(self, context_id, concept_id, *, learner_id):
        key = (canonical_learner_id(learner_id), context_id, concept_id)
        if self._cache_allowed(learner_id) and key in self._context_links:
            return
        with self._session() as session:
            context = self.get_context(learner_id, context_id)
            if context is None:
                raise ValueError('Learning context not found for learner')
            session.execute(insert(links).values(context_id=context_id, concept_id=concept_id, learner_id=context.learner_id).on_conflict_do_nothing())
            if self._cache_allowed(learner_id):
                self._context_links.add(key)

    def set_context_goal(self, context_id, concept_id, importance, target_difficulty, *, learner_id):
        with self._session() as session:
            owner = session.execute(select(contexts.c.learner_id).where(contexts.c.id == context_id, contexts.c.learner_id == learner_id)).scalar_one()
            stmt = insert(links).values(context_id=context_id, concept_id=concept_id, learner_id=owner,
                                       importance=importance, target_difficulty=target_difficulty)
            session.execute(stmt.on_conflict_do_update(index_elements=['context_id','concept_id'],
                set_=dict(importance=importance, target_difficulty=target_difficulty)))

    def get_concept_context_ids(self, concept_id, *, learner_id):
        with self._session() as session:
            return list(session.execute(select(links.c.context_id).where(links.c.concept_id == concept_id, links.c.learner_id == learner_id)).scalars())
