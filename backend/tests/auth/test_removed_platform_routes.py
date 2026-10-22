"""Retired platform contracts must stay absent from the production API surface."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.core.config import Settings


class RemovedPlatformRoutesTests(unittest.TestCase):
    def test_platform_routes_and_contracts_are_absent(self):
        application = FastAPI()
        application.include_router(api_router)
        schema = application.openapi()
        self.assertIn('/api/v1/auth/register', schema['paths'])
        self.assertIn('/api/v1/auth/login', schema['paths'])
        self.assertIn('/api/v1/student-profile', schema['paths'])
        self.assertNotIn('/api/v1/auth/external', schema['paths'])
        self.assertFalse(any('/integrations/' in path for path in schema['paths']))
        self.assertNotIn('ExternalLoginRequest', schema['components']['schemas'])
        with TestClient(application) as client:
            for path in ('/api/v1/auth/external', '/api/v1/integrations/eduverse/students'):
                for headers in ({}, {'X-Mentra-Session': 'cookie', 'Origin': 'http://localhost:5173'}):
                    with self.subTest(path=path, headers=headers):
                        response = client.post(path, json={}, headers=headers)
                        self.assertEqual(response.status_code, 404)
                        self.assertNotIn('set-cookie', response.headers)

    def test_provider_trust_configuration_is_removed(self):
        self.assertNotIn('auth_external_providers', Settings.model_fields)
