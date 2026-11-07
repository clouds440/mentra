from testing.prompt_context import context_data
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
from app.web_search.preview import PublisherRead
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
    async def test_blocked_publisher_then_successful_alternative_finishes_generally(self):
        from unittest.mock import patch
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import HumanMessage
        self.setup_service()
        self.provider.search.return_value={'results':{'web':[
            dict(url='https://example.org/article',title='A publisher',description='A version overview'),
            dict(url='https://docs.python.org/3/whatsnew/',title='Official release notes',description='Release notes')]}}
        state=self.scope | dict(context_rows=[],current_user_message_id=str(uuid4()),history_references=[],memory_references=[])
        class Script:
            async def ainvoke_messages(self,source,messages,**kwargs):
                receipts=[json.loads(item.content) for item in messages if isinstance(item,ToolMessage)]
                if not receipts:
                    return AIMessage(content='',tool_calls=[dict(name='web_search',args={'query':'release notes'},id='lookup')])
                if len(receipts)==1:
                    return AIMessage(content='',tool_calls=[dict(name='web_read',args={'source_token':'W1'},id='blocked')])
                if len(receipts)==2:
                    assert receipts[-1]['publisher_status']=='blocked'
                    return AIMessage(content='',tool_calls=[dict(name='web_read',args={'source_token':'W2'},id='alternative')])
                context=context_data(kwargs['system_context'])
                assert len(context['web_evidence']['page_read_results'])==2
                return AIMessage(content='',tool_calls=[dict(name='FinishResponse',id='finish',args=dict(
                    content='The requested release details are supported by the official page [[W2]].',outcome='partial',
                    tasks=[dict(id='release-details',state='completed',operation='web_read',grounding='web',receipt_ids=['receipt3'])]))])
        with patch('app.langchain.web_reader.read_publisher_result',AsyncMock(side_effect=[
                PublisherRead('blocked','PUBLISHER_HTTP_403',http_status=403),
                PublisherRead('ok',page={'url':'https://docs.python.org/3/whatsnew/','blocks':['Complete release details']})])):
            await tool_reply(Script(),[HumanMessage(content='Explain the release details from a source')],None,str(uuid4()),state,(),{})
        self.assertEqual(state['response_outcome']['state'],'completed')
        self.assertFalse(state['response_outcome']['retryable'])

    async def test_forecast_reads_returned_page_after_snippet_search(self):
        from unittest.mock import patch
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import HumanMessage
        self.setup_service()
        self.provider.search.return_value = {'results':{'web':[dict(url='https://www.bbc.com/weather/1176615',title='Islamabad forecast',description='14 day forecast for Islamabad.')]}}
        state = self.scope | dict(context_rows=[],current_user_message_id=str(uuid4()),history_references=[],memory_references=[])
        blocks = [f'November {day}: Sunny. High 27 C, Low 12 C' for day in range(7,14)]
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                receipts = [json.loads(item.content) for item in messages if isinstance(item,ToolMessage)]
                if not receipts:
                    return AIMessage(content='',tool_calls=[dict(name='web_search',args={'query':'Islamabad 7 day forecast'},id='search')])
                if len(receipts) == 1:
                    assert 'web_read' in [getattr(tool, 'name', '') for tool in kwargs['tools']]
                    return AIMessage(content='',tool_calls=[dict(name='web_read',args={'source_token':'W1'},id='read')])
                assert receipts[-1]['blocks'] == blocks, receipts[-1]
                return AIMessage(content='Seven verified daily rows from the forecast [[W1]].')
        with patch('app.langchain.web_reader.read_publisher_result', AsyncMock(return_value=PublisherRead('ok',page={'url':'https://www.bbc.com/weather/1176615','blocks':blocks}))) as read:
            await tool_reply(Script(),[HumanMessage(content='Tell me the Islamabad weather for one week')],None,str(uuid4()),state,(),{})
        read.assert_awaited_once()
        self.provider.search.assert_awaited_once()
        self.assertEqual(state['web_sources'][0].token, 'W1')

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

    async def test_image_resolution_is_opt_in_and_cached_with_search_evidence(self):
        self.setup_service()
        from types import SimpleNamespace
        from app.web_search.schemas import WebImage
        enriched=normalize_results(PAYLOAD,None,NOW)[0]
        enriched[0].images=[WebImage(url='https://www.python.org/diagram.png',caption='A fixture image')]
        self.service.image_resolver=SimpleNamespace(enrich=AsyncMock(return_value=enriched))
        owner=str(uuid4())
        await self.service.search(SearchInput(query='ordinary facts'),owner=owner,attempt_id='plain',deadline=monotonic()+20)
        self.service.image_resolver.enrich.assert_not_awaited()
        request=SearchInput(query='show a diagram',include_images=True)
        first=await self.service.search(request,owner=owner,attempt_id='images',deadline=monotonic()+20)
        reused=await self.service.search(request,owner=owner,attempt_id='later',deadline=monotonic()+20)
        self.assertEqual(first.sources[0].images[0].url,'https://www.python.org/diagram.png')
        self.assertEqual(reused.sources[0].images[0].url,first.sources[0].images[0].url)
        self.assertTrue(reused.cache_hit)
        self.service.image_resolver.enrich.assert_awaited_once()

    async def test_parallel_successful_searches_both_retain_evidence(self):
        self.setup_service()
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import HumanMessage
        self.provider.search.return_value={'results':{'web':[dict(url=f'https://python.org/{index}',title='A source',description='Relevant information '*100) for index in range(5)]}}
        state=self.scope | dict(context_rows=[],current_user_message_id=str(uuid4()),history_references=[],memory_references=[],visible_ids=[],evidence_ids=set())
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                receipts=[json.loads(item.content) for item in messages if isinstance(item,ToolMessage)]
                if not receipts:
                    return AIMessage(content='',tool_calls=[dict(name='web_search',args={'query':f'evidence {index}'},id=f'search-{index}') for index in range(2)])
                assert len(receipts)==2
                assert all(item.get('sources') for item in receipts),[(item.get('outcome'),len(item.get('sources',[]))) for item in receipts]
                return AIMessage(content='The returned sources support this answer [[W1]].')
        await tool_reply(Script(),[HumanMessage(content='Compare the evidence.')],None,str(uuid4()),state,(),{})
        self.assertEqual(self.provider.search.await_count,2)

    async def test_evidence_inventory_reaches_next_round_without_blocking_real_followups(self):
        self.setup_service()
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import HumanMessage
        inventories = []
        state=self.scope | dict(context_rows=[],current_user_message_id=str(uuid4()),history_references=[],memory_references=[])
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                context = context_data(kwargs['system_context'])
                inventories.append(context.get('web_evidence'))
                count = len(inventories)
                if count < 3:
                    args = dict(query='initial evidence' if count == 1 else 'missing date')
                    if count == 2:
                        args['evidence_gap'] = 'The required publication date is absent.'
                    return AIMessage(content='',tool_calls=[dict(name='web_search',args=args,id=f'lookup-{count}')])
                return AIMessage(content='The requested fact is supported [[W1]].')
        await tool_reply(Script(),[HumanMessage(content='Verify a date.')],None,str(uuid4()),state,(),{})
        self.assertIsNone(inventories[0])
        self.assertEqual([item['search_calls'] for item in inventories[1:]], [1, 2])
        self.assertEqual([item['last_batch_new_sources'] for item in inventories[1:]], [1, 0])
        self.assertTrue(all(item['source_count'] == 1 for item in inventories[1:]))
        self.assertTrue(all(item['checked_image_count'] == 0 for item in inventories[1:]))
        self.assertTrue(all(item['research_available'] is False for item in inventories[1:]))
        self.assertEqual(self.provider.search.await_count, 2)

    async def test_quick_lookup_retires_search_schema_with_novel_results_each_time(self):
        self.setup_service()
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import HumanMessage
        state=self.scope | dict(context_rows=[],current_user_message_id=str(uuid4()),history_references=[],memory_references=[])
        async def novel(request):
            return {'results': {'web': [dict(url=f'https://python.org/{request.query}', title='New evidence', description='Useful facts')]}}
        self.provider.search.side_effect=novel
        rounds=[]
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                names = {getattr(tool, 'name', '') for tool in kwargs['tools']}
                rounds.append(names)
                if 'web_search' in names:
                    return AIMessage(content='',tool_calls=[dict(id=f'lookup-{len(rounds)}',name='web_search',args=dict(query=f'evidence-{len(rounds)}'))])
                context=context_data(kwargs['system_context'])
                assert context['web_search_phase']['closed']
                return AIMessage(content='The requested explanation is supported [[W1]].')
        await tool_reply(Script(),[HumanMessage(content='Explain a concept.')],None,str(uuid4()),state,(),{})
        self.assertEqual(self.provider.search.await_count, 2)
        self.assertEqual(len(rounds), 3)
        self.assertNotIn('web_search', rounds[-1])
        self.assertEqual(len(state['web_sources']), 2)

    async def test_oversized_batch_does_not_redispatch_or_starve_admitted_sources(self):
        self.setup_service()
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import HumanMessage
        state=self.scope | dict(context_rows=[],current_user_message_id=str(uuid4()),history_references=[],memory_references=[])
        calls=[]
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                calls.append(1)
                if len(calls)==1:
                    return AIMessage(content='',tool_calls=[dict(id=f'lookup-{i}',name='web_search',args=dict(query=f'evidence-{i}')) for i in range(5)])
                return AIMessage(content='Use the admitted evidence [[W1]].')
        await tool_reply(Script(),[HumanMessage(content='Explain a concept.')],None,str(uuid4()),state,(),{})
        self.assertEqual(self.provider.search.await_count, 2)
        self.assertTrue(state['web_sources'])

    async def test_followup_rationale_is_not_part_of_provider_query_or_cache_identity(self):
        self.setup_service()
        await self.tool.ainvoke(dict(query='Python releases', evidence_gap='Missing release date.'))
        await self.tool.ainvoke(dict(query='Python releases', evidence_gap='Verify the date again.'))
        self.assertEqual(self.provider.search.await_count, 1)
        request = self.provider.search.call_args.args[0]
        self.assertEqual(request.query, 'Python releases')
        self.assertNotIn('evidence_gap', request.model_dump())

    async def test_unused_schemas_do_not_force_final_with_context_headroom_remaining(self):
        self.setup_service()
        from unittest.mock import patch
        from app.langchain.history_orchestration import tool_reply
        from app.langchain.token_policy import count_messages
        from app.core.config import settings
        from langchain_core.messages import HumanMessage, SystemMessage
        rounds=[]
        state=self.scope | dict(context_rows=[],current_user_message_id=str(uuid4()),history_references=[],memory_references=[],visible_ids=[],evidence_ids=set())
        state['_web_effort'] = 'extended'
        state['_tool_budget']=ToolBudget(max_result_tokens=1300,max_result_bytes=5200)
        self.provider.search.return_value={'results':{'web':[dict(url=f'https://python.org/{index}',title='A source',description='Relevant information '*100) for index in range(5)]}}
        def constrained_context(messages):
            return sum(9800 if isinstance(message,SystemMessage) else count_messages([message]) for message in messages)
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                count=len([item for item in messages if isinstance(item,ToolMessage)])
                rounds.append(count)
                if count<3:
                    assert kwargs.get('tool_choice') != 'FinishResponse', f'Coordinator closed tools: receipts={count}, budget={state["_tool_budget"].max_result_tokens}/{state["_tool_budget"].result_tokens}, transcript={count_messages(messages)}, selected={state.get("_selected_operations")}'
                    calls=range(2) if count==0 else [2]
                    return AIMessage(content='',tool_calls=[dict(name='web_search',args={'query':f'needed evidence {index}'},id=f'lookup-{index}') for index in calls])
                return AIMessage(content='Completed from the three returned searches [[W1]].')
        with patch('app.langchain.history_orchestration.count_tokens_approximately',side_effect=constrained_context), \
             patch.object(settings,'chat_input_tokens',12288), patch.object(settings,'chat_recovery_input_tokens',13824), \
             patch.object(settings,'chat_context_window_tokens',18000):
            await tool_reply(Script(),[HumanMessage(content='Explain the topic with historical pictures.')],None,str(uuid4()),state,(),{})
        self.assertEqual(rounds,[0,2,3])
        self.assertEqual(self.provider.search.await_count,3)

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
        self.scope['_web_physical_calls'] = self.budget.max_calls
        limited = await self.tool.ainvoke(dict(query='other query'))
        self.assertEqual(limited['outcome'], 'budget_exhausted')
        overdue = await self.service.search(SearchInput(query='release'), owner=str(uuid4()), attempt_id='overdue', deadline=monotonic()-1)
        self.assertEqual(overdue.outcome, 'budget_exhausted')
        self.provider.search.assert_awaited_once()

    async def test_productive_search_continues_past_two_calls_and_five_rounds(self):
        self.setup_service()
        from app.langchain.history_orchestration import tool_reply
        from langchain_core.messages import HumanMessage
        state = self.scope | dict(context_rows=[], current_user_message_id=str(uuid4()),
            history_references=[], memory_references=[], visible_ids=[], evidence_ids=set(), _web_effort='extended')
        rounds = []
        class Script:
            async def ainvoke_messages(self, source, messages, **kwargs):
                count = len([item for item in messages if isinstance(item, ToolMessage)])
                rounds.append(count)
                if count < 7:
                    return AIMessage(content='', tool_calls=[dict(name='web_search', args={'query':f'evidence detail {count}'}, id=f'lookup-{count}')])
                return AIMessage(content='Supported answer [[W1]].')
        with model_budget():
            reply = await tool_reply(Script(), [HumanMessage(content='Find sufficient evidence for the comparison.')], None, str(uuid4()), state, (), {})
        self.assertEqual(rounds, list(range(8)))
        self.assertEqual(self.provider.search.await_count, 7)
        self.assertIn('Supported answer', reply.content)
        self.assertEqual(state['_tool_budget'].max_calls, 9)

    async def test_reused_sources_never_collide_with_new_tokens_and_registry_exceeds_ten(self):
        self.setup_service()
        self.scope['_web_effort'] = 'extended'
        self.budget.max_result_tokens = 20000
        self.budget.max_result_bytes = 80000
        batches = [[0,1], [2,0,3], [4], [5,6,7,8,9], [10,11]]
        for index, batch in enumerate(batches):
            self.provider.search.return_value = {'results':{'web':[
                dict(url=f'https://python.org/source-{number}', title=f'Source {number}', description='Evidence') for number in batch]}}
            result = await self.tool.ainvoke(dict(query=f'query {index}'))
            commit_web_result(self.scope, result)
        sources = self.scope['web_sources']
        self.assertEqual(len(sources), 12)
        self.assertEqual(len({source.token for source in sources}), 12)
        self.assertEqual({source.url:source.token for source in sources}['https://python.org/source-0'], 'W1')
        ChatResponse(content='Grounded comparison.', web_sources=sources)

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
        from testing.legacy_keyword_policy import plan_request
        self.scope['execution_plan'] = plan_request('Explain gravity')
        selection = ToolSelection([self.tool], {'web_search': 'web'}, self.scope)
        self.assertEqual(selection.active, {'web_search'})
        self.assertIn('web_search', selection.catalog['web']['tools'])
        await selection.discovery().ainvoke(dict(tool_names=['web_search']))
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


