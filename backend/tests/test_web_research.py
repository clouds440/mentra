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
    async def test_evidence_inventory_deduplicates_admitted_images_and_reports_research(self):
        from app.langchain.web_tools import web_evidence_context
        from app.web_search.schemas import WebSource, WebImage
        self.assertIsNone(web_evidence_context({}))
        image = WebImage(url='https://www.python.org/diagram.png', caption='An illustration')
        sources = [WebSource(token=f'W{i}', url=f'https://www.python.org/{i}', domain='www.python.org', favicon_url='https://www.python.org/favicon.ico',
            title='Evidence', excerpt='Verified fact', searched_at=NOW, images=[image]) for i in (1, 2)]
        scope = dict(web_sources=sources, _web_physical_calls=3, _research_physical_calls=1)
        self.assertEqual(web_evidence_context(scope, research_available=True), dict(
            search_calls=3, research_calls=1, source_count=2, checked_image_count=1, research_available=True, research_dispatches_left=0))
        self.assertEqual(web_evidence_context(dict(web_searches=[{'outcome': 'no_results'}]))['source_count'], 0)

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

    async def test_research_schema_is_retired_after_its_existing_single_dispatch(self):
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import AIMessage, HumanMessage
        from uuid import uuid4
        normal = AsyncMock(); normal.search.return_value = PAYLOAD
        paid = AsyncMock(); paid.namespace = 'research'; paid.timeout = 45
        paid.search.return_value = dict(PAYLOAD, research_report='A researched answer.')
        service = WebSearchService(normal, Usage(), enabled=True, clock=lambda: NOW)
        service.research = WebSearchService(paid, Usage(), enabled=True, clock=lambda: NOW, namespace='research')
        scope = dict(web_search_service=service, context_rows=[], current_user_message_id=str(uuid4()),
            history_references=[], memory_references=[])
        bindings = []
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                bindings.append({getattr(tool, 'name', '') for tool in kwargs['tools']})
                if len(bindings) == 1:
                    return AIMessage(content='',tool_calls=[dict(id='enable',name='enable_workflow_tools',args=dict(tool_names=['web_research']))])
                if len(bindings) == 2:
                    return AIMessage(content='',tool_calls=[dict(id='research',name='web_research',args=dict(query='Research releases'))])
                return AIMessage(content='The report supports this answer [[W1]].')
        await tool_reply(Script(), [HumanMessage(content='Research releases')], None, str(uuid4()), scope, (), {})
        self.assertNotIn('web_research', bindings[0])
        self.assertIn('web_research', bindings[1])
        self.assertNotIn('web_research', bindings[2])
        self.assertEqual(paid.search.await_count, 1)

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

    async def test_compaction_shrinks_all_excerpts_before_dropping_later_assets(self):
        from app.web_search.normalization import normalize_results
        from app.web_search.schemas import WebImage
        from app.langchain.web_tools import packet_cost
        payload = {'results': {'web': [dict(url=f'https://www.python.org/{i}', title=f'Source {i}',
            description='Historical evidence. ' * 80) for i in range(5)]}}
        sources, _ = normalize_results(payload, None, NOW)
        for index, source in enumerate(sources):
            source.images = [WebImage(url=f'https://www.python.org/{index}-illustration.png', caption=f'Historical picture {index}')]
            source.token = f'W{index+1}'
        service = WebSearchService(AsyncMock(), Usage(), enabled=True, clock=lambda: NOW)
        original = service.envelope('ok', sources=sources)
        packet = fit_result(original, {}, ToolBudget())
        self.assertTrue(packet['details_omitted'])
        self.assertEqual(len(packet['sources']), 5)
        self.assertTrue(all(source['images'] for source in packet['sources']))
        size, tokens = packet_cost(packet)
        self.assertLessEqual(size, 4800)
        self.assertLessEqual(tokens, 1200)
        self.assertEqual(len(original.sources[-1].excerpt), 1200)
