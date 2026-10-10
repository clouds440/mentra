import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.chat.schemas import SendTurn
from app.chat.service import ConversationService
from app.chat.repositories.postgres import ChatRepository
from app.chat.titles import NewChatReply
from app.langchain.chat_service import ChatService
from app.langchain.llm import MentraLLM
from app.langchain.orchestration_service import OrchestrationService
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


def output(title='Understanding Photosynthesis', content='Plants turn light into energy.'):
    return AIMessage(content='', tool_calls=[dict(name='NewChatReply', id='answer',
        args=dict(content=content, conversation_title=title))])


class ScriptedModel:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def bind_tools(self, tools, **kwargs):
        async def invoke(messages):
            self.calls.append((list(messages), tools, kwargs.get('tool_choice')))
            return self.responses.pop(0)
        return SimpleNamespace(ainvoke=invoke)

    async def ainvoke(self, messages):
        self.calls.append((list(messages), [], None))
        return self.responses.pop(0)


def scope(sequence=1):
    return dict(user_sequence=sequence, current_user_message_id='question',
        context_rows=[dict(id='question', role='user', content='Explain photosynthesis')],
        history_references=[], memory_references=[], visible_ids=[], evidence_ids=set())


class TitleGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def reply(self, model, state, tools=()):
        chat = ChatService(MentraLLM(SimpleNamespace(get_model=lambda: model)))
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=list(tools)):
            return await chat.reply([('user', 'Explain photosynthesis')],
                history_runtime=(SimpleNamespace(), 'owner', state))

    async def test_first_answer_has_validated_title_and_only_answer_streams(self):
        model, state, deltas = ScriptedModel([output(title='  Understanding\n Photosynthesis ')]), scope(), []
        async def delta(value): deltas.append(value)
        state['on_delta'] = delta
        answer = await self.reply(model, state)
        self.assertEqual(state['conversation_title'], 'Understanding Photosynthesis')
        self.assertEqual(answer, 'Plants turn light into energy.')
        self.assertEqual(''.join(deltas), answer)
        self.assertIn(NewChatReply, model.calls[0][1])
        self.assertEqual(model.calls[0][2], 'required')
        self.assertIn('first message in a new conversation', model.calls[0][0][0].content)
        self.assertEqual(len(model.calls), 1)

    async def test_followup_does_not_request_a_title(self):
        model, state = ScriptedModel([AIMessage(content='More detail')]), scope(3)
        self.assertEqual(await self.reply(model, state), 'More detail')
        self.assertNotIn('conversation_title', state)
        self.assertNotIn(NewChatReply, model.calls[0][1])
        self.assertNotIn('first message in a new conversation', model.calls[0][0][0].content)

    async def test_domain_tools_remain_available_before_final_output(self):
        class Input(BaseModel):
            query: str
        queries = []
        async def lookup(query):
            queries.append(query)
            return dict(outcome='applied', result='safe data')
        tool = StructuredTool.from_function(name='lookup', description='Lookup', args_schema=Input, coroutine=lookup)
        model = ScriptedModel([AIMessage(content='', tool_calls=[dict(name='lookup', id='lookup1', args=dict(query='photosynthesis'))]), output()])
        state = scope()
        self.assertEqual(await self.reply(model, state, [tool]), 'Plants turn light into energy.')
        self.assertEqual(queries, ['photosynthesis'])
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(state['conversation_title'], 'Understanding Photosynthesis')

    async def test_invalid_title_does_not_lose_answer(self):
        for title in ('   ', 'x' * 81):
            state = scope()
            self.assertEqual(await self.reply(ScriptedModel([output(title)]), state), 'Plants turn light into energy.')
            self.assertNotIn('conversation_title', state)

    async def test_provider_without_tools_uses_json_schema_fallback(self):
        class NoTools(ScriptedModel):
            def bind_tools(self, tools, **kwargs): raise NotImplementedError()
        model = NoTools([AIMessage(content='{"content":"A useful answer","conversation_title":"Photosynthesis Basics"}')])
        state = scope()
        self.assertEqual(await self.reply(model, state), 'A useful answer')
        self.assertEqual(state['conversation_title'], 'Photosynthesis Basics')


class TitlePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.owner = learner_id('alice')
        cls.repo = ChatRepository(cls.db.sessions)

    @classmethod
    def tearDownClass(cls): cls.db.close()

    def begin(self):
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0,
                           content='Explain how plants use sunlight to grow')
        return request, self.repo.begin_turn(self.owner, request)

    def finish(self, job, title='Understanding Photosynthesis'):
        self.repo.finish(self.owner, job, dict(content='Plants use light.', conversation_title=title))
        return self.repo.status(self.owner, job['conversation_id'])

    def test_title_is_atomic_visible_in_sync_and_not_message_metadata(self):
        cursor = self.repo.sync(self.owner)['cursor']
        request, job = self.begin()
        page = self.finish(job)
        self.assertEqual(page['conversation']['title'], 'Understanding Photosynthesis')
        self.assertEqual(page['turn']['state'], 'SUCCEEDED')
        self.assertNotIn('conversation_title', page['items'][1])
        updated = self.repo.sync(self.owner, cursor)['conversations']
        self.assertEqual(next(row for row in updated if row['id'] == job['conversation_id'])['title'], 'Understanding Photosynthesis')
        self.repo.finish(self.owner, job, dict(content='Duplicate', conversation_title='Wrong title'))
        self.assertEqual(self.repo.status(self.owner, job['conversation_id'])['conversation']['title'], 'Understanding Photosynthesis')

    def test_manual_rename_during_generation_survives(self):
        request, job = self.begin()
        self.repo.edit(self.owner, job['conversation_id'], job['title_revision'], 'My biology notes')
        self.assertEqual(self.finish(job)['conversation']['title'], 'My biology notes')

    def test_followup_cannot_rename_chat(self):
        request, job = self.begin()
        page = self.finish(job)
        followup = request.model_copy(update=dict(client_turn_id=uuid4(), expected_revision=page['conversation']['revision'], content='Tell me more'))
        next_job = self.repo.begin_turn(self.owner, followup)
        self.assertEqual(self.finish(next_job, 'Wrong title')['conversation']['title'], 'Understanding Photosynthesis')

    def test_first_turn_retry_is_fenced_and_can_set_title(self):
        request, job = self.begin()
        self.repo.finish(self.owner, job, error='Provider unavailable')
        retry = self.repo.begin_turn(self.owner, request.model_copy(update={'retry': True}))
        self.finish(job, 'Stale title')
        self.assertEqual(self.finish(retry)['conversation']['title'], 'Understanding Photosynthesis')

    def test_manual_rename_before_retry_survives(self):
        request, job = self.begin()
        self.repo.finish(self.owner, job, error='Provider unavailable')
        page = self.repo.status(self.owner, job['conversation_id'])
        self.repo.edit(self.owner, job['conversation_id'], page['conversation']['revision'], 'My biology notes')
        retry = self.repo.begin_turn(self.owner, request.model_copy(update={'retry': True}))
        self.assertEqual(self.finish(retry)['conversation']['title'], 'My biology notes')

    def test_invalid_or_missing_title_keeps_provisional_title(self):
        for title in (None, '', 'x'*81):
            request, job = self.begin()
            page = self.finish(job, title)
            self.assertEqual(page['conversation']['title'], request.content)
            self.assertEqual(page['turn']['state'], 'SUCCEEDED')


class TitleEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_persistence_and_followup(self):
        with PostgresSandbox() as db:
            owner = learner_id('alice')
            repo = ChatRepository(db.sessions)
            service = ConversationService(repo)
            model = ScriptedModel([output(), AIMessage(content='Here is more detail.')])
            chat = ChatService(MentraLLM(SimpleNamespace(get_model=lambda: model)))
            orchestrator = OrchestrationService(chat, history=SimpleNamespace(profile=None))
            async def generate(messages, selection, state):
                return (await orchestrator.chat_reply(messages, None, owner, history_scope=state)).model_dump(mode='json')
            request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Explain photosynthesis')
            with patch('app.langchain.history_orchestration.create_history_tools', return_value=[]):
                first = await service.send(owner, request, generate, with_scope=True)
                self.assertEqual(first['turn']['state'], 'SUCCEEDED')
                self.assertEqual(first['conversation']['title'], 'Understanding Photosynthesis')
                followup = request.model_copy(update=dict(client_turn_id=uuid4(), expected_revision=first['conversation']['revision'], content='Tell me more'))
                second = await service.send(owner, followup, generate, with_scope=True)
                self.assertEqual(second['turn']['state'], 'SUCCEEDED')
                self.assertEqual(second['conversation']['title'], first['conversation']['title'])
                self.assertEqual(second['items'][-1]['content'], 'Here is more detail.')
                self.assertNotIn(NewChatReply, model.calls[-1][1])
            await service.close()
