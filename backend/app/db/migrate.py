"""Explicit Alembic entry point shared by deployment and isolated test fixtures."""

from pathlib import Path
from time import monotonic, sleep

from alembic.config import Config
from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def migration_config(connection=None) -> Config:
    config = Config(str(BACKEND_ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
    if connection is not None:
        config.attributes['connection'] = connection
    return config


def upgrade(engine=None, *, lock_timeout: float = 300) -> None:
    if engine is None:
        from app.db.database import get_engine
        engine = get_engine()
    with engine.connect() as connection:
        from sqlalchemy import text
        # A blocking SELECT holds a transaction snapshot while waiting. Another
        # migration's CREATE INDEX CONCURRENTLY can wait for that snapshot and
        # deadlock with this lock request, even across isolated test schemas.
        # Keep the existing session lock, but release each failed probe's
        # transaction before waiting outside PostgreSQL.
        deadline = monotonic() + lock_timeout
        while True:
            acquired = connection.scalar(text('SELECT pg_try_advisory_lock(17483, 1)'))
            connection.commit()
            if acquired:
                break
            if monotonic() >= deadline:
                raise RuntimeError('Timed out waiting for the database migration lock.')
            sleep(0.05)
        try:
            command.upgrade(migration_config(connection), 'head')
        finally:
            connection.rollback()
            connection.execute(text('SELECT pg_advisory_unlock(17483, 1)'))
            connection.commit()


if __name__ == '__main__':
    from app.core.logging import configure_logging, workflow_logger
    configure_logging('migration')
    with workflow_logger.workflow('db.migrate') as execution:
        upgrade()
        execution.outcome = 'success'
