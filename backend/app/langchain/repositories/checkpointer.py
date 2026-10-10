"""Pooled PostgreSQL checkpoint adapter; schema is owned by Alembic."""
from contextlib import contextmanager
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.core.logging import workflow_logger

@workflow_logger.operation(kind='scope')
@contextmanager
def postgres_saver(engine):
    raw = engine.raw_connection()
    connection = raw.driver_connection
    previous_factory, previous_autocommit = connection.row_factory, connection.autocommit
    try:
        connection.autocommit = True
        connection.row_factory = dict_row
        connection.execute("SET statement_timeout = '5s'")
        yield PostgresSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=None))
    finally:
        try:
            connection.execute('RESET statement_timeout')
            connection.row_factory = previous_factory
            connection.autocommit = previous_autocommit
        finally:
            raw.close()
