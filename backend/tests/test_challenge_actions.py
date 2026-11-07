import unittest
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import Mock
from sqlalchemy import select,update,func
from app.chat.schemas import SendTurn
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.tables import turns,conversations
from app.challenge.schemas import ChallengeAction
from app.challenge.repositories.tables import choices
from app.challenge.repositories.actions import queue_action
from app.assessments.generation_worker import AssessmentGenerationWorker
from app.langchain.orchestration_service import OrchestrationService
from app.rag.schemas import ChatSelection
from app.core.exceptions import AppError
from tests import test_assessments as fixtures


class ChallengeActionTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.AssessmentTests.setUp

    def test_browser_requests_have_independent_tool_binding_state(self):
        from testing.browser_auth_server import BrowserModelFactory
        from testing.history_model import HistoryChatFactory
        from pydantic import BaseModel
        class Empty(BaseModel):pass
        factory=BrowserModelFactory(HistoryChatFactory())
        first,second=factory.get_model(),factory.get_model()
        self.assertIsNot(first,second)
        first.bind_tools([SimpleNamespace(name='first',args_schema=Empty)])
        second.bind_tools([SimpleNamespace(name='second',args_schema=Empty)])
        self.assertEqual(first.available_tools,{'first'})
        self.assertEqual(second.available_tools,{'second'})

    async def original(self):
        self.chat=ChatRepository(self.db.sessions)
        conversation=str(uuid4());seed=str(uuid4())
        self.chat.begin_turn(self.owner,SendTurn(conversation_id=conversation,client_turn_id=seed,expected_revision=0,content='Practice'))
        with self.db.sessions.begin() as session:
            session.execute(update(turns).where(turns.c.id==seed).values(state='SUCCEEDED',lease_until=None))
        card=await self.service.generate_chat(self.owner,conversation,self.request.model_copy(update={'client_request_id':uuid4(),'count':3,'question_format':'mcq','language':'en'}))
        return conversation,card

    def action(self,conversation,card,**changes):
        body=ChallengeAction(source_kind='draft',source_id=card['id'],expected_revision=card['assessment']['revision'],direction='harder').model_copy(update=changes)
        with self.db.sessions() as session:
            revision=session.scalar(select(conversations.c.revision).where(conversations.c.id==conversation))
        identifier=str(uuid4())
        self.chat.begin_turn(self.owner,SendTurn(conversation_id=conversation,client_turn_id=identifier,expected_revision=revision,
            content=f'Make “{card["assessment"]["title"]}” harder.',challenge_action=body))
        return dict(turn_id=identifier,conversation_id=conversation,challenge_action=body.model_dump(mode='json'))

    async def test_typed_action_skips_chat_model_records_receipt_and_replays_one_job(self):
        conversation,card=await self.original()
        scope=self.action(conversation,card)
        chat=SimpleNamespace(reply=AsyncMock(side_effect=AssertionError('The chat model must not run')))
        orchestrator=OrchestrationService(chat,assessments=self.service)
        response=await orchestrator.chat_reply([('user','Harder please')],ChatSelection(),self.owner,history_scope=scope)
        self.assertEqual(response.response_outcome['state'],'in_progress')
        chat.reply.assert_not_awaited()
        job=queue_action(self.service,self.owner,scope)
        self.assertEqual(job['id'],response.assessment_cards[0]['generation_job_id'])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(choices)),1)
            row=session.execute(select(choices)).mappings().one()
            self.assertEqual(row['direction'],'harder')
            self.assertIsNone(row['served_at'])
        await AssessmentGenerationWorker(self.service).run_once()
        completed=self.service.generation_jobs.get(self.owner,job['id'])
        self.assertEqual(completed['state'],'completed',completed)
        child=completed['result']['assessment']
        self.assertEqual(len(child['questions']),len(card['assessment']['questions']))
        self.assertEqual(child['preferences']['delivery'],card['assessment']['preferences']['delivery'])
        self.assertEqual([q['concept_ids'] for q in child['questions']],[q['concept_ids'] for q in card['assessment']['questions']])
        self.assertEqual(self.service.chat.detail(self.owner,card['id'])['assessment'],card['assessment'])
        with self.db.sessions() as session:
            self.assertIsNotNone(session.scalar(select(choices.c.served_at)))

    async def test_stale_and_foreign_sources_cannot_enqueue_choices(self):
        conversation,card=await self.original()
        scope=self.action(conversation,card,expected_revision=99)
        with self.assertRaises(AppError) as caught:queue_action(self.service,self.owner,scope)
        self.assertEqual(caught.exception.code,'REVISION_CONFLICT')
        with self.assertRaises(AppError):queue_action(self.service,self.other,scope)
        with self.db.sessions() as session:self.assertEqual(session.scalar(select(func.count()).select_from(choices)),0)

    async def test_source_change_during_background_generation_cannot_publish(self):
        conversation,card=await self.original()
        scope=self.action(conversation,card)
        job=queue_action(self.service,self.owner,scope)
        paper=card['assessment']
        self.service.repository.review_item(self.owner,card['assessment_id'],paper['questions'][0]['id'],paper['revision'],str(uuid4()),'wrong_answer')
        await AssessmentGenerationWorker(self.service).run_once()
        value=self.service.generation_jobs.get(self.owner,job['id'])
        self.assertEqual(value['state'],'failed')
        self.assertIsNone(value['result'])
        with self.db.sessions() as session:self.assertIsNone(session.scalar(select(choices.c.served_at)))

    async def test_choice_metadata_is_part_of_chat_retry_identity(self):
        conversation,card=await self.original()
        scope=self.action(conversation,card)
        body=SendTurn(conversation_id=conversation,client_turn_id=scope['turn_id'],expected_revision=0,
            content=f'Make “{card["assessment"]["title"]}” harder.',challenge_action=scope['challenge_action'])
        self.assertFalse(self.chat.begin_turn(self.owner,body)['run'])
        with self.assertRaises(AppError):
            self.chat.begin_turn(self.owner,body.model_copy(update={'challenge_action':body.challenge_action.model_copy(update={'direction':'easier'})}))

    async def test_full_chat_action_skips_history_model_admission_and_duplicate_learner_capture(self):
        from app.chat.service import ConversationService
        from app.langchain.repositories.evidence_tables import jobs as chat_jobs
        conversation,card=await self.original()
        with self.db.sessions() as session:revision=session.scalar(select(conversations.c.revision).where(conversations.c.id==conversation))
        body=SendTurn(conversation_id=conversation,client_turn_id=uuid4(),expected_revision=revision,
            content=f'Make “{card["assessment"]["title"]}” harder.',challenge_action=ChallengeAction(source_kind='draft',
                source_id=card['id'],expected_revision=1,direction='harder'))
        admission=SimpleNamespace(acquire=Mock(side_effect=AssertionError('No foreground model reservation')),release=Mock())
        service=ConversationService(self.chat,admission=admission)
        service.summaries=SimpleNamespace(load_context=AsyncMock(side_effect=AssertionError('No history/summary load')))
        chat=SimpleNamespace(reply=AsyncMock(side_effect=AssertionError('No chat model')))
        orchestrator=OrchestrationService(chat,assessments=self.service)
        async def generate(messages,selection,scope):
            self.assertEqual(len(messages),1)
            return (await orchestrator.chat_reply(messages,ChatSelection(**selection),self.owner,history_scope=scope)).model_dump(mode='json')
        result=await service.send(self.owner,body,generate,with_scope=True)
        self.assertEqual(result['turn']['state'],'SUCCEEDED',result['turn'])
        self.assertEqual(result['turn']['response_outcome']['state'],'in_progress')
        admission.acquire.assert_not_called();chat.reply.assert_not_awaited()
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(chat_jobs)),0)
            self.assertEqual(session.scalar(select(func.count()).select_from(choices)),1)
        await service.close()
