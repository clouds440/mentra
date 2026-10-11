import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from pydantic import ValidationError
from app.chat.interactions import ChoiceContent, ChoiceCard, InteractionResponse, create_interaction_tools
from app.chat.response import ChatResponse
from app.chat.schemas import SendTurn
from app.chat.repositories.postgres import ChatRepository
from app.core.exceptions import AppError
from app.history_management.budgets import ToolBudget
from testing.postgres import PostgresSandbox
from testing.identities import learner_id

class ChoiceSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_ids_stable_and_schema_rejects_code_or_duplicate_ids(self):
        args = dict(kind='multiple_choice', question='Choose', options=[dict(id='a', label='A'),dict(id='b',label='B')])
        scope = dict(current_user_message_id=str(uuid4()))
        tool = create_interaction_tools('owner', scope, ToolBudget())[0]
        first = await tool.ainvoke(args)
        second = await tool.ainvoke(args)
        self.assertEqual(first['interaction_id'], second['interaction_id'])
        self.assertEqual(len(scope['interactions']), 1)
        self.assertEqual(len(ChatResponse(content='', interactions=scope['interactions']).interactions), 1)
        for bad in [dict(args, code='alert(1)'),dict(args,options=[dict(id='a',label='A'),dict(id='a',label='B')])]:
            with self.assertRaises(ValidationError): ChoiceContent(**bad)

class ChoicePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=PostgresSandbox(); cls.repo=ChatRepository(cls.db.sessions)
        cls.owner=learner_id('alice'); cls.other=learner_id('bob')
    @classmethod
    def tearDownClass(cls): cls.db.close()
    def prepare(self, kind='multiple_choice'):
        request=SendTurn(conversation_id=uuid4(),client_turn_id=uuid4(),expected_revision=0,content='Choose topics')
        job=self.repo.begin_turn(self.owner,request)
        card=ChoiceCard(id=uuid4(),kind=kind,question='Choose topics',options=[dict(id='a',label='Algebra'),dict(id='b',label='Biology')]).model_dump(mode='json')
        self.repo.finish(self.owner,job,dict(content='Please choose.',interactions=[card]))
        page=self.repo.history(self.owner,str(request.conversation_id))
        response=InteractionResponse(message_id=page['items'][-1]['id'],interaction_id=card['id'],selected=['b','a'] if kind=='multiple_choice' else ['a'])
        body=SendTurn(conversation_id=request.conversation_id,client_turn_id=uuid4(),expected_revision=page['conversation']['revision'],content='forged text',interaction_response=response)
        return body
    def test_atomic_persistence_replay_and_context(self):
        body=self.prepare(); job=self.repo.begin_turn(self.owner,body)
        page=self.repo.history(self.owner,str(body.conversation_id))
        self.assertEqual(page['items'][-1]['content'],'Choose topics\nSelected: a: Algebra; b: Biology')
        self.assertEqual(page['items'][1]['interactions'][0]['submitted_turn_id'],str(body.client_turn_id))
        self.assertEqual(page['items'][-1]['interaction_response']['selected'],['b','a'])
        self.assertFalse(self.repo.begin_turn(self.owner,body)['run'])
        self.repo.finish(self.owner,job,error='Retry me')
        self.assertTrue(self.repo.begin_turn(self.owner,body.model_copy(update={'retry':True}))['run'])
        self.assertEqual(len(self.repo.history(self.owner,str(body.conversation_id))['items']),3)
    def test_ownership_message_and_input_validation_roll_back(self):
        body=self.prepare('single_choice')
        for bad in [body.model_copy(update={'interaction_response':body.interaction_response.model_copy(update={'selected':['a','b']})}),
                    body.model_copy(update={'interaction_response':body.interaction_response.model_copy(update={'selected':['x']})}),
                    body.model_copy(update={'interaction_response':body.interaction_response.model_copy(update={'message_id':uuid4()})})]:
            with self.assertRaises(AppError): self.repo.begin_turn(self.owner,bad)
        with self.assertRaises(AppError): self.repo.begin_turn(self.other,body)
        page=self.repo.history(self.owner,str(body.conversation_id))
        self.assertFalse(page['items'][1]['interactions'][0]['submitted_turn_id'])
        self.assertEqual(len(page['items']),2)
    def test_concurrent_and_changed_duplicate_submissions_rejected(self):
        body=self.prepare()
        def send(identifier):
            try: return self.repo.begin_turn(self.owner,body.model_copy(update={'client_turn_id':identifier}))['run']
            except AppError: return False
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(send,[uuid4(),uuid4()]))
        self.assertEqual(outcomes.count(True),1)
        page=self.repo.status(self.owner,str(body.conversation_id))
        self.repo.finish(self.owner,dict(turn_id=page['turn']['id'],conversation_id=str(body.conversation_id),attempt=1,user_sequence=page['turn']['user_sequence']),dict(content='Continued'))
        with self.assertRaises(AppError): self.repo.begin_turn(self.owner,body.model_copy(update={'expected_revision':self.repo.history(self.owner,str(body.conversation_id))['conversation']['revision']}))
