import os
import unittest
from uuid import uuid4
from sqlalchemy import select,func
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.langchain.repositories.evidence import ChatEvidenceRepository
from app.langchain.repositories.evidence_tables import jobs

@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires dedicated database')
class EvidenceJobTests(unittest.TestCase):
    def setUp(self):
        self.db=PostgresSandbox();self.addCleanup(self.db.close)
        self.owner=learner_id('alice');self.chat=ChatRepository(self.db.sessions)
        self.conversation=uuid4()
        first=self.chat.begin_turn(self.owner,SendTurn(conversation_id=self.conversation,client_turn_id=uuid4(),expected_revision=0,content='Practice algebra'))
        self.chat.finish(self.owner,first,response={'content':'What is two plus two?'})
        revision=self.chat.status(self.owner,str(self.conversation))['conversation']['revision']
        self.job=self.chat.begin_turn(self.owner,SendTurn(conversation_id=self.conversation,client_turn_id=uuid4(),expected_revision=revision,content='Two plus two equals four.'))
        self.chat.finish(self.owner,self.job,response={'content':'Correct.'})

    def test_restart_claim_and_atomic_receipt_are_idempotent(self):
        repository=ChatEvidenceRepository(self.db.sessions)
        job=repository.claim()
        self.assertEqual(job['user']['content'],'Two plus two equals four.')
        self.assertIsNone(ChatEvidenceRepository(self.db.sessions).claim())
        repository.complete(job,lambda tx:None)
        with self.db.sessions() as session:
            self.assertEqual(session.execute(select(jobs.c.state)).scalar_one(),'ignored')
        self.assertIsNone(repository.claim())

    def test_chat_deletion_removes_pending_evidence_jobs(self):
        revision=self.chat.status(self.owner,str(self.conversation))['conversation']['revision']
        self.chat.edit(self.owner,str(self.conversation),revision,remove=True)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(jobs)),0)

    def test_busy_owner_is_skipped_without_waiting(self):
        from app.db.owner_transactions import OwnerTransactions
        from time import monotonic
        with OwnerTransactions(self.db.sessions).write(self.owner):
            started = monotonic()
            self.assertIsNone(ChatEvidenceRepository(self.db.sessions).claim())
            self.assertLess(monotonic() - started, 1)
        self.assertIsNotNone(ChatEvidenceRepository(self.db.sessions).claim())

    def test_exhausted_crashed_claim_becomes_terminal(self):
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import update
        repository = ChatEvidenceRepository(self.db.sessions)
        job = repository.claim()
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.turn_id == job['turn_id']).values(
                attempts=3, claim_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
        self.assertIsNone(repository.claim())
        with self.db.sessions() as session:
            row = session.execute(select(jobs)).mappings().one()
        self.assertEqual(row['state'], 'failed')
        self.assertIsNone(row['claim_id'])
        self.assertIsNone(row['retry_at'])
