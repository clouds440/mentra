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

class RichInteractionSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_blank_selection_is_canonical_empty_not_a_server_error(self):
        from app.chat.interactions import InputCard, InputField, resolve_choice
        card = InputCard(id=uuid4(), kind='form', question='Preferences', fields=[dict(id='depth', kind='select', label='Depth', required=False, options=[dict(id='brief', label='Brief')])]).model_dump(mode='json')
        reply = InteractionResponse(message_id=uuid4(), interaction_id=card['id'], values={'depth': '  '})
        self.assertEqual(resolve_choice([card], reply)[1], 'Preferences\nDepth: ')
        with self.assertRaises(ValidationError):
            InputField(id='depth', kind='select', label='Depth', max_length=1, options=[dict(id='brief', label='Brief')])

    async def test_custom_input_and_form_tools_are_typed_and_static_visuals_do_not_submit(self):
        from app.chat.interactions import ChatChoiceContent, InputContent, ValueBar, resolve_choice
        args = dict(kind='single_choice', question='Choose a topic', options=[dict(id='known', label='Known'), dict(id='custom', label='Other', input=dict(label='Your topic'))])
        scope = dict(current_user_message_id=str(uuid4()))
        tools = {tool.name: tool for tool in create_interaction_tools('owner', scope, ToolBudget())}
        self.assertEqual(set(tools), {'present_choices', 'request_input', 'present_visuals'})
        await tools['present_choices'].ainvoke(args)
        card = scope['interactions'][0]
        reply = InteractionResponse(message_id=uuid4(), interaction_id=card['id'], selected=['custom'], option_inputs={'custom': 'درخت — indexes'})
        self.assertIn('درخت — indexes', resolve_choice([card], reply)[1])
        for inputs in [{}, {'custom': '   '}, {'unknown': 'value'}, {'custom': 'x' * 301}]:
            with self.assertRaises(AppError): resolve_choice([card], reply.model_copy(update={'option_inputs': inputs}))
        with self.assertRaises(AppError): resolve_choice([card], reply.model_copy(update={'selected': ['known']}))
        # Shared assessment options must still reject attached chat input.
        with self.assertRaises(ValidationError): ChoiceContent(**args)
        self.assertEqual(ChatChoiceContent(**args).options[1].input.max_length, 300)
        form = dict(kind='form', question='Study setup', fields=[dict(id='minutes', kind='number', label='Minutes', minimum=5, maximum=60), dict(id='depth', kind='select', label='Depth', options=[dict(id='brief', label='Brief')])])
        await tools['request_input'].ainvoke(form)
        formcard = scope['interactions'][1]
        response = InteractionResponse(message_id=uuid4(), interaction_id=formcard['id'], values={'minutes': '20', 'depth': 'brief'})
        self.assertIn('Depth: Brief', resolve_choice([formcard], response)[1])
        for values in [{'minutes':'NaN','depth':'brief'}, {'minutes':'70','depth':'brief'}, {'minutes':'20','depth':'unknown'}, {'minutes':'20','depth':'brief','extra':'x'}]:
            with self.assertRaises(AppError): resolve_choice([formcard], response.model_copy(update={'values': values}))
        for bad in [dict(form, fields=form['fields'] * 2), dict(kind='text_input', question='Question', fields=form['fields'])]:
            with self.assertRaises(ValidationError): InputContent(**bad)
        visual_tool = create_interaction_tools('owner', scope, ToolBudget())[2]
        receipt = await visual_tool.ainvoke(dict(question='Relative difficulty', bars=[dict(label='Concept A', value=3, max=5, note='Illustrative')]))
        self.assertIn('no user input', receipt['next_step'])
        static = scope['interactions'][2]
        self.assertEqual(ChatResponse(content='', interactions=scope['interactions']).interactions[-1].kind, 'value_bars')
        with self.assertRaises(AppError): resolve_choice([static], InteractionResponse(message_id=uuid4(), interaction_id=static['id']))
        for value in [float('nan'), -1, 6]:
            with self.assertRaises(ValidationError): ValueBar(label='Difficulty', value=value, max=5)

    async def test_ui_guidance_is_composed_once_and_versioned(self):
        from app.langchain.prompts import get_system_prompt, get_prompt_version, PromptSource
        from app.langchain.prompts.chat_ui import SYSTEM_PROMPT, VERSION
        prompt = get_system_prompt(PromptSource.CHAT)
        self.assertEqual(prompt.count(SYSTEM_PROMPT), 1)
        self.assertIn(VERSION, get_prompt_version(PromptSource.CHAT))
        self.assertIn('present_visuals', prompt)


class RichInteractionPersistenceTests(ChoicePersistenceTests):
    def test_custom_values_are_atomic_replayable_and_restore_from_history(self):
        from app.chat.interactions import InputCard
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Choose')
        job = self.repo.begin_turn(self.owner, request)
        card = ChoiceCard(id=uuid4(), kind='single_choice', question='Topic?', options=[dict(id='a',label='Algebra'),dict(id='custom',label='Other',input=dict(label='Your topic'))]).model_dump(mode='json')
        self.repo.finish(self.owner, job, dict(content='Choose', interactions=[card]))
        page = self.repo.history(self.owner, str(request.conversation_id))
        reply = InteractionResponse(message_id=page['items'][-1]['id'], interaction_id=card['id'], selected=['custom'], option_inputs={'custom':'Database indexes'})
        body = SendTurn(conversation_id=request.conversation_id, client_turn_id=uuid4(), expected_revision=page['conversation']['revision'], content='forged', interaction_response=reply)
        accepted = self.repo.begin_turn(self.owner, body)
        self.assertFalse(self.repo.begin_turn(self.owner, body)['run'])
        history = self.repo.history(self.owner, str(request.conversation_id))
        self.assertIn('Database indexes', history['items'][-1]['content'])
        self.assertNotIn('forged', history['items'][-1]['content'])
        self.assertEqual(history['items'][1]['interactions'][0]['option_inputs'], {'custom':'Database indexes'})
        self.repo.finish(self.owner, accepted, dict(content='Next'))
        # A separate text-input turn follows the same durable path.
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Ask')
        job = self.repo.begin_turn(self.owner, request)
        card = InputCard(id=uuid4(), kind='text_input', question='Topic?', fields=[dict(id='topic',label='Your topic')]).model_dump(mode='json')
        self.repo.finish(self.owner, job, dict(content='Enter', interactions=[card]))
        page = self.repo.history(self.owner, str(request.conversation_id))
        reply = InteractionResponse(message_id=page['items'][-1]['id'], interaction_id=card['id'], values={'topic':'Quantum mechanics'})
        body = SendTurn(conversation_id=request.conversation_id, client_turn_id=uuid4(), expected_revision=page['conversation']['revision'], content='forged', interaction_response=reply)
        self.repo.begin_turn(self.owner, body)
        history = self.repo.history(self.owner, str(request.conversation_id))
        self.assertEqual(history['items'][1]['interactions'][0]['values'], {'topic':'Quantum mechanics'})
        self.assertIn('Your topic: Quantum mechanics', history['items'][-1]['content'])

    def test_legacy_choice_request_fingerprint_is_unchanged(self):
        import json
        from hashlib import sha256
        body = self.prepare('single_choice')
        base = sha256(json.dumps([str(body.conversation_id), body.content, body.retrieval.model_dump(mode='json')], sort_keys=True).encode()).hexdigest()
        old_reply = body.interaction_response.model_dump_json(exclude={'option_inputs','values'})
        expected = sha256((base + old_reply).encode()).hexdigest()
        self.assertEqual(self.repo._request_hash(body), expected)
