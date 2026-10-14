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

    def read_profile(self, learner_id):
        from .tables import student_profile
        from ..schemas import StudentProfile
        learner_id = canonical_learner_id(learner_id)
        with self.sessions() as session:
            row = session.execute(select(student_profile).where(student_profile.c.learner_id == learner_id)).mappings().first()
            if row is not None:
                return StudentProfile.model_validate(dict(row))
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
