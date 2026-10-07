"""Real PostgreSQL identity, signed-token, session, and learner integration checks."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from alembic import command
from app.db.migrate import migration_config, upgrade

from app.auth.config import ExternalProviderSettings
from app.auth.errors import AuthenticationError, AccountExistsError
from app.auth.passwords import Passwords
from app.auth.repositories.postgres import PostgresIdentityRepository
from app.auth.repositories.tables import learner, mentra_account, external_identity, auth_session
from app.auth.schemas import RegisterRequest, LoginRequest, ExternalLoginRequest
from app.auth.service import AuthService, token_digest
from app.auth.tokens import ExternalTokenVerifier
from app.api.routes.auth import router
from app.core.exception_handlers import register_exception_handlers
from app.learner import LearnerEngine, ResolveLearningContextRequest, EvidenceSubmissionRequest, ConceptStateRequest
from testing.postgres import PostgresSandbox


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public = cls.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        cls.passwords = Passwords()

    def setUp(self):
        self.db = PostgresSandbox(seed_learners=False)
        self.addCleanup(self.db.close)
        self.now = datetime.now(timezone.utc)
        self.config = ExternalProviderSettings(issuer='https://issuer.example', audience='mentra',
            public_keys={'key-1': self.public})
        self.providers = {'eduverse': self.config, 'another_platform': self.config.model_copy()}
        self.repository = PostgresIdentityRepository(self.db.sessions)
        self.service = AuthService(self.repository, ExternalTokenVerifier(self.providers),
            clock=lambda: self.now, passwords=self.passwords)

    def assertion(self, *, key=None, headers=None, **changes):
        claims = dict(iss=self.config.issuer, aud=self.config.audience, sub='student-123',
            iat=int(self.now.timestamp()), exp=int((self.now + timedelta(seconds=120)).timestamp()))
        claims.update(changes)
        return jwt.encode(claims, key or self.key, algorithm='RS256', headers=headers or {'kid': 'key-1'})

    def external(self, *, provider='eduverse', **changes):
        return self.service.external_login(ExternalLoginRequest(provider=provider, token=self.assertion(**changes)))

    def count(self, table):
        with self.db.engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(table)).scalar_one()

    def register(self, username='alice'):
        return self.service.register(RegisterRequest(username=username, password='a long unique passphrase'))

    def test_standalone_registration_password_hash_and_login(self):
        response = self.register(' Alice ')
        self.assertNotEqual(response.user_id, response.learner_id)
        account = self.repository.get_account('alice')
        self.assertTrue(account.password_hash.startswith('$argon2id$'))
        self.assertNotIn('a long unique passphrase', account.password_hash)
        self.assertEqual(account.learner_id, response.learner_id)
        logged_in = self.service.login(LoginRequest(username='ALICE', password='a long unique passphrase'))
        self.assertEqual(logged_in.learner_id, response.learner_id)
        self.assertNotEqual(logged_in.access_token, response.access_token)
        for username, password in (('alice', 'wrong'), ('unknown', 'a long unique passphrase')):
            with self.assertRaises(AuthenticationError):
                self.service.login(LoginRequest(username=username, password=password))
        self.assertEqual(self.count(learner), 1)

    def test_duplicate_accounts_never_create_orphan_learners(self):
        self.register()
        with self.assertRaises(AccountExistsError):
            self.register('ALICE')
        self.assertEqual(self.count(learner), 1)
        self.assertEqual(self.count(mentra_account), 1)
        self.assertEqual(self.count(auth_session), 1)

    def test_concurrent_registration_is_unique_and_atomic(self):
        def register(_):
            try:
                return self.register()
            except AccountExistsError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(register, range(4)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.count(learner), 1)
        self.assertEqual(self.count(auth_session), 1)

    def test_session_hashing_expiry_logout_and_invalid_tokens(self):
        response = self.register()
        principal = self.service.authenticate(response.access_token)
        self.assertEqual(principal.learner_id, response.learner_id)
        with self.db.engine.connect() as connection:
            digest = connection.execute(select(auth_session.c.token_digest)).scalar_one()
        self.assertEqual(digest, token_digest(response.access_token))
        self.assertNotEqual(digest, response.access_token)
        for token in ('', 'malformed', 'x' * 43, response.access_token + 'x'):
            with self.assertRaises(AuthenticationError):
                self.service.authenticate(token)
        with patch.object(self.service, 'clock', return_value=response.expires_at):
            with self.assertRaises(AuthenticationError):
                self.service.authenticate(response.access_token)
        self.service.logout(response.access_token)
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(response.access_token)

    def test_first_external_login_provisions_mapping_without_credentials(self):
        first, second = self.external(), self.external()
        self.assertEqual(first.learner_id, second.learner_id)
        self.assertIsNone(first.user_id)
        self.assertEqual(first.provider, 'eduverse')
        self.assertEqual(self.count(learner), 1)
        self.assertEqual(self.count(external_identity), 1)
        self.assertEqual(self.count(mentra_account), 0)
        self.assertLessEqual(first.expires_at, self.now + timedelta(seconds=120))
        with self.db.engine.connect() as connection:
            mapping = connection.execute(select(external_identity)).mappings().one()
        self.assertEqual(mapping['external_subject_id'], 'student-123')

    def test_concurrent_external_login_creates_exactly_one_learner(self):
        token = self.assertion()
        request = ExternalLoginRequest(provider='eduverse', token=token)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.service.external_login(request), range(12)))
        self.assertEqual(len({r.learner_id for r in results}), 1)
        self.assertEqual(self.count(learner), 1)
        self.assertEqual(self.count(external_identity), 1)
        self.assertEqual(self.count(auth_session), 12)

    def test_provider_and_subject_namespaces_are_isolated(self):
        first = self.external()
        other_provider = self.external(provider='another_platform')
        other_student = self.external(sub='student-456')
        standalone = self.register('student-123')
        self.assertEqual(len({r.learner_id for r in (first, other_provider, other_student, standalone)}), 4)
        self.assertEqual(self.count(external_identity), 3)

    def test_untrusted_assertions_do_not_provision_anything(self):
        tokens = [self.assertion(iss='https://attacker.example'), self.assertion(aud='other-api'),
            self.assertion(key=self.other_key), self.assertion(headers={'kid': 'unknown'}),
            self.assertion(exp=int((self.now - timedelta(seconds=60)).timestamp())),
            self.assertion(iat=int((self.now + timedelta(seconds=60)).timestamp())),
            self.assertion(exp=int((self.now + timedelta(seconds=1000)).timestamp())),
            self.assertion(sub=''), self.assertion(sub=[]), self.assertion(sub=True),
            self.assertion(sub=' student-123'), self.assertion(headers={'crit': ['custom']}),
            jwt.encode({'sub': 'student-123'}, 'attacker-controlled-secret-long-enough', algorithm='HS256'),
            jwt.encode({'sub': 'student-123'}, key='', algorithm='none')]
        for missing in ('iss', 'aud', 'iat', 'exp', 'sub'):
            claims = jwt.decode(self.assertion(), options={'verify_signature': False})
            del claims[missing]
            tokens.append(jwt.encode(claims, self.key, algorithm='RS256'))
        for token in tokens:
            with self.subTest(token_header=token[:20]):
                with self.assertRaises(AuthenticationError):
                    self.service.external_login(ExternalLoginRequest(provider='eduverse', token=token))
        with self.assertRaises(AuthenticationError):
            self.external(provider='unconfigured')
        self.assertEqual(self.count(learner), 0)
        self.assertEqual(self.count(external_identity), 0)
        self.assertEqual(self.count(auth_session), 0)

    def test_numeric_existing_student_claim_and_key_rotation(self):
        self.providers['eduverse'] = self.config.model_copy(update={'subject_claim': 'student_id',
            'public_keys': {'key-1': self.public, 'key-2': self.public}})
        response = self.external(student_id=314, headers={'kid': 'key-2'})
        repeated = self.external(student_id='314')
        self.assertEqual(response.learner_id, repeated.learner_id)
        with self.db.engine.connect() as connection:
            self.assertEqual(connection.execute(select(external_identity.c.external_subject_id)).scalar_one(), '314')
        with self.assertRaises(AuthenticationError):
            self.external(student_id=315, headers={'typ': 'JWT'})

    def test_request_and_provider_configuration_validation(self):
        with self.assertRaises(ValidationError):
            RegisterRequest(username='alice', password='short')
        with self.assertRaises(ValidationError):
            ExternalLoginRequest(provider='eduverse', token=self.assertion(), password='never accepted')
        with self.assertRaises(ValidationError):
            ExternalLoginRequest(provider='eduverse', token=self.assertion(), learner_id='injected')
        for values in ({'algorithm': 'HS256'}, {'public_keys': {'key-1': 'shared secret'}},
                       {'subject_claim': 'iss'}, {'max_token_lifetime_seconds': 99999}):
            with self.assertRaises((ValidationError, ValueError)):
                ExternalProviderSettings.model_validate(self.config.model_dump() | values)

    def test_authenticated_identity_drives_isolated_learner_engine(self):
        first, second = self.external(), self.external(sub='student-456')
        engine = LearnerEngine(self.db.repository)
        concept = engine.register_concept('Identity boundary')
        context = engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id=first.learner_id, name='Security', activate=True))
        observation = EvidenceSubmissionRequest(learner_id=first.learner_id, concept_id=concept.id,
            context_id=context.context_id, source_type='QUIZ', result='CORRECT', source_id='q1', difficulty=0.8, independence=1)
        result = engine.submit_evidence(observation)
        self.assertTrue(result.accepted)
        self.assertEqual(engine.get_concept_state(ConceptStateRequest(learner_id=first.learner_id, concept_id=concept.id)).evidence_count, 1)
        self.assertIsNone(engine.get_concept_state(ConceptStateRequest(learner_id=second.learner_id, concept_id=concept.id)))
        self.assertIsNone(self.db.repository.get_evidence(result.evidence_id, second.learner_id))
        self.assertIsNone(self.db.repository.get_decision(result.evidence_id, second.learner_id))
        with self.assertRaises(IntegrityError):
            with self.db.engine.begin() as connection:
                connection.execute(external_identity.insert().values(provider='eduverse', external_subject_id='student-123', learner_id=second.learner_id))

    def test_auth_routes_and_server_bearer_dependency(self):
        application = FastAPI()
        application.state.auth_service = self.service
        application.include_router(router, prefix='/api/v1')
        register_exception_handlers(application)
        with TestClient(application) as client:
            response = client.post('/api/v1/auth/register', json={'username': 'alice', 'password': 'a long unique passphrase'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()['username'], 'alice')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            token = response.json()['access_token']
            headers = {'Authorization': 'Bearer ' + token}
            self.assertEqual(client.get('/api/v1/auth/me', headers=headers).json()['learner_id'], response.json()['learner_id'])
            self.assertEqual(client.get('/api/v1/auth/me').status_code, 401)
            self.assertEqual(client.post('/api/v1/auth/login', json={'username': 'alice', 'password': 'bad'}).status_code, 401)
            self.assertEqual(client.post('/api/v1/auth/logout', headers=headers).status_code, 204)
            self.assertEqual(client.get('/api/v1/auth/me', headers=headers).status_code, 401)
            external = client.post('/api/v1/auth/external', json={'provider': 'eduverse', 'token': self.assertion()})
            self.assertEqual(external.status_code, 200)
            self.assertIsNone(external.json()['user_id'])

    def cookie_client(self):
        application = FastAPI()
        application.state.auth_service = self.service
        application.include_router(router, prefix='/api/v1')
        register_exception_handlers(application)
        return TestClient(application, headers={'Origin': 'http://localhost:5173', 'X-Mentra-Session': 'cookie'})

    def test_cookie_registration_restores_identity_and_survives_time_until_logout(self):
        with self.cookie_client() as client:
            response = client.post('/api/v1/auth/register', json={'username': 'alice', 'password': 'a long unique passphrase'})
            self.assertEqual(response.status_code, 201)
            self.assertNotIn('access_token', response.json())
            self.assertEqual(response.json()['username'], 'alice')
            cookie = response.headers['set-cookie']
            self.assertIn('HttpOnly', cookie)
            self.assertIn('SameSite=lax', cookie)
            self.assertIn('Max-Age=34560000', cookie)
            self.assertIn('Path=/api/v1', cookie)
            token = client.cookies.get('mentra_session')
            with self.db.engine.connect() as connection:
                session = connection.execute(select(auth_session)).mappings().one()
            self.assertIsNone(session['expires_at'])
            self.assertEqual(session['token_digest'], token_digest(token))
            later = self.now + timedelta(days=730)
            with patch.object(self.service, 'clock', return_value=later):
                restored = client.get('/api/v1/auth/me')
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(restored.json(), response.json())
                self.assertIn('Max-Age=34560000', restored.headers['set-cookie'])
                self.assertEqual(client.post('/api/v1/auth/logout').status_code, 204)
                self.assertIsNone(client.cookies.get('mentra_session'))
                with self.assertRaises(AuthenticationError):
                    self.service.authenticate(token)
                self.assertEqual(client.get('/api/v1/auth/me').status_code, 401)
                self.assertEqual(client.post('/api/v1/auth/logout').status_code, 204)

    def test_cookie_login_uses_real_credentials_and_revokes_only_current_session(self):
        self.register()
        with self.cookie_client() as client:
            bad = client.post('/api/v1/auth/login', json={'username': 'alice', 'password': 'incorrect'})
            self.assertEqual(bad.status_code, 401)
            self.assertIsNone(client.cookies.get('mentra_session'))
            good = client.post('/api/v1/auth/login', json={'username': 'ALICE', 'password': 'a long unique passphrase'})
            self.assertEqual(good.status_code, 200)
            self.assertNotIn('access_token', good.json())
            with self.cookie_client() as returning:
                returning.cookies.update(client.cookies)
                self.assertEqual(returning.get('/api/v1/auth/me').json(), good.json())
            self.assertEqual(client.post('/api/v1/auth/logout').status_code, 204)
            self.assertEqual(self.count(auth_session), 2)
            with self.db.engine.connect() as connection:
                active = connection.execute(select(func.count()).select_from(auth_session).where(auth_session.c.revoked_at.is_(None))).scalar_one()
            self.assertEqual(active, 1)

    def test_cookie_mutations_require_trusted_origin(self):
        with self.cookie_client() as client:
            credentials = {'username': 'alice', 'password': 'a long unique passphrase'}
            for origin in ('https://attacker.example', 'null'):
                self.assertEqual(client.post('/api/v1/auth/register', json=credentials, headers={'Origin': origin}).status_code, 403)
            self.assertEqual(self.count(learner), 0)
            self.assertEqual(client.post('/api/v1/auth/register', json=credentials).status_code, 201)
            token = client.cookies.get('mentra_session')
            self.assertEqual(client.post('/api/v1/auth/logout', headers={'Origin': 'https://attacker.example'}).status_code, 403)
            self.assertEqual(self.service.authenticate(token).learner_id, client.get('/api/v1/auth/me').json()['learner_id'])
            self.assertEqual(client.post('/api/v1/auth/logout').status_code, 204)

    def test_cookie_secure_flags_and_external_expiry_are_preserved(self):
        from app.auth import cookies
        from app.core.config import Settings
        configured = Settings(_env_file=None, auth_cookie_secure=True, auth_cookie_same_site='none')
        with patch.object(cookies, 'settings', configured), self.cookie_client() as client:
            response = client.post('/api/v1/auth/external', json={'provider': 'eduverse', 'token': self.assertion()})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertIn('SameSite=none', response.headers['set-cookie'])
            with self.db.engine.connect() as connection:
                self.assertIsNotNone(connection.execute(select(auth_session.c.expires_at)).scalar_one())

    def test_persistent_session_migration_downgrade_preserves_and_revokes_sessions(self):
        request = RegisterRequest(username='alice', password='a long unique passphrase')
        response = self.service.register(request, persistent=True)
        self.assertIsNone(response.expires_at)
        with self.db.engine.begin() as connection:
            command.downgrade(migration_config(connection), '20261007_0001')
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(response.access_token)
        self.assertEqual(self.count(auth_session), 1)
        upgrade(self.db.engine)
        with self.db.engine.connect() as connection:
            command.check(migration_config(connection))
