import io
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.core.observability.files import DailyFileHandler


def event_record(day, event='test.completed'):
    record = logging.LogRecord('mentra.events', logging.INFO, '', 0, 'secret free text', (), None)
    record.created = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
    record.workflow_event = dict(timestamp=day + 'T00:00:00.000Z', event=event, process_role='api')
    return record


class DailyLogTests(unittest.TestCase):
    def test_midnight_restart_and_json_format(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = DailyFileHandler(directory)
            sink.handle(event_record('2026-10-10'))
            sink.handle(event_record('2026-10-11'))
            DailyFileHandler(directory).handle(event_record('2026-10-11'))
            files = sorted(Path(directory).glob('*.log'))
            self.assertEqual([f.name for f in files], ['backend-2026-10-10.log', 'backend-2026-10-11.log'])
            self.assertEqual([len(f.read_text().splitlines()) for f in files], [1, 2])
            for f in files:
                for line in f.read_text().splitlines():
                    self.assertEqual(json.loads(line)['event'], 'test.completed')
                    self.assertNotIn('secret free text', line)

    def test_failure_is_visible_throttled_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'logs'
            target.write_text('blocked')
            sink = DailyFileHandler(target)
            with patch('sys.stderr', new_callable=io.StringIO) as stderr:
                sink.handle(event_record('2026-10-10'))
                sink.handle(event_record('2026-10-10'))
                self.assertEqual(stderr.getvalue().count('logging.file_write_failed'), 1)
                self.assertNotIn('secret', stderr.getvalue())
            target.unlink()
            sink.handle(event_record('2026-10-10'))
            self.assertEqual(len(list(target.glob('*.log'))), 1)

    def test_separate_processes_do_not_interleave_large_records(self):
        with tempfile.TemporaryDirectory() as directory:
            script = '''
import logging, sys
from app.core.observability.files import DailyFileHandler
sink = DailyFileHandler(sys.argv[1])
for i in range(60):
    record = logging.LogRecord('mentra.events', logging.INFO, '', 0, '', (), None)
    record.workflow_event = dict(timestamp='test', event='test.completed', pid=__import__('os').getpid(), sequence=i, padding='x'*40000)
    sink.handle(record)
'''
            processes = [subprocess.Popen([sys.executable, '-c', script, directory], stderr=subprocess.PIPE, stdout=subprocess.PIPE) for _ in range(3)]
            try:
                results = [process.communicate(timeout=30) for process in processes]
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()
            for process, (output, error) in zip(processes, results):
                self.assertEqual(process.returncode, 0, error.decode())
                self.assertEqual(error, b'')
            records = [json.loads(line) for f in Path(directory).glob('*.log') for line in f.read_text().splitlines()]
            self.assertEqual(len(records), 180)
            self.assertEqual(len({(r['pid'], r['sequence']) for r in records}), 180)

    def test_configuration_and_disable(self):
        with tempfile.TemporaryDirectory() as directory:
            script = '''
import logging, sys
from app.core.config import settings
from app.core.logging import configure_logging, workflow_logger
from app.core.observability.files import DailyFileHandler
settings.log_directory = sys.argv[1]
settings.log_file_enabled = True
settings.log_level = 'INFO'
configure_logging('api')
configure_logging('api')
assert sum(isinstance(h, DailyFileHandler) for h in logging.getLogger().handlers) == 1
workflow_logger.event('file.test')
settings.log_file_enabled = False
configure_logging('api')
workflow_logger.event('disabled.test')
'''
            result = subprocess.run([sys.executable, '-c', script, directory], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            records = [json.loads(line) for f in Path(directory).glob('*.log') for line in f.read_text().splitlines()]
            self.assertEqual(sum(r['event'] == 'file.test' for r in records), 1)
            self.assertFalse(any(r['event'] == 'disabled.test' for r in records))
