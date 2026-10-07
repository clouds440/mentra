from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import blake2b
from sqlalchemy import text
from app.core.identifiers import canonical_learner_id
from .store import PostgresProfileStore


class PostgresStudentProfileRepository:
    def __init__(self, session_factory):
        self.sessions = session_factory

    @contextmanager
    def transaction(self, learner_id):
        learner_id = canonical_learner_id(learner_id)
        key = int.from_bytes(blake2b(('mentra:student-profile:' + learner_id).encode(), digest_size=8).digest(), 'big', signed=True)
        with self.sessions.begin() as session:
            session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
            yield PostgresProfileStore(session, learner_id, datetime.now(timezone.utc))
