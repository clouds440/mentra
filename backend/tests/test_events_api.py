"""Real event persistence behind the HTTP boundary and production auth dependencies."""
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.events import router
from app.auth.models import AuthenticatedIdentity
from app.auth.errors import AuthenticationError
from app.core.exception_handlers import register_exception_handlers
from app.history_management.events.factory import create_events_service
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires explicit dedicated TEST_DATABASE_URL')
class EventsAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix='/api/v1')
        app.state.history_management = SimpleNamespace(events=create_events_service(self.db.sessions))
        class Auth:
            def authenticate(self, token):
                if token not in ('alice', 'bob', 'new'):
                    raise AuthenticationError()
                return AuthenticatedIdentity(learner_id=learner_id('alice' if token == 'new' else token), session_id=token, expires_at=None)
        class Profile:
            def get(self, owner):
                return SimpleNamespace(onboarding_phase='complete')
        app.state.auth_service = Auth()
        app.state.student_profile_service = Profile()
        self.client = TestClient(app)
        self.headers = {'Authorization': 'Bearer alice'}

    def body(self):
        return dict(title='Chemistry assignment', kind='assignment', timezone='Asia/Karachi',
                    local_date='2026-10-12', client_request_id=str(uuid4()))

    def test_authentication_unknown_fields_and_cookie_origin(self):
        self.assertEqual(self.client.get('/api/v1/events/summary').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/events', json=self.body()).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/events', json=self.body() | {'learner_id':learner_id('bob')}, headers=self.headers).status_code, 422)
        self.client.cookies.set('mentra_session', 'alice')
        self.assertEqual(self.client.post('/api/v1/events', json=self.body(), headers={'Origin':'https://attacker.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/events', json=self.body(), headers={'Origin':'http://localhost:5173'}).status_code, 200)

    def test_create_recovery_detail_sync_and_retry_delete(self):
        body = self.body()
        response = self.client.post('/api/v1/events', json=body, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        event = response.json()['event']
        self.assertNotIn('learner_id', event)
        self.assertEqual(event['origin'], 'manual')
        recovered = self.client.get('/api/v1/events/operations/'+body['client_request_id'], headers=self.headers)
        self.assertEqual(recovered.json()['event']['id'], event['id'])
        url = '/api/v1/events/'+event['id']
        self.assertEqual(self.client.get(url, headers={'Authorization':'Bearer bob'}).status_code, 404)
        self.assertEqual(self.client.get(url, headers=self.headers).json()['evidence'], [])
        patch = dict(expected_revision=1, client_request_id=str(uuid4()), status='completed')
        completed = self.client.patch(url, json=patch, headers=self.headers)
        self.assertEqual(completed.json()['event']['reminder_state'], 'cancelled')
        self.assertEqual(self.client.patch(url, json=patch | {'client_request_id':str(uuid4())}, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.get('/api/v1/events/sync', headers=self.headers).status_code, 200)
        operation = str(uuid4())
        deletion = url+'?expected_revision=2&client_request_id='+operation
        self.assertEqual(self.client.delete(deletion, headers=self.headers).json()['outcome'], 'deleted')
        self.assertEqual(self.client.delete(deletion, headers=self.headers).json()['outcome'], 'deleted')
        self.assertEqual(self.client.get(url, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/events', json=body, headers=self.headers).json()['outcome'], 'deleted')

    def test_static_paths_preview_range_and_response_validation(self):
        for path in ('preferences', 'summary', 'sync'):
            self.assertEqual(self.client.get('/api/v1/events/'+path, headers=self.headers).status_code, 200)
        gap = self.client.post('/api/v1/events/temporal-preview', headers=self.headers,
            json=dict(timezone='America/New_York', local_start='2026-03-08T02:30:00'))
        self.assertEqual(gap.status_code, 200, gap.text)
        self.assertEqual(gap.json()['field_errors'][0]['code'], 'DATE_AMBIGUOUS')
        self.assertEqual(gap.json()['choices'], [])
        fold = self.client.post('/api/v1/events/temporal-preview', headers=self.headers,
            json=dict(timezone='America/New_York', local_start='2026-11-01T01:30:00'))
        self.assertEqual(len(fold.json()['choices']), 2)
        self.assertTrue(fold.json()['requires_choice'])
        self.assertEqual(self.client.get('/api/v1/events?after=2026-10-09T00:00:00', headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/events?after=2026-10-09T00:00:00Z&before=2028-10-09T00:00:00Z', headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/events', headers=self.headers, json=self.body() | {'local_date':'9999-12-31'}).status_code, 422)

    def test_extreme_query_dates_are_validation_errors(self):
        for value in ('9999-12-31T23:59:59Z', '0001-01-01T00:00:00Z'):
            response = self.client.get('/api/v1/events', params={'after':value}, headers=self.headers)
            self.assertEqual(response.status_code, 422, response.text)
