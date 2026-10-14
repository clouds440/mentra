"""Read-only readiness and content-free worker heartbeat infrastructure."""
from datetime import datetime, timezone, timedelta
from sqlalchemy import Table, Column, Text, DateTime, select, text
from sqlalchemy.dialects.postgresql import insert
from app.db.metadata import metadata

workers = Table('worker_health', metadata, Column('role', Text, primary_key=True),
    Column('last_seen', DateTime(timezone=True), nullable=False))


def heartbeat(sessions, role):
    now = datetime.now(timezone.utc)
    with sessions.begin() as session:
        session.execute(insert(workers).values(role=role, last_seen=now).on_conflict_do_update(
            index_elements=[workers.c.role], set_=dict(last_seen=now)))


def readiness(sessions):
    with sessions.begin() as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        session.execute(text("SET LOCAL statement_timeout = '1s'"))
        session.execute(text('SELECT 1'))
        seen = dict(session.execute(select(workers)).all())
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    return {role: 'ok' if seen.get(role) and seen[role] > cutoff else 'unavailable'
            for role in ('rag', 'events', 'assessment')}
