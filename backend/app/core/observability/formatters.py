import json
import logging
import os
from datetime import datetime, timezone
from .sanitization import error_metadata


class EventFormatter(logging.Formatter):
    def __init__(self, mode='console'):
        super().__init__()
        self.mode = mode

    def format(self, record):
        data = getattr(record, 'workflow_event', None)
        if data is None:
            # Legacy and dependency free text is deliberately not serialized.
            data = dict(schema_version=1, timestamp=datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                        event='application.message', logger=record.name, service='mentra-backend', pid=os.getpid())
            from . import events
            data['process_role'] = events.process_role
            for key in ('trace_id', 'workflow_id', 'request_id', 'span_id'):
                if getattr(record, key, None):
                    data[key] = getattr(record, key)
            if record.exc_info and record.exc_info[1]:
                data['error'] = error_metadata(record.exc_info[1])
        data = dict(data, level=record.levelname)
        if self.mode == 'json':
            return json.dumps(data, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
        head = f"{data['timestamp']} {record.levelname:<7} {data['event']}"
        fields = ' '.join(f'{key}={json.dumps(value, ensure_ascii=True, separators=(",", ":"))}'
                          for key, value in data.items() if key not in ('timestamp', 'level', 'event', 'summary'))
        summary = data.get('summary')
        if summary:
            fields += '\n  modules: ' + ' -> '.join(summary.get('modules', []))
            for entry in summary.get('operations', []):
                fields += f"\n  {entry['start_sequence']:>4} {entry['operation']} execution={entry['execution_status']} outcome={entry['outcome']} duration_ms={entry.get('duration_ms', 'pending')}"
                if entry.get('result'):
                    fields += ' result=' + json.dumps(entry['result'], ensure_ascii=True)
            for link in summary.get('linked_workflows', []):
                fields += f"\n  workflow {link['workflow_id']} {link['workflow']} state={link['state']}"
                fields += '\n    modules: ' + ' -> '.join(link.get('modules', []))
                for entry in link.get('operations', []):
                    fields += f"\n    {entry['start_sequence']:>4} {entry['operation']} outcome={entry['outcome']} duration_ms={entry.get('duration_ms', 'pending')}"
            if summary.get('summary_truncated'):
                fields += f"\n  summary_truncated=true dropped_steps={summary.get('dropped_steps', 0)} overflow_count={summary.get('overflow_count', 0)}"
        return head + ' ' + fields
