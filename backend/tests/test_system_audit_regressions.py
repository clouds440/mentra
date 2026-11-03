"""Offline reproductions for the November system audit; no provider calls."""
import os
import time
import unittest
from io import BytesIO
from uuid import uuid4
from sqlalchemy import select, update, func
from app.core.config import Settings
from app.core.exceptions import AppError
from app.files.provider import CloudinaryProvider
from app.files.service import FilesService
from app.files.tables import assets
from app.speech.service import SpeechService
from testing.files import MemoryFileProvider
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.tables import turns
from app.chat.schemas import SendTurn
from app.langchain.repositories.evidence import ChatEvidenceRepository
from app.langchain.repositories.evidence_tables import jobs


def nonreading_worker(connection, config):
    time.sleep(4)
    connection.close()


class SpeechDeadlineRegression(unittest.TestCase):
    def test_submission_is_inside_deadline(self):
        service = SpeechService(Settings(_env_file=None, speech_timeout_seconds=.1), worker_target=nonreading_worker)
        self.addCleanup(service.close)
        started = time.monotonic()
        with self.assertRaises(AppError) as error:
            service.transcribe(b'x' * (2 * 1024 * 1024), None)
        self.assertEqual(error.exception.code, 'SPEECH_TIMEOUT')
        self.assertLess(time.monotonic() - started, 2)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL required')
class AuditDatabaseRegressions(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.owner = learner_id('alice')

    def test_storage_override_upload_and_cleanup(self):
        config = Settings(_env_file=None, app_env='production', files_environment='development',
                          cloudinary_url='cloudinary://dummy:dummy@test',
                          frontend_origin='https://mentra.example',cors_origins='https://mentra.example')
        policy = CloudinaryProvider(config)
        self.addCleanup(policy.close)
        class Provider(MemoryFileProvider):
            def upload(self, path, row):
                policy._owned(row)
                return super().upload(path, row)
            def destroy(self, row):
                policy._owned(row)
                super().destroy(row)
        provider = Provider()
        files = FilesService(self.db.sessions, provider, config)
        stored = files.upload(self.owner, BytesIO(b'source'), 'source.txt', 'chat', 'override')
        with self.db.sessions() as session:
            row = session.execute(select(assets).where(assets.c.id == stored['id'])).mappings().one()
            self.assertTrue(row['public_id'].startswith('mentra/development/'))
        files.cancel(self.owner, stored['id'])
        files.cleanup()
        self.assertFalse(provider.objects)

    def evidence_turn(self):
        chat = ChatRepository(self.db.sessions)
        cid = str(uuid4())
        first = chat.begin_turn(self.owner, SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=0, content='Practice'))
        chat.finish(self.owner, first, response={'content': 'What is two plus two?'})
        revision = chat.status(self.owner, cid)['conversation']['revision']
        job = chat.begin_turn(self.owner, SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=revision, content='Four.'))
        return chat, job

    def test_partial_response_does_not_enqueue_evidence(self):
        chat, job = self.evidence_turn()
        chat.finish(self.owner, job, response={'content': 'Partly done.', 'response_outcome': dict(state='partial', retryable=True)})
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(jobs)), 0)

    def test_handoffs_and_review_waits_do_not_enqueue_evidence(self):
        for state in ('in_progress','awaiting_input','paused'):
            chat,job=self.evidence_turn()
            chat.finish(self.owner,job,response={'content':'Waiting.', 'response_outcome':dict(state=state)})
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(jobs)),0)

    def test_legacy_stale_job_is_retired(self):
        chat, job = self.evidence_turn()
        chat.finish(self.owner, job, response={'content': 'Correct.'})
        with self.db.sessions.begin() as session:
            session.execute(update(turns).where(turns.c.id == job['turn_id']).values(state='FAILED'))
        self.assertIsNone(ChatEvidenceRepository(self.db.sessions).claim())
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.state)), 'ignored')

    def test_enqueue_replay_is_idempotent(self):
        chat, job = self.evidence_turn()
        chat.finish(self.owner, job, response={'content': 'Correct.'})
        with self.db.sessions.begin() as session:
            ChatEvidenceRepository.queue(session, self.owner, job)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(jobs)), 1)
