"""Bounded, read-only database readiness diagnostics."""
from sqlalchemy import Table, Column, Text, DateTime, text
from app.db.metadata import metadata

# Retain the legacy table mapping for compatibility with applied migrations.
# Runtime health checks and workers no longer read or write it.
workers = Table('worker_health', metadata, Column('role', Text, primary_key=True),
    Column('last_seen', DateTime(timezone=True), nullable=False))


def readiness(sessions) -> None:
    with sessions.begin() as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        session.execute(text("SET LOCAL statement_timeout = '1s'"))
        session.execute(text('SELECT 1'))
