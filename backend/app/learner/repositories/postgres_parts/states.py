from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.learner.exceptions import LearnerError
from app.learner.repositories.tables import learner_concept_state as states
from .base import PostgresRepositoryBase, utcnow
from app.core.identifiers import canonical_learner_id


class StatesStore(PostgresRepositoryBase):
    def rebuild_ranking_projection(self,owner,after_id='',limit=256):
        """Replace derived rows from CURRENT state, without replaying/changing beliefs."""
        from ..tables.projections import ranking_projection
        from app.learner.scoring.projection import project
        with self.transaction(learner_ids=[owner]) as repository:
            session=repository._active_session
            rows=list(session.execute(select(states).where(states.c.learner_id==owner,states.c.concept_id>after_id)
                .order_by(states.c.concept_id).limit(min(256,max(1,limit)))).mappings())
            rebuilt=0
            for row in rows:
                state=self._state_from_row(row);half_life=state.policy_data.get('ranking_half_life')
                value=project(state,half_life) if half_life else None
                if not value:continue
                stmt=insert(ranking_projection).values(learner_id=owner,concept_id=state.concept_id,state_version=state.version,**value)
                session.execute(stmt.on_conflict_do_update(index_elements=['learner_id','concept_id'],
                    set_={key:stmt.excluded[key] for key in value|{'state_version':state.version}}));rebuilt+=1
            return dict(scanned=len(rows),rebuilt=rebuilt,skipped=len(rows)-rebuilt,next_cursor=rows[-1]['concept_id'] if len(rows)==min(256,max(1,limit)) else None)

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
            from ..tables.projections import ranking_projection
            from app.learner.scoring.projection import project
            from sqlalchemy import delete
            half_life = state.policy_data.get('ranking_half_life')
            projection = project(state, half_life) if half_life else None
            if projection:
                indexed = insert(ranking_projection).values(learner_id=state.learner_id,
                    concept_id=state.concept_id, state_version=state.version, **projection)
                session.execute(indexed.on_conflict_do_update(index_elements=['learner_id','concept_id'],
                    set_={key: indexed.excluded[key] for key in projection | {'state_version':state.version}}))
            else:
                session.execute(delete(ranking_projection).where(ranking_projection.c.learner_id==state.learner_id,
                    ranking_projection.c.concept_id==state.concept_id))
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
