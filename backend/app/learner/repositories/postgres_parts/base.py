"""Per-operation SQLAlchemy sessions and scoped PostgreSQL transaction locks."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import blake2b

from sqlalchemy import text
from app.core.identifiers import canonical_learner_id

from app.learner.models import Concept, LearningContext, LearnerConceptState, LearningEvidence, Misconception


def utcnow():
    return datetime.now(timezone.utc)


class PostgresRepositoryBase:
    def __init__(self, session_factory, session=None):
        self._session_factory = session_factory
        self._active_session = session
        self._locked_learners = set()
        self._read_cache = {}
        self._context_links = set()

    def _cache_allowed(self, learner_id=None):
        return self._active_session is not None and (learner_id is None or
            canonical_learner_id(learner_id) in self._locked_learners)

    def _remember(self, kind, key, read, *, learner_id=None):
        # Transaction locks make these lookups stable; nothing survives commit/rollback.
        if not self._cache_allowed(learner_id):
            return read()
        if learner_id is not None:
            key = (canonical_learner_id(learner_id), *key[1:])
        cache_key = (kind, key)
        if cache_key not in self._read_cache:
            self._read_cache[cache_key] = read()
        return self._read_cache[cache_key]

    @contextmanager
    def _session(self):
        if self._active_session is not None:
            yield self._active_session
        else:
            with self._session_factory.begin() as session:
                yield session

    @contextmanager
    def transaction(self, *, learner_ids=(), ontology=False):
        if self._active_session is not None:
            raise RuntimeError('Nested learner repository transactions are not supported')
        with self._session_factory.begin() as session:
            lock = 'pg_advisory_xact_lock' if ontology else 'pg_advisory_xact_lock_shared'
            session.execute(text(f'SELECT {lock}(17483, 2)'))
            repository = type(self)(self._session_factory, session)
            repository.lock_learners(learner_ids)
            try:
                yield repository
            finally:
                repository._active_session = None
                repository._read_cache.clear()
                repository._context_links.clear()
                repository._locked_learners.clear()

    def lock_learners(self, learner_ids):
        if self._active_session is None:
            raise RuntimeError('Learner locks require a repository transaction')
        normalized = {canonical_learner_id(value) for value in learner_ids}
        for learner_id in sorted(normalized - self._locked_learners):
            key = int.from_bytes(blake2b(('mentra:learner:' + learner_id).encode(), digest_size=8).digest(), 'big', signed=True)
            self._active_session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
            self._locked_learners.add(learner_id)

    @staticmethod
    def _concept_from_row(row):
        return Concept(row['id'], row['canonical_name'], row['description']) if row else None

    @staticmethod
    def _context_from_row(row):
        return LearningContext(row['id'], row['learner_id'], row['name'], row['status'],
                               row['description'], row['relevance_score'], row['last_activity_at']) if row else None

    @staticmethod
    def _state_from_row(row):
        if row is None:
            return None
        values = dict(row)
        values['policy_data'] = values.pop('policy_data_json')
        values.pop('updated_at')
        return LearnerConceptState(**values)

    @staticmethod
    def _evidence_from_row(row):
        if row is None:
            return None
        values = {key: value for key, value in row.items() if key in LearningEvidence.__dataclass_fields__}
        values.update(learner_id=row['learner_id'], metadata=row['metadata_json'])
        return LearningEvidence(**values)

    @staticmethod
    def _misconception_from_row(row):
        return Misconception(row['id'], row['learner_id'], row['concept_id'], row['description'],
                             row['confidence'], row['status'], row['context_id']) if row else None

    @staticmethod
    def _owned_values(value):
        values = asdict(value)
        if values.get('learner_id') is not None:
            values['learner_id'] = canonical_learner_id(values['learner_id'])
        return values
