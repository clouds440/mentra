import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import update, select, func
from app.chat.repositories.attachments import AttachmentRepository
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.tables import attachments
from app.chat.schemas import SendTurn
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class AttachmentMaintenanceTests(unittest.TestCase):
    def test_cleanup_is_bounded_and_preserves_bound_files(self):
        with PostgresSandbox() as db:
            owner = learner_id('alice')
            repository = AttachmentRepository(db.sessions)
            unsent = repository.create(owner, 'old.txt', b'old')
            bound = repository.create(owner, 'bound.txt', b'bound')
            ChatRepository(db.sessions).begin_turn(owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(),
                expected_revision=0, content='File', attachment_ids=[bound['id']]))
            with db.sessions.begin() as session:
                session.execute(update(attachments).values(created_at=datetime.now(timezone.utc) - timedelta(days=2)))
            self.assertEqual(repository.cleanup_unsent(limit=1), 1)
            with db.sessions() as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(attachments)), 1)
                self.assertEqual(session.scalar(select(attachments.c.id)), bound['id'])
            self.assertEqual(repository.cleanup_unsent(), 0)
