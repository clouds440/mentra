import asyncio
import json
import unittest
import importlib.util
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import uuid4
from unittest.mock import AsyncMock
from pydantic import ValidationError
from langchain_core.messages import AIMessage, ToolMessage
from app.web_search import SearchInput, WebSearchService
from app.web_search.normalization import normalize_results, source_date
from app.web_search.urls import in_scope, public_url
from app.web_search.citations import web_citations, historical_web_markers
from app.web_search.provider import ProviderError
from app.langchain.activity import ActivityPublisher, ActivityUpdate, publish_activity
from app.langchain.web_tools import create_web_tools, commit_web_result
from app.langchain.tool_execution import ToolExecutor
from app.langchain.tool_selection import ToolSelection
from app.langchain.orchestration_service import OrchestrationService
from app.langchain.chat_service import ChatService
from app.langchain.llm import MentraLLM
from app.langchain.workflow_budget import model_budget
from app.history_management.budgets import ToolBudget
from app.chat.response import ChatResponse

NOW = datetime(2026, 10, 11, 18, 59, tzinfo=timezone.utc)
PAYLOAD = {'results': {'web': [dict(url='https://www.python.org/downloads/', title='Python releases',
    description='Release notes from Python.', page_age='2026-10-08')], 'news': []}}


class Usage:
    def __init__(self): self.states = {}; self.admissions = 0; self.cache = {}
    def reserve(self, owner, operation, now):
        self.admissions += 1
        if operation in self.states: return 'duplicate'
        self.states[operation] = 'reserved'
        return 'reserved'
    def mark(self, operation, state): self.states[operation] = state
    def cached(self, owner, key, now):
        value = self.cache.get(key)
        return value if value and value['expires_at'] > now else None
    def cache_result(self, owner, key, now, expires, payload): self.cache[key] = dict(payload=payload, expires_at=expires)


class Trace:
    def __init__(self): self.events = []
    async def publish(self, update): self.events.append(update)