class WebReceiptBoundaryTests(unittest.TestCase):
    def envelope(self, outcome='ok'):
        return WebSearchService(AsyncMock(), Usage(), enabled=True, clock=lambda: NOW).envelope(outcome).model_dump(mode='json')

    def test_dispatch_rejection_cannot_poison_public_search_metadata_or_citations(self):
        scope = {'web_sources': [{'token': 'W1'}]}
        commit_web_result(scope, self.envelope())
        scope['_web_pending'] = [{'token': 'unadmitted'}]
        for code in ('TOOL_NOT_ENABLED', 'TOOL_UNKNOWN', 'TOOL_INVALID_ARGUMENTS'):
            commit_web_result(scope, dict(outcome='rejected', code=code, category='invalid_arguments', effect_certainty='not_started'))
        self.assertEqual(len(scope['web_searches']), 1)
        self.assertEqual(scope['web_sources'], [{'token': 'W1'}])
        self.assertNotIn('_web_pending', scope)
        ChatResponse(role='assistant', content='A grounded answer.', web_searches=scope['web_searches'])

    def test_real_dated_failures_are_retained(self):
        scope = {}
        commit_web_result(scope, self.envelope('unavailable'))
        self.assertEqual(scope['web_searches'][0]['outcome'], 'unavailable')
        ChatResponse(role='assistant', content='Search unavailable.', web_searches=scope['web_searches'])

    def test_poisoned_checkpoint_restores_without_discarding_valid_searches(self):
        from types import SimpleNamespace
        from app.langchain.response_runtime import ResponseRuntime
        conversation, scope = [], {}
        selection = SimpleNamespace(active=set(), pending=set(), explicit=set(), by_name={}, common=set())
        runtime = ResponseRuntime(conversation, scope, ToolBudget(), selection, SimpleNamespace())
        state = runtime.capture()
        rejection = dict(outcome='rejected', code='TOOL_NOT_ENABLED', category='invalid_arguments', effect_certainty='not_started')
        state['scope']['web_searches'] = [self.envelope(), rejection]
        runtime.restore(state)
        self.assertEqual(len(scope['web_searches']), 1)
        self.assertEqual(scope['web_searches'][0].outcome, 'ok')
