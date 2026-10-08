from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.urls import postgres_url
from app.learner.repositories.tables import metadata
from app.student_profile.repositories import tables as profile_tables
from app.rag.repositories import tables as rag_tables

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=metadata, compare_type=True, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=postgres_url(settings.database_url), target_metadata=metadata,
                      literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get('connection') is not None:
    run(config.attributes['connection'])
else:
    engine = create_engine(postgres_url(settings.database_url), poolclass=pool.NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
