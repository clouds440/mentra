from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import blake2b
from sqlalchemy import text, select
from app.core.identifiers import canonical_learner_id
from .store import PostgresProfileStore


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={'transaction': {'kind':'contextmanager'}})
class PostgresStudentProfileRepository:
    def __init__(self, session_factory):
        self.sessions = session_factory
        from app.core.read_cache import ReadCache
        self._profiles = ReadCache(capacity=128, ttl=None)

    def read_profile(self, learner_id):
        from .tables import student_profile
        from ..schemas import StudentProfile
        learner_id = canonical_learner_id(learner_id)
        with self.sessions() as session:
            revision = session.execute(select(student_profile.c.version, student_profile.c.created_at)
                .where(student_profile.c.learner_id == learner_id)).first()
            key = (learner_id, *revision) if revision else None
            cached = self._profiles.get(key) if revision is not None else None
            if cached is not None:
                return cached
            row = session.execute(select(student_profile).where(student_profile.c.learner_id == learner_id)).mappings().first()
            if row is not None:
                value = StudentProfile.model_validate(dict(row))
                self._profiles.put((learner_id, value.version, value.created_at), value)
                return value
        with self.transaction(learner_id) as store:
            return store.profile()

    @contextmanager
    def transaction(self, learner_id):
        learner_id = canonical_learner_id(learner_id)
        key = int.from_bytes(blake2b(('mentra:student-profile:' + learner_id).encode(), digest_size=8).digest(), 'big', signed=True)
        with self.sessions.begin() as session:
            from app.db.owner_transactions import lock_owner
            lock_owner(session, learner_id)
            session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
            yield PostgresProfileStore(session, learner_id, datetime.now(timezone.utc))
