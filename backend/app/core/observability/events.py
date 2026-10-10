import logging
import os
from datetime import datetime, timezone
from .context import current, span

process_role = 'backend'
logging.getLogger('mentra.events').addHandler(logging.NullHandler())


def emit(event, *, level=logging.INFO, **fields):
    """Instrumentation must never replace a domain result with a logging error."""
    try:
        collector = current.get()
        record = dict(schema_version=1, timestamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                      event=event, service='mentra-backend', process_role=process_role, pid=os.getpid())
        if collector:
            record.update(trace_id=collector.trace_id, workflow_id=collector.workflow_id,
                          workflow=collector.workflow, sequence=collector.next_sequence())
            for key in ('request_id', 'origin_request_id', 'origin_workflow_id', 'origin_span_id'):
                value = getattr(collector, key)
                if value:
                    record[key] = value
            if collector.closed and event not in ('workflow.completed', 'request.completed', 'summary.part'):
                record['after_parent_completion'] = True
            if collector.quiet and level < logging.WARNING:
                level = logging.DEBUG
        record.update(fields)
        logging.getLogger('mentra.events').log(level, event, extra={'workflow_event': record})
    except Exception:
        pass


class ContextFilter(logging.Filter):
    def filter(self, record):
        collector, operation = current.get(), span.get()
        if collector and not hasattr(record, 'workflow_event'):
            record.trace_id = collector.trace_id
            record.workflow_id = collector.workflow_id
            record.request_id = collector.request_id
            record.span_id = operation['span_id'] if operation else None
            if collector.quiet and record.levelno < logging.WARNING:
                record.levelno, record.levelname = logging.DEBUG, 'DEBUG'
                if logging.getLogger().getEffectiveLevel() > logging.DEBUG:
                    return False
        return True
