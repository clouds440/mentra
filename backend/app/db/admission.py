"""Content-free, cross-process capacity leases and bounded rate buckets."""
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, timezone
from hashlib import blake2b
from uuid import uuid4

from sqlalchemy import Table, Column, Text, Integer, DateTime, select, delete, func, text
from sqlalchemy.dialects.postgresql import insert
from app.db.metadata import metadata
from app.core.exceptions import AppError

leases = Table('work_admission', metadata,
    Column('id', Text, primary_key=True), Column('kind', Text, nullable=False),
    Column('owner', Text, nullable=False), Column('expires_at', DateTime(timezone=True), nullable=False))
rates = Table('request_rate', metadata,
    Column('kind', Text, primary_key=True), Column('bucket', Integer, primary_key=True),
    Column('started_at', DateTime(timezone=True), nullable=False), Column('count', Integer, nullable=False))


class Admission:
    def __init__(self, sessions, *, clock=lambda: datetime.now(timezone.utc), settings=None):
        self.sessions, self.clock = sessions, clock
        self.settings = settings

    def acquire(self, kind, owner, *, capacity, owner_capacity, seconds=180, rate_keys=()):
        if self.settings is not None:
            if kind == 'auth':
                capacity, owner_capacity = self.settings.auth_global_capacity, self.settings.auth_owner_capacity
            elif kind == 'model':
                capacity, owner_capacity = self.settings.work_global_capacity, self.settings.work_owner_capacity
            elif kind in ('parse', 'upload'):
                capacity, owner_capacity = self.settings.parse_global_capacity, self.settings.parse_owner_capacity
        now, identifier = self.clock(), str(uuid4())
        digest = int.from_bytes(blake2b(('mentra:admission:' + kind).encode(), digest_size=8).digest(), 'big', signed=True)
        with self.sessions.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            session.execute(text('SELECT pg_advisory_xact_lock(:key)'), dict(key=digest))
            session.execute(delete(leases).where(leases.c.kind == kind, leases.c.expires_at <= now))
            active = select(func.count()).select_from(leases).where(leases.c.kind == kind)
            if session.scalar(active) >= capacity or session.scalar(active.where(leases.c.owner == owner)) >= owner_capacity:
                raise AppError('WORK_CAPACITY', 'The service is busy. Try again shortly.', 429)
            # Fixed hash buckets cap anonymous cardinality; collisions fail closed.
            for dimension, key, maximum in rate_keys:
                bucket = int.from_bytes(blake2b(str(key).encode(), digest_size=4).digest(), 'big') % 4096
                rate_kind = kind + ':' + dimension
                row = session.execute(select(rates).where(rates.c.kind == rate_kind, rates.c.bucket == bucket)).mappings().first()
                fresh = row is None or row['started_at'] <= now - timedelta(seconds=60)
                count = 1 if fresh else row['count'] + 1
                if count > maximum:
                    raise AppError('REQUEST_RATE_LIMIT', 'Too many requests. Try again shortly.', 429)
                values = dict(kind=rate_kind, bucket=bucket, started_at=now if fresh else row['started_at'], count=count)
                session.execute(insert(rates).values(**values).on_conflict_do_update(
                    index_elements=[rates.c.kind, rates.c.bucket], set_=dict(started_at=values['started_at'], count=count)))
            session.execute(leases.insert().values(id=identifier, kind=kind, owner=owner, expires_at=now + timedelta(seconds=seconds)))
        return identifier

    def release(self, identifier):
        with self.sessions.begin() as session:
            session.execute(delete(leases).where(leases.c.id == identifier))

    @contextmanager
    def reserve(self, *args, **kwargs):
        identifier = self.acquire(*args, **kwargs)
        try:
            yield identifier
        finally:
            try:
                self.release(identifier)
            except Exception:
                from app.core.logging import workflow_logger
                workflow_logger.event('admission.cleanup_deferred', code='CLAIM_CLEANUP_UNAVAILABLE')

    @asynccontextmanager
    async def async_reserve(self, *args, **kwargs):
        from app.core.observability.timing import run_in_threadpool
        identifier = await run_in_threadpool(self.acquire, *args, **kwargs)
        try:
            yield identifier
        finally:
            try:
                await run_in_threadpool(self.release, identifier)
            except Exception:
                from app.core.logging import workflow_logger
                workflow_logger.event('admission.cleanup_deferred', code='CLAIM_CLEANUP_UNAVAILABLE')


@asynccontextmanager
async def request_capacity(request, owner, kind, *, capacity=4, owner_capacity=1, seconds=300):
    gate = getattr(request.app.state, 'work_admission', None)
    if gate is None:
        yield
    else:
        if owner is None:
            raise AppError('AUTH_REQUIRED', 'Sign in to continue.', 401)
        async with gate.async_reserve(kind, owner, capacity=capacity, owner_capacity=owner_capacity, seconds=seconds,
                                      rate_keys=[('owner', owner, 30)]):
            yield
