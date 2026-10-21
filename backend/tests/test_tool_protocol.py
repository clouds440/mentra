"""Regressions for discovery exhausting result space and provider control text."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage, HumanMessage
from app.core.exceptions import AppError
from app.langchain.history_orchestration import tool_reply
from app.langchain.llm import MentraLLM


class ToolProtocolTests(unittest.IsolatedAsyncioTestCase):
    def scope(self, tools=()):
        return dict(current_user_message_id='current', user_sequence=3, conversation_id='current-chat',
            visible_ids=[], evidence_ids=set(), history_references=[], memory_references=[],
            execution_plan=SimpleNamespace(tool_names=list(tools), direct_candidate=False, steps=[]))

    async def test_discovery_reserves_a_real_lookup_before_disabling_tools(self):
        scope, rounds = self.scope(), []
        class Model:
            async def ainvoke_messages(model, source, messages, **kwargs):
                rounds.append(dict(limit=scope['_chat_input_limit'], tools=[tool.name for tool in kwargs.get('tools') or []]))
                if len(rounds) == 1:
                    return AIMessage(content='', tool_calls=[dict(name='enable_workflow_tools',
                        args=dict(tool_names=['conversation_summary_search']), id='discovery')])
                if len(rounds) == 2:
                    return AIMessage(content='', tool_calls=[dict(name='conversation_summary_search',
                        args={'query': 'project'}, id='lookup')])
                return AIMessage(content='No matching summaries.')
        service = SimpleNamespace(events=None, search_summaries=AsyncMock(return_value={'summaries': []}))
        await tool_reply(Model(), [HumanMessage(id='current', content='Find past project discussions.')],
            service, 'owner', scope, (), {'padding': 'x'*12000})
        self.assertEqual(rounds[0]['limit'], 8192)
        self.assertEqual(rounds[1]['limit'], 12288)
        self.assertIn('conversation_summary_search', rounds[1]['tools'])
        service.search_summaries.assert_awaited_once()

    async def protocol_reply(self, responses, service):
        class Model:
            def bind_tools(model, tools, **kwargs): return model
            async def ainvoke(model, messages): return responses.pop(0)
        model = Model()
        class Factory:
            def get_model(factory): return model
        return await tool_reply(MentraLLM(Factory()), [HumanMessage(id='current', content='Find earlier project decisions.')],
            service, 'owner', self.scope(['conversation_summary_search']), (), {})

    async def test_protocol_text_is_not_executed_and_one_native_repair_can_succeed(self):
        service = SimpleNamespace(events=None, search_summaries=AsyncMock(return_value={'summaries': []}))
        responses = [AIMessage(content='<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="conversation_summary_search">'),
            AIMessage(content='', tool_calls=[dict(name='conversation_summary_search', args={'query': 'project'}, id='native')]),
            AIMessage(content='No matching summaries.')]
        result = await self.protocol_reply(responses, service)
        self.assertEqual(result.content, 'No matching summaries.')
        service.search_summaries.assert_awaited_once()
        self.assertEqual(responses, [])

    async def test_repeated_protocol_text_fails_cleanly_without_running_a_tool(self):
        service = SimpleNamespace(events=None, search_summaries=AsyncMock())
        responses = [AIMessage(content='<｜｜DSML｜｜ calls>') for _ in range(2)]
        with self.assertRaises(AppError) as caught:
            await self.protocol_reply(responses, service)
        self.assertEqual(caught.exception.code, 'AI_PROVIDER_ERROR')
        self.assertNotIn('DSML', caught.exception.message)
        service.search_summaries.assert_not_awaited()
        self.assertEqual(responses, [])
