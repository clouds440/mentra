from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock
from uuid import uuid4
import time


def identifier():
    return uuid4().hex


@dataclass
class Collector:
    workflow: str
    trace_id: str = field(default_factory=identifier)
    workflow_id: str = field(default_factory=identifier)
    request_id: str | None = None
    origin_request_id: str | None = None
    origin_workflow_id: str | None = None
    origin_span_id: str | None = None
    quiet: bool = False
    maximum: int = 500
    started: float = field(default_factory=time.monotonic)
    sequence: int = 0
    closed: bool = False
    closed_at: float | None = None
    entries: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    links: dict = field(default_factory=dict)
    dropped: int = 0
    overflow: int = 0
    outcome: str = 'unknown'
    lock: RLock = field(default_factory=RLock)

    def next_sequence(self):
        with self.lock:
            self.sequence += 1
            return self.sequence

    def add(self, entry):
        with self.lock:
            if self.closed:
                return
            module = entry['module']
            if module not in self.modules:
                if len(self.modules) < 100:
                    self.modules.append(module)
                else:
                    self.overflow += 1
            if len(self.entries) + sum(len(x.get('operations', [])) for x in self.links.values()) < self.maximum:
                self.entries.append(entry)
            else:
                self.dropped += 1

    def update(self, entry, **values):
        with self.lock:
            if not self.closed:
                entry.update(values)

    def link(self, child, summary=None):
        with self.lock:
            if self.closed:
                return
            if child.workflow_id not in self.links and len(self.links) >= 100:
                self.overflow += 1
                return
            link = dict(workflow_id=child.workflow_id, workflow=child.workflow,
                        state='completed' if summary else 'pending')
            if summary:
                available = max(0, self.maximum - len(self.entries) - sum(len(x.get('operations', [])) for k,x in self.links.items() if k != child.workflow_id))
                link.update(outcome=summary['outcome'], modules=summary['modules'],
                            operations=summary['operations'][:available],
                            summary_truncated=summary['summary_truncated'] or len(summary['operations']) > available)
            self.links[child.workflow_id] = link

    def snapshot(self):
        with self.lock:
            return dict(workflow=self.workflow, outcome=self.outcome,
                        duration_ms=round(((self.closed_at or time.monotonic())-self.started)*1000, 3),
                        modules=list(self.modules), operations=[dict(x) for x in self.entries],
                        linked_workflows=[dict(x) for x in self.links.values()],
                        summary_truncated=bool(self.dropped or self.overflow),
                        dropped_steps=self.dropped, overflow_count=self.overflow)

    def close(self):
        with self.lock:
            if self.closed:
                return None
            self.closed = True
            self.closed_at = time.monotonic()
            return self.snapshot()


current: ContextVar[Collector | None] = ContextVar('mentra_workflow', default=None)
span: ContextVar[dict | None] = ContextVar('mentra_span', default=None)


def envelope():
    collector, operation = current.get(), span.get()
    if collector is None:
        return None
    return dict(schema_version=1, trace_id=collector.trace_id,
                origin_request_id=collector.request_id or collector.origin_request_id,
                origin_workflow_id=collector.workflow_id,
                origin_span_id=operation['span_id'] if operation else None)


def validated_envelope(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        return {}
    result = {}
    for key in ('trace_id', 'origin_request_id', 'origin_workflow_id', 'origin_span_id'):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or len(item) != 32 or any(c not in '0123456789abcdef' for c in item):
                return {}
            result[key] = item
    return result if 'trace_id' in result else {}
