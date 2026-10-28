import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.langchain.concurrent_reads import gather_reads, project_read
from app.langchain.history_orchestration import tool_reply
from app.langchain.activity import ActivityUpdate
from app.chat.repositories.activity import DurableActivitySink
from app.core.exceptions import AppError


class Query(BaseModel):
    query: str


def scope():
    return dict(current_user_message_id='question', current_answer_text='Research these topics',
        history_references=[], memory_references=[], evidence_ids=set(), visible_ids=[],
        conversation_id='conversation', turn_id='turn', attempt=1, user_sequence=2)


class ConcurrentDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_recall_overlaps_profile_and_memory_reads(self):
        import threading
        from app.history_management.service import HistoryManagement
        from app.history_management.schemas import MemoryToolInput
        gate = threading.Barrier(2, timeout=2)
        def memories(*args):
            gate.wait()
            return dict(items=[])
        def profile(*args):
            gate.wait()
            return SimpleNamespace(details=None)
        service = HistoryManagement(SimpleNamespace(list=memories), None, None,
            profile=SimpleNamespace(get=profile))
        result = await service.memory('owner', scope(), MemoryToolInput(action='recall', query='goals'), None)
        self.assertEqual(result['memories'], [])
        self.assertEqual(result['current_profile'], {})

    async def test_fanout_never_exceeds_four(self):
        active = peak = 0
        async def read():
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(.01)
                return 'value'
            finally:
                active -= 1
        self.assertEqual(await gather_reads([read] * 10), ['value'] * 10)
        self.assertEqual(peak, 4)
        self.assertEqual(active, 0)

    def test_overlapping_history_results_keep_one_reference_and_evidence(self):
        from app.history_management.service import HistoryManagement
        state = scope()
        windows = [dict(conversation_id='conversation', title='History', messages=[
            dict(id='source-user', role='user', content='My learning goal', sequence=1)])]
        first = HistoryManagement._lookup_result(state, windows)
        second = HistoryManagement._lookup_result(state, windows)
        self.assertEqual(first['windows'][0]['token'], 'H1')
        self.assertEqual(second['windows'], [])
        self.assertEqual(len(state['history_references']), 1)
        self.assertEqual(state['evidence_ids'], {'source-user'})

    async def run_tools(self, tools, calls, state):
        from app.langchain.tool_selection import ToolSelection
        class DiscoveredSelection(ToolSelection):
            def __init__(self, available, domains, scope):
                super().__init__(available,domains,scope)
                self.active.update(tool.name for tool in tools)
        model = SimpleNamespace(ainvoke_messages=AsyncMock(side_effect=[
            AIMessage(content='', tool_calls=calls), AIMessage(content='Verified answer')]))
        with patch('app.langchain.workflow_tools.create_workflow_tools', return_value=tools), patch('app.langchain.tool_selection.ToolSelection',DiscoveredSelection):
            result = await tool_reply(model, [HumanMessage(content='Research these topics', id='question')],
                None, 'owner', state, (), {})
        return result, model

    async def test_fetches_overlap_but_citations_merge_in_call_order(self):
        state = scope()
        started = set()
        both = asyncio.Event()
        async def read(query):
            started.add(query)
            if len(started) == 2: both.set()
            await asyncio.wait_for(both.wait(), .5)
            if query == 'first': await asyncio.sleep(.02)
            def project(value):
                token = 'H' + str(len(state['history_references'])+1)
                state['history_references'].append(dict(token=token, query=value))
                return dict(token=token, value=value)
            return project_read(project, query)
        tool = StructuredTool.from_function(name='history_lookup', description='Read', args_schema=Query,
            coroutine=read, metadata={'parallel_read': True})
        calls = [dict(name=tool.name, args=dict(query=q), id=str(i), type='tool_call') for i, q in enumerate(('first', 'second', ' first '))]
        result, model = await self.run_tools([tool], calls, state)
        self.assertEqual(result.content, 'Verified answer')
        self.assertEqual([r['query'] for r in state['history_references']], ['first','second'])
        messages = [m for m in model.ainvoke_messages.call_args.args[1] if isinstance(m, ToolMessage)]
        self.assertEqual([m.tool_call_id for m in messages], ['0','1','2'])
        self.assertEqual(json.loads(messages[0].content)['token'], 'H1')
        self.assertEqual(json.loads(messages[1].content)['token'], 'H2')
        self.assertEqual(state['_tool_budget'].calls, 2)

    async def test_write_is_a_barrier_and_following_read_sees_its_effect(self):
        state, order = scope(), []
        async def read(query):
            await asyncio.sleep(.01)
            order.append(query)
            return dict(version=len(order))
        async def write(query):
            self.assertEqual(order, ['before'])
            order.append('write')
            return dict(outcome='saved')
        tools = [StructuredTool.from_function(name=name, description='Tool', args_schema=Query,
            coroutine=fn, metadata={'parallel_read': True}) for name,fn in [('event_lookup',read),('event_manage',write)]]
        calls = [dict(name=name, args=dict(query=q), id=str(i), type='tool_call') for i,(name,q) in enumerate([
            ('event_lookup','before'),('event_manage','write'),('event_lookup','after')])]
        await self.run_tools(tools, calls, state)
        self.assertEqual(order, ['before','write','after'])

    async def test_failed_read_cannot_remove_successful_sibling_references(self):
        state = scope()
        async def read(query):
            if query == 'bad': raise AppError('SOURCE_NOT_FOUND', 'Missing', 404)
            def project(value):
                state['history_references'].append(dict(token='H1', query=value))
                return dict(token='H1')
            return project_read(project, query)
        tool = StructuredTool.from_function(name='history_lookup', description='Read', args_schema=Query,
            coroutine=read, metadata={'parallel_read': True})
        calls = [dict(name=tool.name, args=dict(query=q), id=q, type='tool_call') for q in ('good','bad')]
        await self.run_tools([tool], calls, state)
        self.assertEqual(state['history_references'], [dict(token='H1',query='good')])

    async def test_cancelled_fanout_drains_every_child(self):
        active = set()
        async def work(i):
            active.add(i)
            try: await asyncio.Event().wait()
            finally: active.remove(i)
        task = asyncio.create_task(gather_reads([lambda i=i: work(i) for i in range(6)], limit=2))
        await asyncio.sleep(.01)
        self.assertEqual(len(active), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertFalse(active)

    async def test_real_web_adapter_merges_reversed_results_without_losing_sources(self):
        from app.web_search import WebSearchService
        from datetime import datetime, timezone
        class Usage:
            def reserve(self, *args): return 'reserved'
            def mark(self, *args): pass
        active = set()
        both = asyncio.Event()
        class Provider:
            async def search(self, request):
                active.add(request.query)
                if len(active) == 2: both.set()
                await asyncio.wait_for(both.wait(), .5)
                if request.query == 'first': await asyncio.sleep(.03)
                return {'results': {'web': [dict(url=f'https://example.com/{request.query}', title=request.query, description='Verified public source')]}}
        web = WebSearchService(Provider(), Usage(), enabled=True, cache_seconds=0,
            clock=lambda: datetime(2026,10,12,tzinfo=timezone.utc))
        state = dict(scope(), web_search_service=web)
        calls = [dict(name='web_search', args=dict(query=q), id=q, type='tool_call') for q in ('first','second')]
        _, model = await self.run_tools([], calls, state)
        self.assertEqual([(s.token, s.title) for s in state['web_sources']], [('W1','first'),('W2','second')])
        messages = [m for m in model.ainvoke_messages.call_args.args[1] if isinstance(m, ToolMessage)]
        self.assertEqual([json.loads(m.content)['sources'][0]['token'] for m in messages], ['W1','W2'])
        self.assertFalse(json.loads(messages[0].content)['reused_within_turn'])

    async def test_context_preparation_overlaps_without_changing_model_context(self):
        import threading
        from app.langchain.orchestration_service import OrchestrationService
        gate = threading.Barrier(2, timeout=2)
        def profile(*args):
            gate.wait()
            return SimpleNamespace(model_dump=lambda **kw: {'name':'Student'})
        def memories(*args):
            gate.wait()
            return dict(state='empty',content='',revision=0), None
        learner = Mock()
        search = Mock()
        chat = SimpleNamespace(reply=AsyncMock(return_value='Grounded explanation'))
        state = dict(scope(), context_rows=[])
        service = OrchestrationService(chat, rag=SimpleNamespace(search=search),
            learner=SimpleNamespace(get_relevant_context=learner),
            history=SimpleNamespace(profile=SimpleNamespace(prompt_context=profile),summary_context=memories))
        from testing.identities import learner_id
        result = await service.chat_reply([('user','Help me study my notes')],None,learner_id('alice'),history_scope=state)
        self.assertEqual(result.content, 'Grounded explanation')
        self.assertEqual(chat.reply.call_args.kwargs['profile_context'], {'name':'Student'})
        learner.assert_not_called()
        search.assert_not_called()
        self.assertNotIn('_tool_budget', state)
        self.assertEqual(state['_tool_execution_state']['failed'], {})


class ActivityBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_reporting_timeout_does_not_cancel_later_completion(self):
        sink = DurableActivitySink(SimpleNamespace(), 'owner', {})
        sink.writer = asyncio.create_task(asyncio.sleep(10))
        wait_for = asyncio.wait_for
        async def short_wait(awaitable, timeout):
            return await wait_for(awaitable, .01)
        try:
            with patch('app.chat.repositories.activity.asyncio.wait_for', side_effect=short_wait):
                await sink.flush()
            self.assertIsInstance(sink.error, TimeoutError)
            self.assertFalse(sink.writer.cancelled())
            await sink.flush()
        finally:
            await sink.close()
        self.assertTrue(sink.writer.cancelled())

    async def test_progress_does_not_block_and_flush_preserves_order(self):
        import threading
        release, entered = threading.Event(), threading.Event()
        batches = []
        def append(owner, job, updates):
            entered.set()
            if not release.wait(2): raise RuntimeError('Writer never released')
            batches.append(updates)
        sink = DurableActivitySink(SimpleNamespace(append_many=append), 'owner', {})
        try:
            for i in range(20):
                await sink.publish(ActivityUpdate(step_id=str(i), status='running', user_message='Working'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.assertFalse(batches)
            release.set()
            await sink.flush()
            self.assertEqual([u.step_id for b in batches for u in b], [str(i) for i in range(20)])
            self.assertEqual(len(batches), 1)
        finally:
            release.set()
            await sink.close()

    async def test_stale_attempt_fails_flush_and_write_guard(self):
        def stale(*args): raise AppError('CHAT_ATTEMPT_EXPIRED', 'Stopped', 409)
        sink = DurableActivitySink(SimpleNamespace(append_many=stale, ensure_active=stale), 'owner', {})
        await sink.publish(ActivityUpdate(step_id='test',status='running',user_message='Working'))
        with self.assertRaises(AppError): await sink.flush()
        with self.assertRaises(AppError): await sink.ensure_active()
        await sink.close()


    async def test_reporting_failure_does_not_replace_domain_success(self):
        def failed(*args): raise RuntimeError('Unavailable')
        sink = DurableActivitySink(SimpleNamespace(append_many=failed, ensure_active=lambda *a: None), 'owner', {})
        await sink.publish(ActivityUpdate(step_id='test',status='running',user_message='Working'))
        await sink.flush()
        await sink.ensure_active()
        await sink.close()


class PersistenceLatencyTests(unittest.TestCase):
    def setUp(self):
        from testing.postgres import PostgresSandbox
        from testing.identities import learner_id
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.owner = learner_id('alice')

    def test_batch_activity_retains_capacity_fencing_and_contiguous_sequences(self):
        from uuid import uuid4
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.repositories.activity import ActivityRepository
        from app.chat.schemas import SendTurn
        chat, activity = ChatRepository(self.db.sessions), ActivityRepository(self.db.sessions)
        job = chat.begin_turn(self.owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(),
            expected_revision=0, content='Question'))
        updates = [ActivityUpdate(step_id='response-stream',status='running',user_message='Writing',token_delta='text') for _ in range(194)]
        updates.append(ActivityUpdate(step_id='finished',status='completed',user_message='Ready'))
        events = activity.append_many(self.owner, job, updates)
        self.assertEqual([e.sequence for e in events], list(range(1,194)))
        self.assertEqual(events[-1].step_id, 'finished')
        chat.stop_turn(self.owner, job['conversation_id'],job['turn_id'],job['attempt'])
        with self.assertRaises(AppError): activity.append_many(self.owner,job,updates[:1])
        page = activity.page(self.owner,job['conversation_id'],job['turn_id'],job['attempt'])
        self.assertEqual(len(page['events']),193)

    def test_batched_concept_search_matches_original_lookup_sets(self):
        from app.learner.engine import LearnerEngine
        engine = LearnerEngine(self.db.repository)
        engine.register_concept('Motion and forces', aliases=['Physics'])
        engine.register_concept('Motion and energy', aliases=['Physics energy'])
        engine.register_concept('Other topic')
        terms = ['motion','energy','physics']
        original = {c.id for term in terms for c in self.db.repository.search_concepts(term,1)}
        batch = {c.id for c in self.db.repository.search_concept_terms(terms,1)}
        self.assertEqual(batch,original)
        forms = ('motion and forces','physics')
        original = {c.id for term in forms for c in self.db.repository.find_by_normalized_alias(term)}
        original.update(c.id for term in forms if (c := self.db.repository.get_concept_by_normalized_name(term)))
        self.assertEqual({c.id for c in self.db.repository.find_exact_concepts(forms)},original)
