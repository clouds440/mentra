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
