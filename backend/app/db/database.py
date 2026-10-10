"""Application database lifecycle. Repositories own all domain persistence."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.core.config import settings
from app.db.urls import postgres_url


def build_engine(database_url: str, **options):
    return create_engine(postgres_url(database_url), pool_pre_ping=True, hide_parameters=True, **options)


@lru_cache
def get_engine():
    return build_engine(settings.database_url)


def get_session_factory():
    return sessionmaker(get_engine(), expire_on_commit=False)


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def init_db() -> None:
    """Check migration readiness; never create or alter tables during app startup."""
    from app.db.migrate import migration_config
    head = ScriptDirectory.from_config(migration_config()).get_current_head()
    with get_engine().connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head or head is None:
        raise RuntimeError('Database schema is not current. Run Alembic upgrade head before starting Mentra.')
