"""Real PostgreSQL identity, session, and learner integration checks."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, func
from alembic import command
from app.db.migrate import migration_config, upgrade

from app.auth.errors import AuthenticationError, AccountExistsError, PasswordChangeError
from app.auth.passwords import Passwords
from app.auth.repositories.postgres import PostgresIdentityRepository
from app.auth.repositories.tables import learner, mentra_account, external_identity, auth_session
from app.auth.schemas import ChangePasswordRequest, RegisterRequest, LoginRequest
from app.auth.service import AuthService, token_digest
from app.api.routes.auth import router
from app.core.exception_handlers import register_exception_handlers
from app.learner import LearnerEngine, ResolveLearningContextRequest, EvidenceSubmissionRequest, ConceptStateRequest
from testing.postgres import PostgresSandbox


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.passwords = Passwords()

    def setUp(self):
        self.db = PostgresSandbox(seed_learners=False)
        self.addCleanup(self.db.close)
        self.now = datetime.now(timezone.utc)
        self.repository = PostgresIdentityRepository(self.db.sessions)
        self.service = AuthService(self.repository,
            clock=lambda: self.now, passwords=self.passwords)

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

    def test_change_password_preserves_identity_and_current_session_revokes_other_sessions(self):
        first = self.register()
        other = self.service.login(LoginRequest(username='alice', password='a long unique passphrase'))
        unrelated = self.register('bob')
        principal = self.service.authenticate(first.access_token)
        self.service.change_password(ChangePasswordRequest(old_password='a long unique passphrase',
            new_password='a different unique passphrase'), principal=principal)
        self.assertEqual(self.service.authenticate(first.access_token), principal)
        self.service.authenticate(unrelated.access_token)
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(other.access_token)
        with self.assertRaises(AuthenticationError):
            self.service.login(LoginRequest(username='alice', password='a long unique passphrase'))
        logged_in = self.service.login(LoginRequest(username='alice', password='a different unique passphrase'))
        self.assertEqual(logged_in.learner_id, first.learner_id)
        self.assertEqual(logged_in.user_id, first.user_id)
        self.assertTrue(self.repository.get_account('alice').password_hash.startswith('$argon2id$'))

    def test_wrong_current_password_does_not_change_password_or_revoke_sessions(self):
        first = self.register()
        other = self.service.login(LoginRequest(username='alice', password='a long unique passphrase'))
        before = self.repository.get_account('alice')
        with self.assertRaises(PasswordChangeError):
            self.service.change_password(ChangePasswordRequest(old_password='wrong',
                new_password='a different unique passphrase'), principal=self.service.authenticate(first.access_token))
        self.assertEqual(self.repository.get_account('alice'), before)
        self.service.authenticate(first.access_token)
        self.service.authenticate(other.access_token)

    def test_stale_password_change_cannot_overwrite_new_password(self):
        first = self.register()
        principal = self.service.authenticate(first.access_token)
        stale = self.repository.get_account('alice')
        self.service.change_password(ChangePasswordRequest(old_password='a long unique passphrase',
            new_password='a different unique passphrase'), principal=principal)
        with self.assertRaises(AuthenticationError):
            self.repository.change_password(stale, self.passwords.hash('stale password overwrite'), principal.session_id, self.now)
        self.service.login(LoginRequest(username='alice', password='a different unique passphrase'))

    def test_password_change_requires_active_session(self):
        first = self.register()
        principal = self.service.authenticate(first.access_token)
        self.service.logout(first.access_token)
        with self.assertRaises(AuthenticationError):
            self.service.change_password(ChangePasswordRequest(old_password='a long unique passphrase',
                new_password='a different unique passphrase'), principal=principal)

    def test_password_change_cookie_route_validation_origin_and_authentication(self):
        payload = {'old_password': 'a long unique passphrase', 'new_password': 'a different unique passphrase'}
        with self.cookie_client() as client:
            self.assertEqual(client.post('/api/v1/auth/change-password', json=payload).status_code, 401)
            client.post('/api/v1/auth/register', json={'username': 'alice', 'password': payload['old_password']})
            self.assertEqual(client.post('/api/v1/auth/change-password', json=payload,
                headers={'Origin': 'https://attacker.example'}).status_code, 403)
            for changes in ({'new_password': 'short'}, {'old_password': ''}, {'user_id': 'injected'}, {'new_password': 'x' * 257}):
                self.assertEqual(client.post('/api/v1/auth/change-password', json=payload | changes).status_code, 422)
            bad = client.post('/api/v1/auth/change-password', json=payload | {'old_password': 'wrong'})
            self.assertEqual(bad.status_code, 400)
            self.assertEqual(bad.json()['error']['code'], 'PASSWORD_CHANGE_FAILED')
            response = client.post('/api/v1/auth/change-password', json=payload)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b'')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(client.get('/api/v1/auth/me').status_code, 200)

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

    def test_request_validation(self):
        with self.assertRaises(ValidationError):
            RegisterRequest(username='alice', password='short')
        with self.assertRaises(ValidationError):
            RegisterRequest(username='alice', password='a long unique passphrase', learner_id='injected')

    def test_authenticated_identity_drives_isolated_learner_engine(self):
        first, second = self.register('alice'), self.register('bob')
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
            from http.cookies import SimpleCookie
            parsed = SimpleCookie(cookie)
            self.assertTrue(2591990 <= int(parsed['mentra_session']['max-age']) <= 2592000)
            self.assertIn('Path=/api/v1', cookie)
            token = client.cookies.get('mentra_session')
            with self.db.engine.connect() as connection:
                session = connection.execute(select(auth_session)).mappings().one()
            self.assertEqual(session['expires_at'], self.now + timedelta(days=30))
            self.assertEqual(session['token_digest'], token_digest(token))
            later = self.now + timedelta(days=12)
            with patch.object(self.service, 'clock', return_value=later):
                restored = client.get('/api/v1/auth/me')
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(restored.json(), response.json())
                self.assertIn('Max-Age=', restored.headers['set-cookie'])
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

    def test_cookie_secure_flags_and_expiry_are_preserved(self):
        from app.auth import cookies
        from app.core.config import Settings
        configured = Settings(_env_file=None, auth_cookie_secure=True, auth_cookie_same_site='none')
        with patch.object(cookies, 'settings', configured), self.cookie_client() as client:
            response = client.post('/api/v1/auth/register', json={'username': 'alice', 'password': 'a long unique passphrase'})
            self.assertEqual(response.status_code, 201)
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertIn('SameSite=none', response.headers['set-cookie'])
            with self.db.engine.connect() as connection:
                self.assertIsNotNone(connection.execute(select(auth_session.c.expires_at)).scalar_one())

    def test_persistent_session_migration_downgrade_preserves_and_revokes_sessions(self):
        request = RegisterRequest(username='alice', password='a long unique passphrase')
        response = self.service.register(request, persistent=True)
        # Rehearse an actual legacy unbounded session, not a new-policy session.
        from sqlalchemy import update
        with self.db.sessions.begin() as session:
            session.execute(update(auth_session).values(expires_at=None))
        with self.db.engine.begin() as connection:
            command.downgrade(migration_config(connection), '20261007_0001')
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(response.access_token)
        self.assertEqual(self.count(auth_session), 1)
        upgrade(self.db.engine)
        with self.db.engine.connect() as connection:
            command.check(migration_config(connection))

    def test_new_persistent_sessions_expire_but_legacy_sessions_are_preserved(self):
        response = self.service.register(RegisterRequest(username='alice', password='a long unique passphrase'), persistent=True)
        self.assertEqual(response.expires_at, self.now + timedelta(days=30))
        with patch.object(self.service, 'clock', return_value=self.now + timedelta(days=30)):
            with self.assertRaises(AuthenticationError):
                self.service.authenticate(response.access_token)
        from sqlalchemy import update
        with self.db.sessions.begin() as session:
            session.execute(update(auth_session).values(expires_at=None))
        with patch.object(self.service, 'clock', return_value=self.now + timedelta(days=730)):
            self.assertEqual(self.service.authenticate(response.access_token).learner_id, response.learner_id)
        self.assertEqual(self.repository.cleanup_sessions(self.now + timedelta(days=730)), 0)

    def test_legacy_platform_sessions_are_rejected_without_deleting_records(self):
        from uuid import uuid4
        legacy_token = 'x' * 43
        owner = str(uuid4())
        with self.db.engine.begin() as connection:
            connection.execute(learner.insert().values(id=owner, created_at=self.now))
            connection.execute(external_identity.insert().values(provider='retired-platform',
                external_subject_id='legacy-student', learner_id=owner, created_at=self.now))
            connection.execute(auth_session.insert().values(session_id=str(uuid4()), learner_id=owner,
                provider='retired-platform', token_digest=token_digest(legacy_token),
                created_at=self.now, expires_at=self.now + timedelta(hours=1)))
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(legacy_token)
        self.assertEqual(self.count(learner), 1)
        self.assertEqual(self.count(external_identity), 1)
        self.assertEqual(self.count(auth_session), 1)
