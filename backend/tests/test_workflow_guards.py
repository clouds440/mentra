import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from app.core.exceptions import AppError
from app.history_management.budgets import ToolBudget
from app.langchain.history_orchestration import tool_reply
from app.langchain.token_policy import check_input
from app.langchain.prompts import PromptSource
from app.vision.assessment_extractor import AssessmentAnswerExtractor, PageAnswers


class Empty(BaseModel):
    pass


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def scope(self):
        return dict(current_user_message_id='user-1', history_references=[], memory_references=[],
                    learner_service=object(), history_token_budget=4096)

    async def test_parallel_reads_then_second_round_and_matching_results(self):
        started = set()
        both = asyncio.Event()
        async def read(name):
            started.add(name)
            if len(started) == 2: both.set()
            await asyncio.wait_for(both.wait(), 1)
            return dict(name=name)
        async def a(): return await read('a')
        async def b(): return await read('b')
        tools = [StructuredTool.from_function(name='read_a', description='read', args_schema=Empty, coroutine=a),
                 StructuredTool.from_function(name='read_b', description='read', args_schema=Empty, coroutine=b)]
        class Model:
            rounds = 0
            async def ainvoke_messages(self, source, messages, **kwargs):
                self.rounds += 1
                results = [message.tool_call_id for message in messages if isinstance(message, ToolMessage)]
                if self.rounds == 1:
                    return AIMessage(content='', tool_calls=[dict(name='read_a',args={},id='a'),dict(name='read_b',args={},id='b')])
                if self.rounds == 2:
                    assert results == ['a','b']
                    return AIMessage(content='', tool_calls=[dict(name='read_a',args={},id='a2')])
                assert results == ['a','b','a2']
                return AIMessage(content='Complete')
        model = Model()
        with patch('app.langchain.learner_tools.create_learner_tools', return_value=tools):
            result = await tool_reply(model, [HumanMessage(content='Study', id='user-1')], SimpleNamespace(events=None),
                'owner', self.scope(), (), {})
        self.assertEqual(result.content, 'Complete')
        self.assertEqual(model.rounds, 3)

    async def test_large_committed_write_returns_truthful_receipt(self):
        async def write(): return dict(outcome='saved', memory=dict(id='memory-id', content='x'*16000))
        tool = StructuredTool.from_function(name='user_memory', description='write', args_schema=Empty, coroutine=write)
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                results = [message for message in messages if isinstance(message, ToolMessage)]
                if not results:
                    return AIMessage(content='', tool_calls=[dict(name='user_memory',args={},id='write')])
                receipt = json.loads(results[-1].content)
                assert receipt['outcome'] == 'saved'
                assert receipt['memory']['id'] == 'memory-id'
                return AIMessage(content='Saved')
        scope = self.scope(); scope['learner_service'] = None
        with patch('app.langchain.history_orchestration.create_history_tools', return_value=[tool]):
            result = await tool_reply(Model(), [HumanMessage(content='Remember', id='user-1')], SimpleNamespace(events=None),
                'owner', scope, (), {})
        self.assertEqual(result.content, 'Saved')

    def test_normal_packet_fits_but_large_unicode_and_model_context_do_not(self):
        ToolBudget().consume(json.dumps(dict(concepts=[dict(id=str(index), details='x'*80) for index in range(8)])))
        with self.assertRaises(AppError): ToolBudget().consume('😀'*4000)
        with self.assertRaises(AppError):
            check_input([HumanMessage(content='Answer. '*10000)], PromptSource.ASSESSMENT_GRADING)

    def test_nested_workflows_share_one_budget(self):
        from app.langchain.workflow_budget import model_budget
        with model_budget() as parent:
            parent.reserve(100,100)
            with model_budget() as child:
                self.assertIs(child,parent)
                child.reserve(100,100)
            self.assertEqual(parent.rounds,2)
            parent.rounds=12
            with self.assertRaises(AppError): parent.reserve(1,1)

    def test_write_receipt_reserves_utf8_bytes_as_well_as_tokens(self):
        budget = ToolBudget(result_characters=12000,result_tokens=2500)
        with self.assertRaises(AppError): budget.call(True)

    def test_missing_tokenizer_cache_never_downloads_on_request(self):
        from app.langchain.token_policy import _encoding
        _encoding.cache_clear()
        try:
            with patch.dict('os.environ',{'TIKTOKEN_CACHE_DIR':''}), patch('tiktoken.get_encoding') as load:
                self.assertIsNone(_encoding())
                load.assert_not_called()
        finally:
            _encoding.cache_clear()

    def test_response_shows_latest_card_for_each_assessment_version(self):
        from app.chat.response import ChatResponse
        first = dict(id='draft-one',assessment={'id':'assessment-one'})
        answered = dict(first,attempt_id='attempt-one')
        revised = dict(id='draft-two',assessment={'id':'assessment-two'})
        response = ChatResponse(content='Ready',assessment_cards=[first,answered,revised])
        self.assertEqual(response.assessment_cards,[answered,revised])


class VisionMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_number_map_and_multi_page_continuation(self):
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                mapping = json.loads(messages[0].content[0]['text'])
                assert mapping['questions'][0]['number'] == 1
                return PageAnswers(answers=[dict(question_id='q1', text=f"Page {mapping['page']}", confidence=.8)])
        questions = [SimpleNamespace(id='q1', prompt='Question one'), SimpleNamespace(id='q2', prompt='Question two')]
        with patch('app.vision.assessment_extractor.prepare_pages', return_value=['image1','image2']):
            result = await AssessmentAnswerExtractor(Model()).extract(b'bytes', questions)
        self.assertEqual(result['answers']['q1'], 'Page 1\nPage 2')
        self.assertEqual(result['answers']['q2'], '')
        self.assertTrue(result['requires_confirmation'])
        self.assertTrue(result['warnings'])

    async def test_foreign_question_id_is_rejected(self):
        class Model:
            async def ainvoke_messages(self, *args, **kwargs):
                return PageAnswers(answers=[dict(question_id='foreign', text='invented', confidence=1)])
        with patch('app.vision.assessment_extractor.prepare_pages', return_value=['image']):
            with self.assertRaises(AppError):
                await AssessmentAnswerExtractor(Model()).extract(b'bytes', [SimpleNamespace(id='q1', prompt='Question')])
