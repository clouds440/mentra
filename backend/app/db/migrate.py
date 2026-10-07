"""Explicit Alembic entry point shared by deployment and isolated test fixtures."""

from pathlib import Path

from alembic.config import Config
from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def migration_config(connection=None) -> Config:
    config = Config(str(BACKEND_ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
    if connection is not None:
        config.attributes['connection'] = connection
    return config


def upgrade(engine=None) -> None:
    if engine is None:
        from app.db.database import get_engine
        engine = get_engine()
    with engine.connect() as connection:
        from sqlalchemy import text
        connection.execute(text('SELECT pg_advisory_lock(17483, 1)'))
        connection.commit()
        try:
            command.upgrade(migration_config(connection), 'head')
        finally:
            connection.rollback()
            connection.execute(text('SELECT pg_advisory_unlock(17483, 1)'))
            connection.commit()


if __name__ == '__main__':
    upgrade()
