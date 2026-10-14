import unittest
from unittest.mock import AsyncMock
import httpx
from app.web_search import SearchInput, WebSearchService
from app.web_search.you_research import YouResearchProvider
from app.web_search.provider import ProviderError
from app.langchain.web_tools import create_web_tools, commit_web_result, fit_result
from app.history_management.budgets import ToolBudget
from tests.test_web_search import Usage, NOW, PAYLOAD


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_pool_is_reused_and_closed_by_provider_lifecycle(self):
        provider = YouResearchProvider('test-key', transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={'output': {'content': 'Report', 'sources': []}})))
        client = provider._client
        for _ in range(2):
            await provider.search(SearchInput(query='Research releases'))
            self.assertIs(provider._client, client)
            self.assertFalse(client.is_closed)
        await provider.close()
        self.assertTrue(client.is_closed)
    async def test_authenticated_contract_and_scope(self):
        seen = []
        async def handle(request):
            import json
            seen.append((request, json.loads(request.content)))
            return httpx.Response(200, json={'output': {'content': 'Verified release details.', 'sources': PAYLOAD['results']['web']}})
        provider = YouResearchProvider('test-only-key', transport=httpx.MockTransport(handle))
        payload = await provider.search(SearchInput(query='Research Python releases', website='python.org'))
        request, body = seen[0]
        self.assertEqual(str(request.url), 'https://api.you.com/v1/research')
        self.assertEqual(request.headers['X-API-Key'], 'test-only-key')
        self.assertEqual(body['research_effort'], 'standard')
        self.assertEqual(body['source_control'], {'include_domains': ['python.org']})
        self.assertEqual(payload['research_report'], 'Verified release details.')

    async def test_provider_errors_and_bounded_response(self):
        for status, outcome in [(402, 'quota_exhausted'), (429, 'rate_limited'), (401, 'unavailable'), (302, 'unavailable')]:
            with self.subTest(status=status):
                provider = YouResearchProvider('test-key', transport=httpx.MockTransport(lambda request: httpx.Response(status)))
                with self.assertRaises(ProviderError) as caught:
                    await provider.search(SearchInput(query='Research releases'))
                self.assertEqual(caught.exception.outcome, outcome)
        provider = YouResearchProvider('test-key', transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'x' * (512*1024+1))))
        with self.assertRaises(ProviderError):
            await provider.search(SearchInput(query='Research releases'))

    async def test_separate_tools_cache_citations_and_single_paid_dispatch(self):
        normal = AsyncMock(); normal.search.return_value = PAYLOAD
        paid = AsyncMock(); paid.namespace = 'research'; paid.timeout = 45
        paid.search.return_value = dict(PAYLOAD, research_report='A researched answer.')
        usage = Usage()
        service = WebSearchService(normal, usage, enabled=True, clock=lambda: NOW)
        service.research = WebSearchService(paid, usage, enabled=True, clock=lambda: NOW, request_timeout=45, namespace='research')
        scope = {'conversation_id': 'chat', 'turn_id': 'turn', 'attempt': 1}
        budget = ToolBudget(max_result_tokens=4800, max_result_bytes=19200)
        tools = {tool.name: tool for tool in create_web_tools(service, 'owner', scope, budget)}
        self.assertEqual(set(tools), {'web_search', 'web_research'})
        search = await tools['web_search'].ainvoke({'query': 'Python releases'})
        commit_web_result(scope, search)
        research = await tools['web_research'].ainvoke({'query': 'Python releases'})
        commit_web_result(scope, research)
        self.assertEqual(research['research_report'], 'A researched answer.')
        self.assertEqual(research['sources'][0]['token'], search['sources'][0]['token'])
        repeated = await tools['web_research'].ainvoke({'query': 'Python releases'})
        self.assertEqual(repeated['research_report'], research['research_report'])
        self.assertEqual((await tools['web_research'].ainvoke({'query': 'Other research'}))['outcome'], 'budget_exhausted')
        self.assertEqual(normal.search.await_count, 1)
        self.assertEqual(paid.search.await_count, 1)
        self.assertEqual(usage.admissions, 2)

    async def test_routine_compaction_keeps_success_and_research_sources(self):
        from app.web_search.normalization import normalize_results
        service = WebSearchService(AsyncMock(), Usage(), enabled=True, clock=lambda: NOW)
        sources, _ = normalize_results(PAYLOAD, None, NOW)
        sources[0].excerpt = 'Useful evidence. ' * 70
        result = service.envelope('ok', sources=sources).model_copy(update={'research_report': 'Research details. '*350})
        packet = fit_result(result, {}, ToolBudget(max_result_tokens=1200, max_result_bytes=4800))
        self.assertEqual(packet['outcome'], 'ok')
        self.assertTrue(packet['details_omitted'])
        self.assertEqual(len(packet['sources']), 1)
