"""Controlled before/after dispatch benchmark; no external requests or user records.

Run from the repository root: PYTHONPATH=backend python -m testing.latency_benchmark
The baseline dispatcher is loaded from the pinned pre-change commit; responses are fixed.
Injected I/O delays represent network waits, not measured production service times.
"""
import asyncio
import json
import statistics
import subprocess
import time
import types
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage
from app.langchain.history_orchestration import tool_reply
from app.langchain.activity import ActivityPublisher
from app.chat.repositories.activity import DurableActivitySink
from app.core.observability.timing import run_in_threadpool
from app.web_search import WebSearchService


class Usage:
    def reserve(self, *args): return 'reserved'
    def mark(self, *args): pass


class Provider:
    def __init__(self): self.active = self.peak = self.calls = 0
    async def search(self, request):
        self.active += 1
        self.calls += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(.25 if request.query == 'first' else .30)
            return {'results': {'web': [dict(url=f'https://example.com/{request.query}',
                title=request.query, description='Fixed benchmark evidence.')]}}
        finally:
            self.active -= 1


class ActivityStore:
    def __init__(self): self.transactions = 0; self.events = []
    def append_many(self, owner, job, updates):
        time.sleep(.075)
        self.transactions += 1
        self.events.extend(updates)
    def ensure_active(self, *args): time.sleep(.025)


class OriginalSink:
    def __init__(self, repository): self.repository = repository
    async def publish(self, update):
        await run_in_threadpool(self.repository.append_many, 'benchmark', {}, [update])
    async def ensure_active(self):
        await run_in_threadpool(self.repository.ensure_active)
    async def flush(self): pass
    async def close(self): pass


class Model:
    def __init__(self): self.calls = 0
    async def ainvoke_messages(self, *args, **kwargs):
        self.calls += 1
        await asyncio.sleep(.05)
        if self.calls == 1:
            return AIMessage(content='', tool_calls=[dict(name='web_search', args=dict(query=q), id=q, type='tool_call') for q in ('first','second')])
        return AIMessage(content='First evidence [[W1]]. Second evidence [[W2]].')


async def measure(dispatcher, buffered):
    provider, repository, model = Provider(), ActivityStore(), Model()
    sink = DurableActivitySink(repository, 'benchmark', {}) if buffered else OriginalSink(repository)
    web = WebSearchService(provider, Usage(), enabled=True, cache_seconds=0,
        clock=lambda: datetime(2026,10,12,tzinfo=timezone.utc))
    scope = dict(current_user_message_id='question', current_answer_text='Research these topics',
        history_references=[], memory_references=[], evidence_ids=set(), visible_ids=[],
        conversation_id='benchmark', turn_id='turn', attempt=1, user_sequence=2,
        web_search_service=web, activity=ActivityPublisher(sink))
    started = time.perf_counter()
    try:
        answer = await dispatcher(model, [HumanMessage(content='Research these topics', id='question')],
            None, 'benchmark', scope, (), {})
        await sink.flush()
        elapsed = time.perf_counter()-started
        assert answer.content == 'First evidence [[W1]]. Second evidence [[W2]].'
        assert [(s.token,s.title) for s in scope['web_sources']] == [('W1','first'),('W2','second')]
        assert provider.calls == model.calls == 2
        return dict(seconds=round(elapsed,4), peak_parallel_searches=provider.peak,
            activity_transactions=repository.transactions, activity_events=len(repository.events),
            model_calls=model.calls, physical_searches=provider.calls)
    finally:
        await sink.close()


async def main():
    baseline_ref = 'db237d5397ce2b6f84b42641eb858a01a1d3c924'
    source = subprocess.check_output(['git','show',f'{baseline_ref}:backend/app/langchain/history_orchestration.py'], text=True)
    baseline = types.ModuleType('app.langchain._latency_baseline')
    baseline.__package__ = 'app.langchain'
    exec(compile(source, '<baseline-dispatcher>', 'exec'), baseline.__dict__)
    # Exclude tokenizer/import/graph warmup from both measured samples.
    await measure(baseline.tool_reply, False)
    await measure(tool_reply, True)
    results = {}
    for label, dispatcher, buffered in [('baseline',baseline.tool_reply,False),('optimized',tool_reply,True)]:
        samples = [await measure(dispatcher,buffered) for _ in range(3)]
        results[label] = dict(samples=samples, median_seconds=round(statistics.median(s['seconds'] for s in samples),4))
    results['reduction_percent'] = round(100*(1-results['optimized']['median_seconds']/results['baseline']['median_seconds']),1)
    results['method'] = 'Fixed model responses; synthetic search delays 250/300ms; activity transaction delay 75ms; unchanged evidence and call counts.'
    results['baseline_ref'] = baseline_ref
    print(json.dumps(results, indent=2))


if __name__ == '__main__': asyncio.run(main())
