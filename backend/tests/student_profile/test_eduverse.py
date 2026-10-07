import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.auth.config import ExternalProviderSettings
from app.auth.repositories.postgres import PostgresIdentityRepository
from app.auth.repositories.tables import learner, external_identity, mentra_account, auth_session
from app.auth.service import AuthService
from app.auth.tokens import ExternalTokenVerifier
from app.api.router import api_router
from app.core.exception_handlers import register_exception_handlers
from app.student_profile.repositories.postgres import PostgresStudentProfileRepository
from app.student_profile.repositories.tables import student_profile, profile_evidence
from app.student_profile.service import StudentProfileService
from app.student_profile.schemas import ProfileUpdate
from testing.postgres import PostgresSandbox
from testing.profile_evaluator import TestProfileEvaluator
from .test_profile import details


class EduVerseProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public = cls.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    def setUp(self):
        self.db = PostgresSandbox(seed_learners=False)
        self.addCleanup(self.db.close)
        provider = ExternalProviderSettings(issuer='https://eduverse-test.example', audience='mentra', public_keys={'test-key': self.public})
        self.auth = AuthService(PostgresIdentityRepository(self.db.sessions), ExternalTokenVerifier({'eduverse': provider}))
        self.profiles = StudentProfileService(PostgresStudentProfileRepository(self.db.sessions), TestProfileEvaluator())
        self.application = FastAPI()
        self.application.state.auth_service, self.application.state.student_profile_service = self.auth, self.profiles
        register_exception_handlers(self.application)
        self.application.include_router(api_router)

    def token(self, subject='existing-student-123', **changes):
        now = datetime.now(timezone.utc)
        claims = dict(sub=subject, iss='https://eduverse-test.example', aud='mentra', iat=int(now.timestamp()), exp=int((now + timedelta(seconds=120)).timestamp())) | changes
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'test-key'})

    def body(self, student_id='existing-student-123', **changes):
        return dict(student_id=student_id, token=self.token(student_id), profile=details(education_level='undergraduate', field_of_study='Computer science').model_dump(mode='json')) | changes

    def count(self, table):
        with self.db.engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(table)).scalar_one()

    def test_signed_provisioning_initializes_profile_without_mentra_credentials(self):
        with TestClient(self.application) as client:
            response = client.post('/api/v1/integrations/eduverse/students', json=self.body())
            self.assertEqual(response.status_code, 201)
            payload = response.json()
            self.assertTrue(payload['profile_initialized'])
            self.assertEqual(payload['student_id'], 'existing-student-123')
            self.assertEqual(payload['provider'], 'eduverse')
            self.assertIsNone(payload['user_id'])
            self.assertEqual(payload['profile']['details'], self.body()['profile'])
            self.assertEqual(payload['profile']['details_source'], 'eduverse')
            self.assertEqual(payload['profile']['onboarding_phase'], 'calibration')
            self.assertEqual(payload['profile']['calibration_status'], 'not_started')
            self.assertTrue(all(value['value'] is None for value in payload['profile']['estimates'].values()))
            self.assertEqual(response.headers['cache-control'], 'no-store')
            authenticated = client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + payload['access_token']})
            self.assertEqual(authenticated.json()['learner_id'], payload['learner_id'])
        self.assertEqual(self.count(learner), 1)
        self.assertEqual(self.count(external_identity), 1)
        self.assertEqual(self.count(mentra_account), 0)
        self.assertEqual(self.count(student_profile), 1)
        self.assertEqual(self.count(profile_evidence), 0)

    def test_repeated_platform_calls_preserve_manual_edits_and_mapping(self):
        with TestClient(self.application) as client:
            first = client.post('/api/v1/integrations/eduverse/students', json=self.body()).json()
            profile = self.profiles.get(first['learner_id'])
            edited = self.profiles.update_details(first['learner_id'], ProfileUpdate(expected_version=profile.version,
                details=profile.details.model_copy(update={'learning_preference': 'concise', 'learning_goal': 'Prepare for my next exam'})))
            second = client.post('/api/v1/integrations/eduverse/students', json=self.body())
            self.assertEqual(second.status_code, 200)
            self.assertFalse(second.json()['profile_initialized'])
            self.assertEqual(second.json()['learner_id'], first['learner_id'])
            self.assertEqual(second.json()['profile']['details'], edited.details.model_dump(mode='json'))
            self.assertEqual(second.json()['profile']['details_source'], 'user')
        self.assertEqual(self.count(learner), 1)

    def test_invalid_assertions_subject_mismatch_and_invalid_profile_never_provision(self):
        with TestClient(self.application) as client:
            for token in ('not-signed', self.token(aud='wrong-audience'), self.token(iss='https://attacker.example')):
                self.assertEqual(client.post('/api/v1/integrations/eduverse/students', json=self.body(token=token)).status_code, 401)
            self.assertEqual(client.post('/api/v1/integrations/eduverse/students', json=self.body(student_id='student-456', token=self.token())).status_code, 401)
            self.assertEqual(client.post('/api/v1/integrations/eduverse/students', json=self.body(profile={'education_level': 'primary'})).status_code, 422)
            self.assertEqual(client.post('/api/v1/integrations/eduverse/students', json=self.body(password='never accepted')).status_code, 422)
            self.assertEqual(client.post('/api/v1/integrations/eduverse/students', json=self.body(learner_id='injected')).status_code, 422)
            self.assertEqual(client.post('/api/v1/integrations/eduverse/students', json=self.body(student_id=True)).status_code, 422)
        self.assertEqual(self.count(learner), 0)
        self.assertEqual(self.count(auth_session), 0)

    def test_cookie_handoff_requires_trusted_origin_and_keeps_external_expiry(self):
        with TestClient(self.application, headers={'Origin': 'http://localhost:5173', 'X-Mentra-Session': 'cookie'}) as client:
            self.assertEqual(client.post('/api/v1/integrations/eduverse/students', json=self.body(), headers={'Origin': 'https://attacker.example'}).status_code, 403)
            self.assertEqual(self.count(learner), 0)
            response = client.post('/api/v1/integrations/eduverse/students', json=self.body())
            self.assertEqual(response.status_code, 201)
            self.assertNotIn('access_token', response.json())
            self.assertIn('HttpOnly', response.headers['set-cookie'])
            self.assertEqual(client.get('/api/v1/auth/me').json()['learner_id'], response.json()['learner_id'])
            with self.db.engine.connect() as connection:
                self.assertIsNotNone(connection.execute(select(auth_session.c.expires_at)).scalar_one())

    def test_numeric_subject_and_concurrent_provisioning_resolve_one_profile(self):
        body = self.body(student_id=314)
        def provision(_):
            with TestClient(self.application) as client:
                response = client.post('/api/v1/integrations/eduverse/students', json=body)
                self.assertIn(response.status_code, (200, 201))
                return response.json()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(provision, range(4)))
        self.assertEqual(len({value['learner_id'] for value in responses}), 1)
        self.assertEqual(sum(value['profile_initialized'] for value in responses), 1)
        self.assertEqual(self.count(learner), 1)
        self.assertEqual(self.count(student_profile), 1)
