import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError
from sqlalchemy import text
from app.db.database import build_engine, get_engine
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from testing.postgres import PostgresSandbox


class DatabaseBudgetTests(unittest.TestCase):
    def test_database_busy_read_can_retry_but_write_retains_unknown_outcome(self):
        from sqlalchemy.exc import OperationalError
        from app.langchain.tool_execution import failure
        original = Exception('private query content')
        original.sqlstate = '55P03'
        error = OperationalError(None, None, original)
        self.assertTrue(failure(error).retryable)
        receipt = failure(error, write=True)
        self.assertFalse(receipt.retryable)
        self.assertEqual(receipt.effect_certainty, 'unknown')
        self.assertEqual(receipt.code, 'DATABASE_BUSY')
        self.assertNotIn('private', receipt.reason)
    def test_pool_checkout_is_bounded(self):
        with PostgresSandbox() as db:
            engine = build_engine(db.engine.url.render_as_string(hide_password=False), pool_size=1, max_overflow=0, pool_timeout=.05)
            self.addCleanup(engine.dispose)
            with engine.connect():
                with self.assertRaises(TimeoutError):
                    engine.connect()

    def test_api_and_worker_use_different_statement_budgets(self):
        with PostgresSandbox() as db:
            for role, expected in [('api', '30s'), ('worker', '2min')]:
                with patch.object(settings, 'database_url', db.engine.url.render_as_string(hide_password=False)), patch.object(settings, 'database_role', role):
                    get_engine.cache_clear()
                    engine = get_engine()
                    try:
                        with engine.connect() as connection:
                            self.assertEqual(connection.scalar(text('SHOW statement_timeout')), expected)
                            self.assertEqual(connection.scalar(text('SHOW lock_timeout')), '5s')
                    finally:
                        engine.dispose()
                        get_engine.cache_clear()

    def test_pool_timeout_has_recoverable_public_response(self):
        app = FastAPI()
        register_exception_handlers(app)
        @app.get('/busy')
        def busy():
            raise TimeoutError('private connection detail')
        response = TestClient(app).get('/busy')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'DATABASE_BUSY')
        self.assertNotIn('private', response.text)
