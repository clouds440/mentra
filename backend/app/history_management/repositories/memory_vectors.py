"""Owner-locked, revision-fenced local memory vectors; no inference under locks."""
from sqlalchemy import select, or_, delete
from sqlalchemy.dialects.postgresql import insert
from app.db.owner_transactions import lock_owner
from .tables import memories as m, memory_vectors as v, preferences as p


class MemoryVectorRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def missing(self, owner, key):
        with self.sessions() as session:
            return list(session.execute(select(m.c.id, m.c.revision, m.c.content).outerjoin(v,
                (v.c.learner_id == m.c.learner_id) & (v.c.memory_id == m.c.id)).where(
                m.c.learner_id == owner, m.c.status == 'active',
                or_(v.c.memory_id.is_(None), v.c.revision != m.c.revision, v.c.model_key != key))
                .order_by(m.c.pinned.desc(), m.c.updated_at.desc()).limit(32)).mappings())

    def save(self, owner, entries):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            if session.scalar(select(p.c.automatic_memory).where(p.c.learner_id == owner)) is False:
                return False
            current = dict(session.execute(select(m.c.id, m.c.revision).where(m.c.learner_id == owner,
                m.c.id.in_([row['memory_id'] for row in entries]), m.c.status == 'active')).all())
            entries = [row for row in entries if row['learner_id'] == owner and current.get(row['memory_id']) == row['revision']]
            if entries:
                stmt = insert(v).values(entries)
                session.execute(stmt.on_conflict_do_update(index_elements=['learner_id', 'memory_id'],
                    set_={name: getattr(stmt.excluded, name) for name in ('revision', 'model_key', 'dimension', 'vector')}))
            return True

    def rows(self, owner, key):
        with self.sessions() as session:
            return list(session.execute(select(m, v.c.vector, v.c.dimension).outerjoin(v,
                (v.c.learner_id == m.c.learner_id) & (v.c.memory_id == m.c.id)
                & (v.c.revision == m.c.revision) & (v.c.model_key == key))
                .where(m.c.learner_id == owner, m.c.status == 'active').limit(1001)).mappings())

    def invalidate(self, owner, identifier, revision, key):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            session.execute(delete(v).where(v.c.learner_id == owner, v.c.memory_id == identifier,
                v.c.revision == revision, v.c.model_key == key))
