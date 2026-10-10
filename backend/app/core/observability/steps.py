import asyncio
import logging
import time
from contextlib import contextmanager
from .context import Collector, current, span, identifier, validated_envelope, envelope
from .events import emit
from .sanitization import safe_metadata, error_metadata


def setting(name, default):
    # Lazy import prevents configuration/registration cycles at module import.
    from app.core.config import settings
    return getattr(settings, name, default)


def complete(event, collector, **fields):
    summary = collector.close()
    if summary is None:
        return
    if not setting('log_workflow_summaries', True):
        emit(event, **fields, outcome=summary['outcome'], duration_ms=summary['duration_ms'])
        return
    import json
    maximum = setting('log_event_max_bytes', 32768) - 3000
    if len(json.dumps(summary).encode()) < maximum:
        emit(event, **fields, summary=summary, outcome=summary['outcome'], duration_ms=summary['duration_ms'])
    else:
        operations = summary.pop('operations')
        links = summary.pop('linked_workflows')
        parts, pending = [], []
        for item in [dict(operation=x) for x in operations] + [dict(link=x) for x in links]:
            if len(json.dumps(pending + [item]).encode()) > maximum and pending:
                parts.append(pending)
                pending = []
            # Child links can themselves exceed the budget; split their operations.
            if len(json.dumps(item).encode()) > maximum and 'link' in item:
                child = dict(item['link'])
                child_ops = child.pop('operations', [])
                pending.append(dict(link=child))
                for operation in child_ops:
                    parts.append([dict(child_workflow_id=child['workflow_id'], operation=operation)])
            else:
                pending.append(item)
        if pending:
            parts.append(pending)
        emit(event, **fields, summary=summary, summary_parts=len(parts), outcome=summary['outcome'], duration_ms=summary['duration_ms'])
        for index, part in enumerate(parts, 1):
            emit('summary.part', part=index, total_parts=len(parts), entries=part)


@contextmanager
def workflow(name, *, log_context=None, quiet=False, collector=None):
    parent = current.get()
    context = validated_envelope(log_context) if log_context else validated_envelope(envelope())
    collector = collector or Collector(name, quiet=quiet or bool(parent and parent.quiet),
                                       maximum=setting('log_summary_max_steps', 500), **context)
    if parent:
        parent.link(collector)
    token, span_token = current.set(collector), span.set(None)
    emit('workflow.started')
    try:
        yield collector
    except BaseException as error:
        collector.outcome = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'timeout' if isinstance(error, TimeoutError) else 'failed'
        emit('workflow.error', level=logging.ERROR, error=error_metadata(error))
        raise
    finally:
        complete('workflow.completed', collector, level=logging.ERROR if collector.outcome == 'failed' else logging.WARNING if collector.outcome in ('rejected', 'timeout', 'cancelled', 'degraded') else logging.INFO)
        if parent:
            parent.link(collector, collector.snapshot())
        span.reset(span_token)
        current.reset(token)


class Operation:
    def __init__(self, module, operation, *, purpose=None, input=None, quiet=False):
        self.module, self.operation = module, operation
        self.purpose, self.input = purpose or operation, input
        self.root = None
        self.quiet = quiet

    def __enter__(self):
        if current.get() is None:
            self.root = workflow(self.operation, quiet=self.quiet)
            self.root.__enter__()
        self.collector = current.get()
        parent = span.get()
        self.entry = dict(span_id=identifier(), parent_span_id=parent['span_id'] if parent else None,
                          module=self.module, operation=self.operation, purpose=self.purpose,
                          start_sequence=self.collector.next_sequence(), execution_status='running', outcome='unknown')
        self.started = time.monotonic()
        self.collector.add(self.entry)
        self.token = span.set(self.entry)
        emit('step.started', **dict(self.entry), input=safe_metadata(self.input))
        return self

    def result(self, value=None, outcome=None):
        metadata = safe_metadata(value)
        if isinstance(metadata, dict):
            metadata = dict(self.entry.get('result') or {}, **metadata)
        values = dict(result=metadata)
        if outcome:
            values['outcome'] = outcome
        self.collector.update(self.entry, **values)

    def __exit__(self, kind, error, traceback):
        values = dict(duration_ms=round((time.monotonic()-self.started)*1000, 3), execution_status='returned')
        if error:
            outcome = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'timeout' if isinstance(error, TimeoutError) else 'rejected' if getattr(error, 'status_code', 500) < 500 else 'failed'
            values.update(execution_status='cancelled' if outcome == 'cancelled' else 'timeout' if outcome == 'timeout' else 'raised',
                          outcome=outcome, error={k:v for k,v in error_metadata(error).items() if k != 'frames'})
        self.collector.update(self.entry, **values)
        terminal = dict(self.entry)
        terminal.update(values)
        emit('step.completed', level=logging.WARNING if error else logging.INFO, **terminal)
        span.reset(self.token)
        if self.root:
            self.collector.outcome = self.entry['outcome']
            self.root.__exit__(kind, error, traceback)
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        return self.__exit__(*args)


def set_outcome(outcome, **metadata):
    collector, entry = current.get(), span.get()
    if collector and entry:
        collector.update(entry, outcome=outcome, result=safe_metadata(metadata))


def start_task(awaitable, *, name, log_context=None):
    """Create the separate collector before HTTP can finish, registering its link."""
    parent = current.get()
    context = log_context or envelope()
    child = Collector(name, quiet=bool(parent and parent.quiet), maximum=setting('log_summary_max_steps', 500), **validated_envelope(context))
    if parent:
        parent.link(child)
    async def run():
        with workflow(name, log_context=context, collector=child):
            return await awaitable
    task = asyncio.create_task(run())
    def cancelled_before_start(done):
        if done.cancelled() and not child.closed:
            import inspect
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            with workflow(name, log_context=context, collector=child):
                child.outcome = 'cancelled'
    task.add_done_callback(cancelled_before_start)
    return task
