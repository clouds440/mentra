import unittest
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.health import router
from app.db.health import heartbeat, readiness
from testing.postgres import PostgresSandbox


class ReadinessTests(unittest.TestCase):
    def test_readiness_never_initializes_collection_and_reports_worker_absence(self):
        with PostgresSandbox() as db:
            app = FastAPI()
            app.include_router(router, prefix='/api/v1')
            app.state.model_factory = Mock()
            app.state.embedding_service = Mock(model_name='test', model_version='test', dimension=3)
            app.state.vector_store = Mock(collection_name='test')
            app.state.database_health_probe = lambda: readiness(db.sessions)
            client = TestClient(app)
            self.assertEqual(client.get('/api/v1/health').status_code, 200)
            self.assertEqual(client.get('/api/v1/health/ready').status_code, 503)
            for role in ('rag', 'events', 'assessment'):
                heartbeat(db.sessions, role)
            self.assertEqual(client.get('/api/v1/health/ready').status_code, 200)
            app.state.vector_store.ensure_collection.assert_not_called()
            self.assertEqual(app.state.vector_store.validate_collection.call_count, 2)
