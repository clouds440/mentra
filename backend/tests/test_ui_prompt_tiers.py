"""Default UI coverage, bounded discovery and complete tool/model round trips."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from pydantic import ValidationError
from app.chat.interactions import create_interaction_tools
from app.history_management.budgets import ToolBudget
from app.langchain.capabilities import DOMAINS
from app.langchain.history_orchestration import tool_reply
from app.langchain.prompts import PromptSource, get_system_prompt
from app.langchain.tool_selection import EnableModules, ToolSelection


def scope_for(**kwargs):
    return dict(current_user_message_id='ui-tier-test', user_sequence=1, history_references=[], memory_references=[],
                execution_plan=SimpleNamespace(tool_names=[], direct_candidate=False, steps=[]), **kwargs)


class UiSelectionTests(unittest.IsolatedAsyncioTestCase):
    def selection(self, scope=None):
        scope = scope if scope is not None else scope_for()
        tools = create_interaction_tools('synthetic', scope, ToolBudget())
        return ToolSelection(tools, DOMAINS, scope), scope

    async def test_common_inputs_are_bound_without_binding_every_visual(self):
        selection, scope = self.selection()
        self.assertEqual(selection.active, {'present_choices', 'request_input'})
        self.assertIn('present_visuals', selection.catalog['chat']['tools'])
        self.assertNotIn('_ui_topics', scope)
        for name in tuple(selection.active): selection.complete(name)
        await selection.discovery().ainvoke({'ui': ['charts']})
        self.assertEqual(selection.active, {'present_choices', 'request_input'})
        self.assertEqual(scope['_ui_topics'], ('charts',))
        self.assertNotIn('Required: type,title', get_system_prompt(PromptSource.CHAT))
        self.assertIn('Recharts', get_system_prompt(PromptSource.CHAT))

    async def test_reference_and_native_bar_binding_are_scoped_and_idempotent(self):
        selection, scope = self.selection()
        help_tool = selection.discovery()
        await help_tool.ainvoke({'ui': ['color', 'charts', 'charts']})
        await help_tool.ainvoke({'ui': ['bars', 'charts']})
        self.assertEqual(scope['_ui_topics'], ('charts', 'color', 'bars'))
        self.assertIn('present_visuals', selection.active)
        other, fresh = self.selection()
        self.assertNotIn('_ui_topics', fresh)
        self.assertNotIn('present_visuals', other.active)
        catalog = await other.discovery().ainvoke({'catalog_only': True})
        self.assertEqual(set(catalog['ui_references']), {'charts', 'disclosures', 'color', 'bars'})

    async def test_reference_budget_rejection_rolls_back_state(self):
        scope = scope_for(_admit_schemas=lambda tools: False)
        selection, _ = self.selection(scope)
        before = set(selection.active)
        result = await selection.discovery().ainvoke({'ui': ['charts', 'bars']})
        self.assertEqual(result['outcome'], 'rejected')
        self.assertEqual(selection.active, before)
        self.assertNotIn('_ui_topics', scope)
        with self.assertRaises(ValidationError): EnableModules(ui=['arbitrary-file'])

    async def test_all_tools_does_not_skip_new_reference_request(self):
        selection, scope = self.selection()
        await selection.discovery().ainvoke({'all_tools': True})
        await selection.discovery().ainvoke({'all_tools': True, 'ui': ['charts']})
        self.assertIn('charts', scope['_ui_topics'])

    async def test_reference_admission_exception_preserves_previous_topics(self):
        selection, scope = self.selection()
        await selection.discovery().ainvoke({'ui': ['color']})
        def fail(_tools): raise RuntimeError('synthetic admission failure')
        scope['_admit_schemas'] = fail
        with self.assertRaises(RuntimeError): await selection.discovery().ainvoke({'ui': ['charts']})
        self.assertEqual(scope['_ui_topics'], ('color',))


class UiCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def run_rounds(self, answers, scope=None):
        scope = scope if scope is not None else scope_for()
        rounds = []
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                rounds.append(kwargs)
                return answers[len(rounds) - 1]
        with patch('app.langchain.workflow_tools.create_workflow_tools', return_value=[]), \
             patch('app.langchain.history_orchestration.count_tokens_approximately', side_effect=count_tokens_approximately), \
             patch('app.langchain.token_policy.count_messages', side_effect=count_tokens_approximately):
            result = await tool_reply(Model(), [HumanMessage(content='Explain this')], None, 'synthetic', scope, (), {})
        return result, rounds, scope

    async def test_common_choice_needs_no_discovery_round(self):
        card = dict(kind='single_choice', question='Which topic?', options=[dict(id='a', label='Algebra'), dict(id='custom', label='My topic', input=dict(label='Topic', kind='short_text'))])
        _, rounds, scope = await self.run_rounds([
            AIMessage(content='', tool_calls=[dict(id='pick', name='present_choices', args=card)]),
            AIMessage(content='Choose a topic below.'),
        ])
        self.assertEqual(len(rounds), 2)
        self.assertEqual(len(scope['interactions']), 1)
        self.assertIn('present_choices', {tool.name for tool in rounds[0]['tools']})
        self.assertNotIn(PromptSource.CHAT_UI_CHARTS, rounds[0]['additional_sources'])

    async def test_chart_reference_is_added_once_and_retained_in_final_round(self):
        scope = scope_for(_tool_budget=ToolBudget(max_calls=1))
        _, rounds, _ = await self.run_rounds([
            AIMessage(content='', tool_calls=[dict(id='help', name='enable_workflow_tools', args=dict(ui=['charts']))]),
            AIMessage(content='A chart based on the supplied values.'),
        ], scope)
        self.assertNotIn(PromptSource.CHAT_UI_CHARTS, rounds[0]['additional_sources'])
        self.assertEqual(rounds[1]['additional_sources'].count(PromptSource.CHAT_UI_CHARTS), 1)
        self.assertIsNone(rounds[1]['tools'])
        self.assertNotIn(PromptSource.CHAT_UI_DISCLOSURES, rounds[1]['additional_sources'])

    async def test_plain_answer_does_not_discover_or_load_advanced_guides(self):
        _, rounds, scope = await self.run_rounds([AIMessage(content='Four.')])
        self.assertEqual(len(rounds), 1)
        self.assertNotIn('_ui_topics', scope)
        self.assertFalse(any(source.value.startswith('chat_ui_') for source in rounds[0]['additional_sources']))
