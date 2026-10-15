import unittest
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.health import router
from app.db.health import readiness
from testing.postgres import PostgresSandbox


class ReadinessTests(unittest.TestCase):
    def test_readiness_checks_database_without_worker_heartbeats(self):
        with PostgresSandbox() as db:
            app = FastAPI()
            app.include_router(router, prefix='/api/v1')
            app.state.model_factory = Mock()
            app.state.embedding_service = Mock(model_name='test', model_version='test', dimension=3)
            app.state.vector_store = Mock(collection_name='test')
            app.state.database_health_probe = lambda: readiness(db.sessions)
            client = TestClient(app)
            self.assertEqual(client.get('/api/v1/health').status_code, 200)
            self.assertEqual(client.get('/api/v1/health/ready').status_code, 200)
            self.assertNotIn('workers', client.get('/api/v1/health/ready').json()['checks'])
            app.state.vector_store.ensure_collection.assert_not_called()
            self.assertEqual(app.state.vector_store.validate_collection.call_count, 2)
            app.state.database_health_probe = Mock(side_effect=RuntimeError('Database unavailable'))
            failed = client.get('/api/v1/health/ready')
            self.assertEqual(failed.status_code, 503)
            self.assertEqual(failed.json()['checks']['database']['status'], 'error')
