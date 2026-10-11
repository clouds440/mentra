"""Cross-worker rolling usage admission. Transactions never contain network work."""
from datetime import timedelta
from time import monotonic
from functools import wraps
from sqlalchemy import select, func, update, delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert
from app.db.owner_transactions import lock_owner
from .tables import calls, guard, cache
from . import RepositoryError

PROVIDER = 'you_free'


def repository_boundary(method):
    @wraps(method)
    def invoke(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except SQLAlchemyError:
            raise RepositoryError('Web search persistence unavailable.') from None
    return invoke


class UsageRepository:
    def __init__(self, sessions, *, global_limit=90, user_limit=10, minute_limit=3):
        self.sessions = sessions
        self.global_limit, self.user_limit, self.minute_limit = global_limit, user_limit, minute_limit
        self._cleanup_at = 0.0

    @repository_boundary
    def reserve(self, owner, operation, now):
        with self.sessions.begin() as session:
            session.execute(text("SELECT set_config('lock_timeout', '1000ms', true), set_config('statement_timeout', '1000ms', true)"))
            lock_owner(session, owner)
            session.execute(insert(guard).values(provider=PROVIDER).on_conflict_do_nothing())
            session.execute(select(guard).where(guard.c.provider == PROVIDER).with_for_update()).one()
            prior = session.execute(select(calls.c.state).where(calls.c.id == operation)).scalar_one_or_none()
            if prior is not None:
                return 'duplicate'
            charged = (calls.c.provider == PROVIDER, calls.c.state != 'released', calls.c.reserved_at > now - timedelta(days=1))
            global_count = session.scalar(select(func.count()).select_from(calls).where(*charged))
            user_count = session.scalar(select(func.count()).select_from(calls).where(*charged, calls.c.learner_id == owner))
            minute_count = session.scalar(select(func.count()).select_from(calls).where(*charged, calls.c.learner_id == owner, calls.c.reserved_at > now - timedelta(minutes=1)))
            if global_count >= self.global_limit or user_count >= self.user_limit:
                return 'quota_exhausted'
            if minute_count >= self.minute_limit:
                return 'rate_limited'
            session.execute(calls.insert().values(id=operation, provider=PROVIDER, learner_id=owner, reserved_at=now, state='reserved'))
            if monotonic() >= self._cleanup_at:
                expired = select(calls.c.id).where(calls.c.reserved_at < now - timedelta(days=2)).limit(100)
                session.execute(delete(calls).where(calls.c.id.in_(expired)))
                self._cleanup_at = monotonic() + 60
            return 'reserved'

    @repository_boundary
    def mark(self, operation, state):
        with self.sessions.begin() as session:
            session.execute(text("SELECT set_config('lock_timeout', '1000ms', true), set_config('statement_timeout', '1000ms', true)"))
            # Release only a proven unsent reservation. Unknown/sent never refund.
            statement = update(calls).where(calls.c.id == operation)
            if state == 'released':
                statement = statement.where(calls.c.state == 'reserved')
            session.execute(statement.values(state=state))

    @repository_boundary
    def cached(self, owner, key, now):
        with self.sessions.begin() as session:
            session.execute(text("SET LOCAL statement_timeout = '1s'"))
            return session.execute(select(cache.c.payload, cache.c.expires_at).where(cache.c.id == key,
                cache.c.learner_id == owner, cache.c.expires_at > now)).mappings().first()

    @repository_boundary
    def cache_result(self, owner, key, now, expires, payload):
        import json
        if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 32768:
            return
        with self.sessions.begin() as session:
            session.execute(text("SELECT set_config('lock_timeout', '1000ms', true), set_config('statement_timeout', '1000ms', true)"))
            lock_owner(session, owner)
            session.execute(insert(guard).values(provider=PROVIDER).on_conflict_do_nothing())
            session.execute(select(guard).where(guard.c.provider == PROVIDER).with_for_update()).one()
            session.execute(delete(cache).where(cache.c.expires_at <= now))
            session.execute(insert(cache).values(id=key, learner_id=owner, cached_at=now, expires_at=expires, payload=payload)
                .on_conflict_do_update(index_elements=[cache.c.id], set_=dict(cached_at=now, expires_at=expires, payload=payload)))
            # Fixed global cap across workers, not a separate 128-entry cache per process.
            evicted = select(cache.c.id).order_by(cache.c.cached_at.desc(), cache.c.id).offset(128)
            session.execute(delete(cache).where(cache.c.id.in_(evicted)))
