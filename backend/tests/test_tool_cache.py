import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pydantic import BaseModel
from langchain_core.tools import StructuredTool
from app.core.read_cache import ReadCache, normalized_query
from app.langchain.tool_cache import tool_cache_key
from app.langchain.tool_execution import ToolExecutor
from app.langchain.activity import ActivityPublisher
from app.history_management.budgets import ToolBudget


class Query(BaseModel):
    query: str
    limit: int = 3
    context_ids: list[str] | None = None


def make_tool(name, action, domain='history'):
    return StructuredTool.from_function(name=name, description='Read', args_schema=Query,
        coroutine=action, metadata={'domain': domain})


class CacheTests(unittest.IsolatedAsyncioTestCase):
    def test_only_safe_query_equivalence_and_defaults(self):
        tool = make_tool('history_lookup', AsyncMock())
        key = lambda args: tool_cache_key(tool, tool.name, args)
        self.assertEqual(key(dict(query='  motion   laws ', context_ids=['b','a'])),
                         key(dict(query='motion laws', limit=3, context_ids=['a','b'])))
        for query in ('motion law', 'not motion laws', 'Motion laws', 'motion laws 2025'):
            self.assertNotEqual(key(dict(query=query)), key(dict(query='motion laws')))
        self.assertNotEqual(normalized_query('"a  b"'), normalized_query('"a b"'))
        self.assertNotEqual(normalized_query('x = 1'), normalized_query('x=1'))
        self.assertNotEqual(key(dict(query='motion laws', limit=4)), key(dict(query='motion laws')))
        self.assertNotEqual(key(dict(query='motion laws', context_ids=[])), key(dict(query='motion laws')))

    def test_ttl_lru_and_copy_isolation(self):
        now = [0]
        cache = ReadCache(capacity=2, ttl=10, clock=lambda: now[0])
        value = {'items': [1]}
        cache.put('a', value)
        value['items'].append(2)
        cache.get('a')['items'].append(3)
        self.assertEqual(cache.get('a'), {'items':[1]})
        cache.put('b', {})
        cache.get('a')
        cache.put('c', {})
        self.assertIsNone(cache.get('b'))
        now[0] = 10
        self.assertIsNone(cache.get('a'))

    async def test_equivalent_reads_hit_but_new_turn_and_writes_do_not(self):
        action = AsyncMock(return_value={'answer':'verified'})
        async def read(**kwargs): return await action(**kwargs)
        tool = make_tool('history_lookup', read)
        executor = ToolExecutor(ToolBudget(), {}, ActivityPublisher())
        first = await executor.execute(tool, dict(query='motion  laws'))
        self.assertEqual(first, await executor.execute(tool, dict(query=' motion laws ', limit=3)))
        first['answer'] = 'caller mutation'
        self.assertEqual((await executor.execute(tool, dict(query='motion laws')))['answer'], 'verified')
        self.assertEqual(action.await_count, 1)
        other = ToolExecutor(ToolBudget(), {}, ActivityPublisher())
        await other.execute(tool, dict(query='motion laws'))
        self.assertEqual(action.await_count, 2)
        write = make_tool('event_manage', read, 'events')
        await executor.execute(write, dict(query='motion laws'))
        await executor.execute(write, dict(query='motion laws'))
        self.assertEqual(action.await_count, 4)

    async def test_assessment_write_invalidates_dependent_learner_read(self):
        executor = ToolExecutor(ToolBudget(), {}, ActivityPublisher())
        action = AsyncMock(side_effect=[{'version':1}, {'version':2}])
        async def read(**kwargs): return await action()
        tool = make_tool('get_relevant_learner_context', read, 'learner')
        await executor.execute(tool, dict(query='motion'))
        executor.invalidate_written_domain('assessment')
        self.assertEqual(await executor.execute(tool, dict(query='motion')), {'version':2})

    async def test_rag_never_skips_service_reauthorization(self):
        executor = ToolExecutor(ToolBudget(), {}, ActivityPublisher())
        action = AsyncMock(side_effect=[{'sources':['old']}, {'sources':['new']}])
        async def read(**kwargs): return await action()
        tool = make_tool('search_study_material', read, 'rag')
        await executor.execute(tool, dict(query='motion'))
        self.assertEqual(await executor.execute(tool, dict(query='motion')), {'sources':['new']})

    async def test_concurrent_web_cache_fill_and_cancelled_waiter(self):
        from tests.test_web_search import Usage, PAYLOAD, NOW
        from app.web_search import WebSearchService, SearchInput
        from time import monotonic
        started, release = asyncio.Event(), asyncio.Event()
        async def search(request):
            started.set()
            await release.wait()
            return PAYLOAD
        provider = SimpleNamespace(search=AsyncMock(side_effect=search))
        usage = Usage()
        service = WebSearchService(provider, usage, enabled=True, clock=lambda: NOW)
        async def call(attempt):
            return await service.search(SearchInput(query='Python  release'), owner='one',
                attempt_id=attempt, deadline=monotonic()+5)
        first = asyncio.create_task(call('1'))
        await started.wait()
        cancelled = asyncio.create_task(call('2'))
        second = asyncio.create_task(call('3'))
        await asyncio.sleep(.01)
        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError): await cancelled
        release.set()
        results = await asyncio.gather(first, second)
        self.assertEqual([r.outcome for r in results], ['ok','ok'])
        self.assertTrue(results[1].cache_hit)
        provider.search.assert_awaited_once()
        self.assertEqual(usage.admissions, 1)
        self.assertFalse(service._cache_locks)
