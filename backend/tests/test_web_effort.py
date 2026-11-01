import unittest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from app.langchain.web_effort import search_phase
from app.langchain.tool_selection import ToolSelection


class PhaseTests(unittest.TestCase):
    def test_quick_phase_closes_despite_novel_evidence(self):
        scope = dict(_web_physical_calls=2, web_sources=[object()],
            _web_cache={'a': {'outcome': 'ok', 'sources': [{}]}, 'b': {'outcome': 'ok', 'sources': [{}]}})
        self.assertTrue(search_phase(scope)['closed'])
        self.assertEqual(search_phase(scope)['calls_remaining'], 0)

    def test_oversized_initial_batch_cannot_use_recovery_while_inflight(self):
        self.assertTrue(search_phase(dict(_web_physical_calls=2, _web_cache={}))['closed'])

    def test_empty_initial_batch_allows_bounded_recovery(self):
        scope = dict(_web_physical_calls=2, _web_cache={'a': {'outcome': 'no_results'}, 'b': {'outcome': 'timeout'}})
        self.assertFalse(search_phase(scope)['closed'])
        self.assertEqual(search_phase(scope)['calls_remaining'], 2)
        scope['_web_physical_calls'] = 4
        self.assertTrue(search_phase(scope)['closed'])

    def test_provider_quota_closes_extended_search(self):
        scope = dict(_web_effort='extended', _web_cache={'a': {'outcome': 'quota_exhausted'}})
        self.assertTrue(search_phase(scope)['closed'])
        self.assertEqual(search_phase(scope)['reason'], 'provider_allowance')


class EffortTests(unittest.IsolatedAsyncioTestCase):
    def selection(self, research=False, **scope):
        class Input(BaseModel):
            query: str
        async def read(query):
            return dict(outcome='ok')
        names = ['web_search', *(['web_research'] if research else [])]
        tools = [StructuredTool.from_function(name=name, description='Public evidence', args_schema=Input, coroutine=read) for name in names]
        return ToolSelection(tools, {name: 'web' for name in names}, scope), scope

    async def test_deeper_effort_chooses_available_research(self):
        selection, scope = self.selection(research=True, _web_physical_calls=2)
        result = await selection.discovery().ainvoke(dict(web_effort=dict(reason='The user requested a thorough comparative investigation.')))
        self.assertIn('web_research', result['tools'])
        self.assertEqual(scope['_web_effort'], 'research')
        self.assertTrue(search_phase(scope)['closed'])

    async def test_without_research_deliberate_effort_preserves_continuation(self):
        selection, scope = self.selection(_web_physical_calls=2)
        await selection.discovery().ainvoke(dict(web_effort=dict(reason='Several requested datasets require independent public lookups.')))
        self.assertEqual(scope['_web_effort'], 'extended')
        self.assertFalse(search_phase(scope)['closed'])

    async def test_reenabling_lookup_does_not_reset_phase(self):
        selection, scope = self.selection(research=True, _web_physical_calls=2)
        result = await selection.discovery().ainvoke(dict(tool_names=['web_search']))
        self.assertNotIn('web_search', result['tools'])
        self.assertIn('web_search_status', result)
        self.assertTrue(search_phase(scope)['closed'])

    async def test_schema_rejection_does_not_promote_effort(self):
        selection, scope = self.selection(_web_physical_calls=2, _admit_schemas=lambda tools: False)
        await selection.discovery().ainvoke(dict(web_effort=dict(reason='Several requested datasets require independent public lookups.')))
        self.assertNotIn('_web_effort', scope)
