from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.learner.exceptions import LearnerError
from app.learner.repositories.tables import learner_concept_state as states
from .base import PostgresRepositoryBase, utcnow
from app.core.identifiers import canonical_learner_id


class StatesStore(PostgresRepositoryBase):
    def get_state(self, learner_id, concept_id):
        def read():
            with self._session() as session:
                return self._state_from_row(session.execute(select(states).where(
                    states.c.learner_id == learner_id, states.c.concept_id == concept_id)).mappings().first())
        return self._remember('state', (learner_id, concept_id), read, learner_id=learner_id)

    def save_state(self, state):
        values = self._owned_values(state)
        values['policy_data_json'] = values.pop('policy_data')
        values['updated_at'] = utcnow()
        stmt = insert(states).values(**values)
        with self._session() as session:
            saved = session.execute(stmt.on_conflict_do_update(index_elements=['learner_id','concept_id'],
                set_={key: stmt.excluded[key] for key in values if key not in ('learner_id','concept_id')},
                where=stmt.excluded.version == states.c.version + 1).returning(states.c.version)).first()
            if saved is None:
                raise LearnerError('Concurrent learner state version conflict; recompute from current state')
            if self._cache_allowed(state.learner_id):
                self._read_cache[('state', (canonical_learner_id(state.learner_id), state.concept_id))] = state

    def list_states(self, learner_id):
        with self._session() as session:
            return [self._state_from_row(row) for row in session.execute(select(states).where(
                states.c.learner_id == learner_id).order_by(states.c.updated_at.desc())).mappings()]

    def states_for_concepts(self, learner_id, concept_ids):
        with self._session() as session:
            return {row['concept_id']: self._state_from_row(row) for row in session.execute(select(states).where(
                states.c.learner_id == learner_id, states.c.concept_id.in_(concept_ids))).mappings()}