class ContractTests(unittest.TestCase):
    def test_hostname_scope_operators_and_private_rejection(self):
        self.assertEqual(SearchInput(query=' release site:PYTHON.ORG ').website, 'python.org')
        self.assertEqual(SearchInput(query='release', website='https://Docs.Python.org/3/').website, 'docs.python.org')
        self.assertEqual(SearchInput(query='release', website='bücher.de').website, 'xn--bcher-kva.de')
        for site in ('localhost', '127.0.0.1', '127.000.000.001', '0x7f.0.0.1', 'https://user:pass@python.org', 'https://python.org:443', '*.python.org', 'host.internal', '[::1]'):
            with self.subTest(site=site), self.assertRaises((ValueError, ValidationError)):
                SearchInput(query='release', website=site)
        for query in ('release -site:python.org', 'release site:python.org OR site:example.com', 'site:python.org', 'release site:python.org'):
            with self.subTest(query=query), self.assertRaises(ValidationError):
                SearchInput(query=query, website='docs.python.org')
        self.assertFalse(in_scope('python.org.evil.com', 'python.org'))
        self.assertFalse(in_scope('evilpython.org', 'python.org'))
        self.assertTrue(in_scope('docs.python.org', 'python.org'))
        with self.assertRaises(ValueError): public_url('javascript:alert(1)')

    def test_source_date_semantics(self):
        self.assertEqual(source_date('2026-10-10', NOW)['date_precision'], 'date')
        aware = source_date('2026-10-10T10:00:00+05:00', NOW)
        self.assertEqual(aware['published_at'].hour, 5)
        naive = source_date('2026-10-10T10:00:00', NOW)
        self.assertIsNone(naive['published_at'])
        self.assertEqual(naive['warnings'], ['timezone_unavailable'])
        self.assertEqual(source_date('yesterday', NOW)['source_date_status'], 'invalid')
        self.assertEqual(source_date('2030-01-01', NOW)['source_date_status'], 'future')
        self.assertEqual(source_date(None, NOW), {})

    def test_normalization_filters_scope_duplicates_and_script_links(self):
        payload = {'results': {'web': [*PAYLOAD['results']['web'], *PAYLOAD['results']['web'],
            dict(url='https://evilpython.org/', title='wrong'), dict(url='javascript:alert(1)'),
            dict(url='https://docs.python.org/', title='<b>Docs</b>', description='Documentation')]}}
        sources, dropped = normalize_results(payload, 'python.org', NOW)
        self.assertEqual(len(sources), 2)
        self.assertTrue(dropped)
        self.assertEqual(sources[1].title, 'Docs')
        self.assertEqual(sources[1].source_date_status, 'missing')
        self.assertEqual(sources[0].favicon_url, 'https://www.python.org/favicon.ico')

    def test_markdown_citations_ignore_code_links_escapes_and_fabricated_tokens(self):
        text = 'Claim [[W1]]. `[[W2]]` [[[W2]]](https://python.org) \\[[W2]] \\[\\[W2\\]\\] [[W99]]\n\n```\n[[W2]]\n```\n\nOther [[W3]].'
        self.assertEqual(web_citations(text, {'W1', 'W2', 'W3'}), ['W1', 'W3'])
        self.assertNotIn('[[W1]]', historical_web_markers(text))

    def test_response_registry_rejects_unresolved_citation_and_unsafe_favicon(self):
        with self.assertRaises(ValidationError): ChatResponse(content='claim', web_citations=['W1'])
        source = normalize_results(PAYLOAD, None, NOW)[0][0].model_copy(update={'token': 'W1'})
        with self.assertRaises(ValidationError):
            ChatResponse(content='claim', web_sources=[source.model_dump() | {'favicon_url': 'https://evil.com/icon'}])
        ActivityUpdate(step_id='web', status='running', user_message='Searching python.org', websites=[dict(domain='python.org', favicon_url='https://python.org/favicon.ico')])
        with self.assertRaises(ValidationError):
            ActivityUpdate(step_id='web', status='running', user_message='Searching', websites=[dict(domain='python.org', favicon_url='javascript:bad')])


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setup_service(self):
        self.now = NOW
        self.provider = AsyncMock()
        self.provider.search.return_value = PAYLOAD
        self.usage = Usage()
        self.service = WebSearchService(self.provider, self.usage, enabled=True, reference_timezone='Asia/Karachi', clock=lambda: self.now)
        self.scope = {'web_search_service': self.service}
        self.budget = ToolBudget()
        self.trace = Trace()
        self.publisher = ActivityPublisher(self.trace)
        self.scope['activity'] = self.publisher
        self.tool = create_web_tools(self.service, str(uuid4()), self.scope, self.budget)[0]

    async def test_search_dates_reuse_rollover_progress_and_no_second_provider_call(self):
        self.setup_service()
        executor = ToolExecutor(self.budget, self.scope, self.publisher)
        with model_budget(), publish_activity(self.publisher):
            result = await executor.execute(self.tool, dict(query='latest release', website='python.org'))
            commit_web_result(self.scope, result)
            self.now += timedelta(minutes=2)
            duplicate = await executor.execute(self.tool, dict(query='latest release', website='python.org'))
        self.assertEqual(result['current_date'], '2026-10-11')
        self.assertEqual(duplicate['current_date'], '2026-10-12')
        self.assertEqual(result['searched_at'], duplicate['searched_at'])
        self.assertTrue(duplicate['reused_within_turn'])
        self.provider.search.assert_awaited_once()
        self.assertEqual(self.budget.calls, 1)
        self.assertEqual(self.scope['web_sources'][0].token, 'W1')
        self.assertTrue(any(event.websites and event.status == 'running' for event in self.trace.events))
        self.assertTrue(any(event.websites and event.status == 'completed' for event in self.trace.events))

    async def test_invalid_input_and_timeout_are_dated_without_retry(self):
        self.setup_service()
        executor = ToolExecutor(self.budget, self.scope, self.publisher)
        invalid = await executor.execute(self.tool, dict(query='x', website='127.0.0.1'))
        self.assertEqual(invalid['outcome'], 'invalid_input')
        self.assertIn('current_datetime', invalid)
        self.provider.search.assert_not_awaited()
        self.provider.search.side_effect = ProviderError('timeout')
        timeout = await executor.execute(self.tool, dict(query='release'))
        self.assertEqual(timeout['outcome'], 'timeout')
        self.assertIn('searched_at', timeout)
        self.assertEqual(list(self.usage.states.values()), ['unknown'])
        duplicate = await executor.execute(self.tool, dict(query='release'))
        self.assertTrue(duplicate['reused_within_turn'])
        self.provider.search.assert_awaited_once()

    async def test_repository_failure_is_dated_sanitized_and_never_dispatches(self):
        self.setup_service()
        from app.web_search.repositories import RepositoryError
        from unittest.mock import patch
        with patch.object(self.usage, 'reserve', side_effect=RepositoryError('private connection details')):
            result = await self.service.search(SearchInput(query='current release'), owner=str(uuid4()), attempt_id='failure', deadline=monotonic()+20)
        self.assertEqual(result.outcome, 'unavailable')
        self.assertEqual(result.current_date.isoformat(), '2026-10-11')
        self.assertNotIn('private', result.model_dump_json())
        self.assertEqual(self.usage.admissions, 0)
        self.provider.search.assert_not_awaited()

    async def test_optional_cache_outage_preserves_quota_and_retrieved_evidence(self):
        from app.web_search.repositories import RepositoryError
        from unittest.mock import patch
        for method in ('cached', 'cache_result'):
            with self.subTest(method=method):
                self.setup_service()
                with patch.object(self.usage, method, side_effect=RepositoryError('private cache failure')):
                    result = await self.service.search(SearchInput(query='current release'), owner=str(uuid4()), attempt_id='cache-outage', deadline=monotonic()+20)
                self.assertEqual(result.outcome, 'ok')
                self.assertEqual(self.usage.admissions, 1)
                self.assertEqual(list(self.usage.states.values()), ['completed'])
                self.provider.search.assert_awaited_once()
                self.assertTrue(result.sources)
                partial = result.model_copy(update={'outcome': 'partial', 'reason': 'Some evidence was omitted to fit the answer budget.'})
                self.assertEqual(self.service.refresh(partial).reason, partial.reason)

    async def test_limit_deadline_and_unicode_packet_preserve_valid_json(self):
        self.setup_service()
        self.provider.search.return_value = {'results': {'web': [dict(url=f'https://python.org/{index}', title='🐍'*200, description='你好🐍'*400) for index in range(5)]}}
        with model_budget():
            result = await self.tool.ainvoke(dict(query='release'))
        content = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
        from app.langchain.token_policy import count_messages
        from langchain_core.messages import HumanMessage
        self.assertLessEqual(len(content.encode()), 4800)
        self.assertLessEqual(count_messages([HumanMessage(content=content)]), 1200)
        self.assertEqual(self.scope.get('web_sources', []), [])  # Staged only until admitted.
        self.scope['_web_physical_calls'] = 2
        limited = await self.tool.ainvoke(dict(query='other query'))
        self.assertEqual(limited['outcome'], 'budget_exhausted')
        overdue = await self.service.search(SearchInput(query='release'), owner=str(uuid4()), attempt_id='overdue', deadline=monotonic()-1)
        self.assertEqual(overdue.outcome, 'budget_exhausted')
        self.provider.search.assert_awaited_once()

    async def test_cancellation_keeps_sent_reservation_charged_and_releases_capacity(self):
        self.setup_service()
        entered = asyncio.Event()
        async def waiting(request):
            entered.set()
            await asyncio.Event().wait()
        self.provider.search.side_effect = waiting
        task = asyncio.create_task(self.service.search(SearchInput(query='release'), owner=str(uuid4()), attempt_id='cancel', deadline=monotonic()+20))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(list(self.usage.states.values()), ['unknown'])
        self.assertEqual(self.service.semaphore._value, 2)

    async def test_web_tool_visible_without_eager_search(self):
        self.setup_service()
        from app.langchain.planning import plan_request
        self.scope['execution_plan'] = plan_request('Explain gravity')
        selection = ToolSelection([self.tool], {'web_search': 'web'}, self.scope)
        self.assertEqual(selection.active, {'web_search'})
        self.provider.search.assert_not_awaited()

    async def test_cross_turn_cache_is_exact_short_lived_and_keeps_original_time(self):
        self.setup_service()
        owner = str(uuid4())
        async def search(query='release', website=None, bypass=False):
            return await self.service.search(SearchInput(query=query, website=website), owner=owner, attempt_id=str(uuid4()), deadline=monotonic()+20, bypass_cache=bypass)
        first = await search()
        self.now += timedelta(seconds=30)
        cached = await search()
        self.assertTrue(cached.cache_hit)
        self.assertFalse(cached.reused_within_turn)
        self.assertEqual(first.searched_at, cached.searched_at)
        self.assertNotEqual(first.current_datetime, cached.current_datetime)
        self.provider.search.assert_awaited_once()
        await search(website='python.org')
        self.assertEqual(self.provider.search.await_count, 2)
        await search(bypass=True)
        self.assertEqual(self.provider.search.await_count, 3)
        self.now += timedelta(seconds=121)
        expired = await search()
        self.assertFalse(expired.cache_hit)
        self.assertEqual(self.provider.search.await_count, 4)

    async def test_stateless_no_history_no_rag_integration_and_typed_citations(self):
        self.setup_service()
        class Model:
            def bind_tools(self, tools, **kwargs): return self
            async def ainvoke(self, messages, **kwargs):
                results = [message for message in messages if isinstance(message, ToolMessage)]
                if not results:
                    return AIMessage(content='', tool_calls=[dict(name='web_search', args=dict(query='Python latest release', website='python.org'), id='search-1', type='tool_call')])
                data = json.loads(results[-1].content)
                return AIMessage(content='Release information. [[' + data['sources'][0]['token'] + ']]')
        class Factory:
            def get_model(self, **kwargs): return Model()
        # Use a real shared MentraLLM facade with only the remote model replaced.
        llm = MentraLLM(Factory())
        orchestration = OrchestrationService(ChatService(llm), web_search=self.service)
        response = await orchestration.chat_reply([('user', 'Search python.org for the latest release')], None, str(uuid4()))
        self.assertEqual(response.web_citations, ['W1'])
        self.assertEqual(response.web_sources[0].domain, 'www.python.org')
        self.assertEqual(response.web_searches[0].current_date.isoformat(), '2026-10-11')

    async def test_six_duplicate_calls_fit_shared_budget_and_keep_temporal_receipts(self):
        self.setup_service()
        from app.langchain.history_orchestration import tool_reply
        scope = self.scope | dict(current_answer_text='Search for current release information', context_rows=[],
            current_user_message_id=str(uuid4()), history_references=[], memory_references=[], visible_ids=[], evidence_ids=set())
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                receipts = [item for item in messages if isinstance(item, ToolMessage)]
                if not receipts:
                    return AIMessage(content='', tool_calls=[dict(name='web_search', args=dict(query='current release', website='python.org'), id=f'call-{index}', type='tool_call') for index in range(6)])
                for receipt in receipts:
                    value = json.loads(receipt.content)
                    self.assert_temporal(value)
                return AIMessage(content='Supported release information [[W1]].')
            @staticmethod
            def assert_temporal(value):
                assert all(key in value for key in ('current_date', 'current_datetime', 'reference_timezone', 'delivered_at'))
        from langchain_core.messages import HumanMessage
        reply = await tool_reply(Script(), [HumanMessage(content='Search current release')], None, str(uuid4()), scope, (), {})
        self.assertIn('[[W1]]', reply.content)
        self.assertLessEqual(self.budget.result_tokens, 3200)
        self.assertLessEqual(self.budget.result_characters, 12800)
        self.provider.search.assert_awaited_once()
        self.assertEqual(len(scope['web_searches']), 6)


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'Official SDK tests run in the supported Python 3.12 image')
class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_handshake_and_closed_search_scope_with_host_overrides(self):
        import httpx2
        from unittest.mock import patch
        from app.web_search.you_mcp import YouMCPProvider
        requests = []
        async def remote(request):
            body = json.loads(request.content)
            requests.append(body)
            method = body['method']
            if method == 'notifications/initialized':
                return httpx2.Response(202)
            result = dict(protocolVersion='2025-03-26', capabilities={'tools':{}}, serverInfo=dict(name='fixture',version='1')) if method == 'initialize' else dict(tools=[dict(name='you-search',inputSchema=dict(type='object',properties={'query':{'type':'string'}}))]) if method == 'tools/list' else dict(content=[dict(type='text',text=json.dumps(PAYLOAD))],isError=False)
            return httpx2.Response(200, json=dict(jsonrpc='2.0',id=body['id'],result=result))
        with patch('app.web_search.you_mcp.BoundedTransport', return_value=httpx2.MockTransport(remote)):
            result = await YouMCPProvider().search(SearchInput(query='release', website='python.org'))
        self.assertEqual(result, PAYLOAD)
        self.assertEqual([item['method'] for item in requests], ['initialize', 'notifications/initialized', 'tools/list', 'tools/call'])
        call = requests[-1]['params']
        self.assertEqual(call['name'], 'you-search')
        self.assertEqual(call['_meta']['com.you.com/search']['include_domains'], ['python.org'])
        self.assertEqual(call['arguments']['extraction'], 'none')

    async def test_result_forms_errors_and_decoded_transport_cap(self):
        import httpx2
        from mcp import types
        from app.web_search.you_mcp import result_payload, LimitedStream, MAX_RESPONSE_BYTES
        from types import SimpleNamespace
        text_result = types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(PAYLOAD))])
        self.assertEqual(result_payload(text_result), PAYLOAD)
        structured = types.CallToolResult(content=[], structured_content=PAYLOAD)
        self.assertEqual(result_payload(structured), PAYLOAD)
        with self.assertRaises(ProviderError): result_payload(types.CallToolResult(content=[], is_error=True))
        with self.assertRaises(ProviderError): result_payload(types.CallToolResult(content=[types.TextContent(type='text',text='not-json')]))
        class LargeStream(httpx2.AsyncByteStream):
            async def __aiter__(self): yield b'x' * (MAX_RESPONSE_BYTES + 1)
        response = httpx2.Response(200, stream=LargeStream())
        stream = LimitedStream(response, SimpleNamespace(received=0))
        with self.assertRaises(ProviderError):
            async for _ in stream: pass
        await stream.aclose()
