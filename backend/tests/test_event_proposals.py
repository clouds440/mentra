import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, func
from app.core.exceptions import AppError
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.history_management.events.factory import create_events_service
from app.history_management.events.proposal_service import create_event_proposals
from app.history_management.events.proposals import EventManage, ProposalDecision
from app.history_management.repositories.events.tables import events, evidence
from app.langchain.repositories.checkpoint_tables import checkpoints, writes, blobs
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated database')
class EventProposalTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.owner, self.other = learner_id('alice'), learner_id('bob')
        self.chat = ChatRepository(self.db.sessions)
        self.events = create_events_service(self.db.sessions)
        self.service = create_event_proposals(self.db.sessions, self.events)
        question = 'My algebra exam is on October 20.'
        self.job = self.chat.begin_turn(self.owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content=question))
        row = self.chat.context_rows(self.owner, self.job['conversation_id'], self.job['user_sequence'])[-1]
        self.scope = dict(self.job, evidence_ids={row['id']})
        self.body = EventManage(message_id=row['id'], quote=question, candidate=dict(title='Algebra exam', kind='exam', timezone='UTC', local_date='2026-10-20'))

    def proposal(self): return self.service.create(self.owner, self.body, self.scope)['proposal']

    def test_approve_replay_restart_and_cleanup(self):
        proposal = self.proposal()
        body = ProposalDecision(expected_revision=proposal['revision'], decision='approve')
        result = self.service.decide(self.owner, proposal['id'], body)
        self.assertEqual(result.state, 'approved')
        restarted = create_event_proposals(self.db.sessions, self.events)
        self.assertEqual(restarted.decide(self.owner, proposal['id'], body).event_id, result.event_id)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(events)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(evidence)), 1)
            for table in (checkpoints, writes, blobs): self.assertEqual(session.scalar(select(func.count()).select_from(table)), 0)

    def test_owner_evidence_and_revision_rejection(self):
        proposal = self.proposal()
        with self.assertRaises(AppError): self.service.detail(self.other, proposal['id'])
        with self.assertRaises(AppError): self.service.decide(self.owner, proposal['id'], ProposalDecision(expected_revision=2, decision='approve'))
        invalid = self.body.model_copy(update={'quote':'Assistant invented event'})
        with self.assertRaises(AppError): self.service.create(self.owner, invalid, self.scope)

    def test_concurrent_approve_dismiss_has_one_winner(self):
        proposal = self.proposal()
        def decide(action):
            try: return self.service.decide(self.owner, proposal['id'], ProposalDecision(expected_revision=1, decision=action)).state
            except AppError: return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(decide, ['approve', 'dismiss']))
        self.assertEqual(results.count('rejected'), 1)
        self.assertIn(self.service.detail(self.owner, proposal['id']).state, ('approved', 'dismissed'))

    def test_deleting_chat_purges_proposal_and_checkpoint(self):
        proposal = self.proposal()
        self.service.graph.decide(self.owner, proposal['id'], 'approve')
        self.chat.edit(self.owner, self.job['conversation_id'], 2, remove=True)
        with self.assertRaises(AppError): self.service.detail(self.owner, proposal['id'])
        with self.db.sessions() as session:
            for table in (checkpoints, writes, blobs): self.assertEqual(session.scalar(select(func.count()).select_from(table)), 0)

    def test_expiry_and_capture_preference(self):
        proposal = self.proposal()
        self.service.repository.clock = lambda: datetime.now(timezone.utc) + timedelta(days=8)
        self.assertEqual(self.service.list(self.owner), [])
        with self.assertRaises(AppError): self.service.decide(self.owner, proposal['id'], ProposalDecision(expected_revision=1, decision='approve'))

    def test_graph_commit_failure_recovers_without_another_event(self):
        proposal = self.proposal()
        body = ProposalDecision(expected_revision=1, decision='approve')
        claim = self.service.repository.claim(self.owner, proposal['id'], body)
        self.service.graph.decide(self.owner, proposal['id'], 'approve')
        # Simulates restart between checkpoint advancement and the domain commit.
        restarted = create_event_proposals(self.db.sessions, self.events)
        result = restarted.repository.commit(self.owner, proposal['id'], claim['claim_id'])
        self.assertEqual(result.state, 'approved')
        self.assertEqual(restarted.decide(self.owner, proposal['id'], body).event_id, result.event_id)

    def test_model_admission_rejects_hypothetical_statement(self):
        import asyncio
        from app.history_management.events.proposals import EventAdmission
        class LLM:
            async def ainvoke(self,*args,**kwargs):
                return EventAdmission(supported=False,first_party=False,actual_event=False,complete_unambiguous=False,timezone_supported=False,confidence=1)
        self.service.llm=LLM()
        scope=dict(self.scope,context_rows=self.chat.context_rows(self.owner,self.job['conversation_id'],self.job['user_sequence']))
        result=asyncio.run(self.service.admit(self.owner,self.body,scope))
        self.assertEqual(result['outcome'],'rejected')
        self.assertEqual(self.service.list(self.owner),[])

    def test_uncertain_model_admission_preserves_reviewable_proposal(self):
        import asyncio
        from app.history_management.events.proposals import EventAdmission
        class LLM:
            async def ainvoke(self,*args,**kwargs):
                return EventAdmission(supported=True,first_party=True,actual_event=True,complete_unambiguous=False,timezone_supported=False,confidence=.7)
        self.service.llm=LLM()
        scope=dict(self.scope,context_rows=self.chat.context_rows(self.owner,self.job['conversation_id'],self.job['user_sequence']))
        result=asyncio.run(self.service.admit(self.owner,self.body,scope))
        self.assertEqual(result['outcome'],'awaiting_confirmation')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(events)),0)
