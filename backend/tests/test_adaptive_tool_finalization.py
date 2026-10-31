"""Continuation headroom and provider misbehavior must not discard usable work."""
import asyncio
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage
from app.core.config import Settings
from app.core.exceptions import AppError
from app.history_management.budgets import ToolBudget
from app.langchain.adaptive_tool_budget import rebalance_tools
from app.langchain.decision_schemas import FinishResponse
from app.langchain.final_response import finish_only
from app.langchain.workflow_budget import ModelBudget


class BudgetTests(unittest.TestCase):
    def test_context_headroom_expands_results_and_reads_without_expanding_writes(self):
        budget = ToolBudget()
        budget.calls = budget.max_calls
        budget.result_tokens = 3100
        budget.result_characters = 12400
        limit = rebalance_tools(budget, used_tokens=10000, input_limit=11000,
            recovery_limit=13824, envelope=ModelBudget())
        self.assertEqual(limit, 13824)
        self.assertEqual(budget.max_result_tokens, 5900)
        self.assertEqual(budget.max_calls, 9)
        budget.writes = 2
        with self.assertRaises(AppError):
            budget.call(write=True)

    def test_deadline_and_context_exhaustion_do_not_expand_results(self):
        for used, envelope in [(13824, ModelBudget()), (1000, ModelBudget(deadline=monotonic()+10))]:
            budget = ToolBudget()
            budget.result_tokens = 3100
            rebalance_tools(budget, used_tokens=used, input_limit=12288, recovery_limit=13824, envelope=envelope)
            self.assertEqual(budget.max_result_tokens, 3200)

    def test_physical_calls_stay_bounded(self):
        budget = ToolBudget(max_calls=12, calls=12)
        rebalance_tools(budget, used_tokens=1000, input_limit=12288, recovery_limit=13824, envelope=ModelBudget())
        self.assertEqual(budget.max_calls, 12)
        restricted = ToolBudget(max_calls=1, calls=1)
        rebalance_tools(restricted, used_tokens=1000, input_limit=12288, recovery_limit=13824, envelope=ModelBudget())
        self.assertEqual(restricted.max_calls, 1)

    def test_timeout_defaults_and_shared_workflow(self):
        config = Settings(_env_file=None)
        self.assertEqual(config.ai_timeout, 60)
        self.assertEqual(config.chat_turn_timeout_seconds, 180)
        self.assertGreater(ModelBudget().remaining, 179)


class FinalizationTests(unittest.IsolatedAsyncioTestCase):
    async def finish(self, llm, response, scope=None):
        self.scope = {} if scope is None else scope
        return await finish_only(llm, response, conversation=[], scope=self.scope,
            sources=(), context='Retained evidence', validate=FinishResponse.model_validate)

    async def test_valid_answer_never_adds_a_call(self):
        llm = SimpleNamespace(ainvoke_messages=AsyncMock())
        result = await self.finish(llm, AIMessage(content='Supported answer.'))
        self.assertEqual(result.content, 'Supported answer.')
        llm.ainvoke_messages.assert_not_awaited()

    async def test_pending_search_is_repaired_without_executing_it(self):
        pending = AIMessage(content='', tool_calls=[dict(name='web_search', args={'query':'more evidence'}, id='pending')])
        llm = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='Answer from existing evidence.')))
        result = await self.finish(llm, pending)
        self.assertIn('existing evidence', result.content)
        self.assertEqual(llm.ainvoke_messages.await_count, 1)

        self.assertEqual(llm.ainvoke_messages.call_args.kwargs['tool_choice'], 'FinishResponse')

    async def test_repeated_unexecuted_action_becomes_honest_partial(self):
        from app.web_search.schemas import WebSource
        from app.web_search.urls import favicon_url
        from datetime import datetime, timezone
        source = WebSource.model_validate(dict(token='W1', url='https://example.com/tutorial', title='Drawing guide', domain='example.com', excerpt='Learn drawing.', favicon_url=favicon_url('example.com'), searched_at=datetime.now(timezone.utc)))
        pending = AIMessage(content='', tool_calls=[dict(name='web_search', args={'query':'more evidence'}, id='pending')])
        llm = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=pending))
        result = await self.finish(llm, pending, {'web_sources':[source]})
        self.assertEqual(result.outcome, 'partial')
        self.assertIn('https://example.com/tutorial', result.content)
        self.assertEqual(self.scope['response_outcome']['state'], 'partial')
        self.assertEqual(llm.ainvoke_messages.await_count, 1)
        # The outer wall-clock/transport recovery path also retains read evidence.
        from app.langchain.recovery_receipts import partial_response
        partial = partial_response(self.scope, 'AI_WORKFLOW_BUDGET')
        self.assertEqual(partial['web_sources'][0]['token'], 'W1')
        self.assertEqual(partial['response_outcome']['state'], 'partial')

    async def test_exhausted_model_budget_returns_partial_cards(self):
        llm = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=AppError('AI_WORKFLOW_BUDGET','budget',422)))
        result = await self.finish(llm, None, {'assessment_cards':[{'generation_job_id':'retained'}]})
        self.assertEqual(result.outcome, 'partial')

    async def test_cancellation_is_never_swallowed(self):
        llm = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=asyncio.CancelledError()))
        with self.assertRaises(asyncio.CancelledError):
            await self.finish(llm, None)

    async def test_provider_connection_failure_preserves_available_cards(self):
        import httpx
        from openai import APIConnectionError
        llm = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=APIConnectionError(request=httpx.Request('POST','https://example.com/model'))))
        result = await self.finish(llm, None, {'assessment_cards':[{'generation_job_id':'retained'}]})
        self.assertEqual(result.outcome, 'partial')

    async def test_forged_receipts_cannot_become_completed_actions(self):
        forged = AIMessage(content='', tool_calls=[dict(name='FinishResponse', id='answer', args=dict(content='Saved.', tasks=[dict(id='save', operation='event_manage', receipt_ids=['invented'])]))])
        llm = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=forged))
        result = await self.finish(llm, forged)
        self.assertEqual(result.outcome, 'failed')
        self.assertNotIn('Saved.', result.content)
