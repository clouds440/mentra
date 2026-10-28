import json
import unittest
from hashlib import sha256
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from app.chat.interactions import QuestionnaireCard, InteractionResponse, create_interaction_tools
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.chat.response import ChatResponse
from app.core.exceptions import AppError
from app.history_management.budgets import ToolBudget
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


def questions(count=5):
    return [dict(id=f'q{i}', kind='single_choice', question=f'Preference question {i}',
        options=[dict(id=f'o{j}', label=f'Option {j}') for j in range(1, 6)]) for i in range(1, count + 1)]


class QuestionnaireSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_twenty_questions_preserve_every_option_without_using_domain_writes(self):
        scope = dict(current_user_message_id=str(uuid4()))
        budget = ToolBudget(writes=2)
        tools = {tool.name:tool for tool in create_interaction_tools('owner', scope, budget)}
        await tools['present_questionnaire'].ainvoke(dict(question='Getting started', questions=questions(20)))
        result = ChatResponse(content='Please answer.', interactions=scope['interactions'])
        self.assertEqual(len(result.interactions[0].questions), 20)
        self.assertTrue(all(len(q.options) == 5 for q in result.interactions[0].questions))
        self.assertEqual(budget.writes, 2)

    async def test_five_legacy_calls_are_not_rejected_after_two_writes(self):
        scope = dict(current_user_message_id=str(uuid4()))
        budget = ToolBudget()
        tool = next(tool for tool in create_interaction_tools('owner', scope, budget) if tool.name == 'present_choices')
        for question in questions():
            await tool.ainvoke({key:value for key,value in question.items() if key != 'id'})
        self.assertEqual(len(ChatResponse(content='', interactions=scope['interactions']).interactions), 5)
        self.assertEqual(budget.writes, 0)
        self.assertEqual(budget.calls, 0)
        self.assertEqual(budget.presentations, 5)

    def test_legacy_interaction_fingerprint_is_unchanged(self):
        body = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=1, content='Answer',
            interaction_response=InteractionResponse(message_id=uuid4(), interaction_id=uuid4(), selected=['a']))
        base = sha256(json.dumps([str(body.conversation_id), body.content, body.retrieval.model_dump(mode='json')], sort_keys=True).encode()).hexdigest()
        old = json.dumps(dict(message_id=str(body.interaction_response.message_id),
            interaction_id=str(body.interaction_response.interaction_id), selected=['a']), separators=(',', ':'))
        self.assertEqual(ChatRepository._request_hash(body), sha256((base + old).encode()).hexdigest())

    def test_resume_keeps_new_common_questionnaire_tool_available(self):
        from types import SimpleNamespace
        from app.langchain.response_runtime import ResponseRuntime
        from app.langchain.tool_selection import ToolSelection
        scope = dict(current_user_message_id=str(uuid4()))
        budget = ToolBudget()
        tools = create_interaction_tools('owner', scope, budget)
        selection = ToolSelection(tools, {tool.name:'chat' for tool in tools}, scope)
        runtime = ResponseRuntime([], scope, budget, selection, SimpleNamespace())
        snapshot = runtime.capture()
        snapshot['active'] = snapshot['pending'] = ['present_choices']
        snapshot['policy_version']='response-v2'
        runtime.restore(snapshot)
        self.assertIn('present_questionnaire', selection.active)


class QuestionnairePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.repo = ChatRepository(cls.db.sessions)
        cls.owner, cls.other = learner_id('alice'), learner_id('bob')

    @classmethod
    def tearDownClass(cls): cls.db.close()

    def prepare(self, legacy=False):
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Ask about my goals')
        job = self.repo.begin_turn(self.owner, request)
        if legacy:
            cards = [dict(id=str(uuid4()), **{key:value for key,value in q.items() if key != 'id'}) for q in questions()]
            replies = [dict(interaction_id=card['id'], selected=['o1']) for card in cards]
            answer = dict(**replies[0], additional_responses=replies[1:])
        else:
            items = questions(4) + [dict(id='q5', kind='short_text', question='Anything else?')]
            items[0]['options'][-1]['input'] = dict(label='Your goal')
            items[2]['kind'] = 'multiple_choice'
            cards = [QuestionnaireCard(id=uuid4(), question='Getting started', questions=items).model_dump(mode='json')]
            answer = dict(interaction_id=cards[0]['id'], answers={
                'q1':dict(selected=['o5'], option_inputs={'o5':'Work conversations'}),
                'q2':dict(selected=['o1']), 'q3':dict(selected=['o1','o3']),
                'q4':dict(selected=['o2']), 'q5':dict(values={'answer':'Please use everyday examples.'})})
        self.repo.finish(self.owner, job, dict(content='Please answer.', interactions=cards))
        page = self.repo.history(self.owner, str(request.conversation_id))
        reply = InteractionResponse(message_id=page['items'][1]['id'], **answer)
        return SendTurn(conversation_id=request.conversation_id, client_turn_id=uuid4(),
            expected_revision=page['conversation']['revision'], content='forged labels', interaction_response=reply)

    def test_full_set_is_atomic_canonical_replayable_and_not_an_assessment(self):
        body = self.prepare()
        reply = body.interaction_response
        bad = reply.model_copy(update={'answers':dict(reply.answers, q4=reply.answers['q4'].model_copy(update={'selected':['forged']}))})
        for owner, request in ((self.owner, body.model_copy(update={'interaction_response':bad})), (self.other, body)):
            with self.assertRaises(AppError): self.repo.begin_turn(owner, request)
        before = self.repo.history(self.owner, str(body.conversation_id))
        self.assertIsNone(before['items'][1]['interactions'][0]['submitted_turn_id'])
        self.assertEqual(len(before['items']), 2)
        self.repo.begin_turn(self.owner, body)
        self.assertFalse(self.repo.begin_turn(self.owner, body)['run'])
        page = self.repo.history(self.owner, str(body.conversation_id))
        self.assertEqual(len(page['items']), 3)
        self.assertIn('Work conversations', page['items'][-1]['content'])
        self.assertIn('Please use everyday examples.', page['items'][-1]['content'])
        self.assertNotIn('forged labels', page['items'][-1]['content'])
        self.assertEqual(len(page['items'][1]['interactions'][0]['answers']), 5)
        with self.db.sessions() as session:
            for table in ('assessment', 'assessment_attempt', 'chat_assessment_draft', 'learning_evidence'):
                self.assertEqual(session.scalar(text(f'SELECT count(*) FROM {table}')), 0)

    def test_legacy_five_card_batch_rolls_back_and_submits_all_once(self):
        body = self.prepare(legacy=True)
        reply = body.interaction_response
        changed = list(reply.additional_responses)
        changed[-1] = changed[-1].model_copy(update={'selected':['invalid']})
        with self.assertRaises(AppError):
            self.repo.begin_turn(self.owner, body.model_copy(update={'interaction_response':reply.model_copy(update={'additional_responses':changed})}))
        self.assertTrue(all(not card.get('submitted_turn_id') for card in self.repo.history(self.owner, str(body.conversation_id))['items'][1]['interactions']))
        def submit(identifier):
            try: return self.repo.begin_turn(self.owner, body.model_copy(update={'client_turn_id':identifier}))['run']
            except AppError: return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(submit, [uuid4(), uuid4()])).count(True), 1)
        page = self.repo.history(self.owner, str(body.conversation_id))
        self.assertEqual(len({card['submitted_turn_id'] for card in page['items'][1]['interactions']}), 1)
        self.assertEqual(page['items'][-1]['content'].count('Preference question'), 5)
