import unittest
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func
from app.db.admission import Admission, rates, leases
from app.core.exceptions import AppError
from testing.postgres import PostgresSandbox


class AdmissionTests(unittest.TestCase):
    def test_auth_rate_admission_happens_before_password_verification(self):
        from unittest.mock import Mock
        from app.auth.service import AuthService
        from app.auth.schemas import LoginRequest
        from app.auth.errors import AuthenticationError
        from app.auth.repositories.postgres import PostgresIdentityRepository
        from app.core.config import Settings
        gate = Admission(self.db.sessions, settings=Settings(_env_file=None, auth_account_minute_limit=2))
        passwords = Mock()
        passwords.verify.return_value = False
        service = AuthService(PostgresIdentityRepository(self.db.sessions), passwords=passwords, admission=gate)
        body = LoginRequest(username='unknown-user', password='wrong')
        for _ in range(2):
            with self.assertRaises(AuthenticationError):
                service.login(body, client_key='127.0.0.1')
        with self.assertRaises(AppError) as error:
            service.login(body, client_key='127.0.0.1')
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(passwords.verify.call_count, 2)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(leases)), 0)

    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.now = datetime.now(timezone.utc)
        self.gate = Admission(self.db.sessions, clock=lambda: self.now)

    def test_concurrent_process_instances_share_capacity_and_release(self):
        def claim(_):
            try:
                return Admission(self.db.sessions).acquire('test', 'owner', capacity=4, owner_capacity=2)
            except AppError as error:
                self.assertEqual(error.status_code, 429)
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = [token for token in pool.map(claim, range(8)) if token]
        self.assertEqual(len(accepted), 2)
        for token in accepted:
            self.gate.release(token)
        token = self.gate.acquire('test', 'other', capacity=4, owner_capacity=2)
        self.gate.release(token)

    def test_rate_is_durable_and_resets_without_unbounded_keys(self):
        for _ in range(2):
            with self.gate.reserve('auth', 'owner', capacity=4, owner_capacity=2,
                                   rate_keys=[('account', 'alice', 2)]):
                pass
        with self.assertRaises(AppError):
            self.gate.acquire('auth', 'owner', capacity=4, owner_capacity=2, rate_keys=[('account', 'alice', 2)])
        self.now += timedelta(seconds=61)
        with self.gate.reserve('auth', 'owner', capacity=4, owner_capacity=2, rate_keys=[('account', 'alice', 2)]):
            pass
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(rates)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(leases)), 0)

    def test_expired_reservation_recovers_after_crash(self):
        self.gate.acquire('test', 'owner', capacity=1, owner_capacity=1, seconds=1)
        self.now += timedelta(seconds=2)
        with self.gate.reserve('test', 'other', capacity=1, owner_capacity=1):
            pass

    def test_chat_rejection_precedes_turn_and_replay_bypasses_capacity(self):
        import asyncio
        from uuid import uuid4
        from app.chat.service import ConversationService
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.repositories.tables import turns
        from app.chat.schemas import SendTurn
        from testing.identities import learner_id
        owner = learner_id('alice')
        service = ConversationService(ChatRepository(self.db.sessions), admission=self.gate)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Hello')
        async def generate(*args):
            return dict(content='Hello back')
        tokens = [self.gate.acquire('model', owner, capacity=16, owner_capacity=2) for _ in range(2)]
        with self.assertRaises(AppError):
            asyncio.run(service.send(owner, request, generate))
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(turns)), 0)
        for token in tokens:
            self.gate.release(token)

        result = asyncio.run(service.send(owner, request, generate))
        self.assertEqual(result['turn']['state'], 'SUCCEEDED')
        from unittest.mock import patch
        with patch.object(service.repository, '_sync_lock', side_effect=AssertionError('Status is read-only')):
            self.assertEqual(service.repository.status(owner, str(request.conversation_id))['turn']['state'], 'SUCCEEDED')
        tokens = [self.gate.acquire('model', owner, capacity=16, owner_capacity=2) for _ in range(2)]
        replay = asyncio.run(service.send(owner, request, generate))
        self.assertEqual(replay['turn']['state'], 'SUCCEEDED')
        for token in tokens:
            self.gate.release(token)

    def test_disconnect_during_admission_does_not_abandon_running_turn(self):
        import asyncio
        import time
        from uuid import uuid4
        from unittest.mock import patch
        from app.chat.service import ConversationService
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        from testing.identities import learner_id
        owner = learner_id('bob')
        repository = ChatRepository(self.db.sessions)
        service = ConversationService(repository, admission=self.gate)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Hello')
        original = repository.begin_turn
        def delayed(*args, **kwargs):
            time.sleep(.15)
            return original(*args, **kwargs)
        async def generate(*args):
            return dict(content='Completed after disconnect')
        async def verify():
            with patch.object(repository, 'begin_turn', side_effect=delayed):
                task = asyncio.create_task(service.send(owner, request, generate))
                await asyncio.sleep(.05)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await asyncio.gather(*list(service.tasks))
            self.assertEqual(repository.status(owner, str(request.conversation_id))['turn']['state'], 'SUCCEEDED')
            await service.close()
        asyncio.run(verify())
