import asyncio
import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk


class LatencyObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_separates_first_text_total_and_callback_wait(self):
        from app.langchain.provider_invocation import invoke_provider
        async def stream(_):
            yield AIMessageChunk(content='Answer')
        async def callback(_):
            await asyncio.sleep(.01)
        with patch('app.langchain.provider_invocation.workflow_logger.event') as event:
            result = await invoke_provider(SimpleNamespace(astream=stream), [], on_delta=callback)
        self.assertEqual(result.content, 'Answer')
        records = {call.args[0]: call.kwargs for call in event.call_args_list}
        self.assertGreaterEqual(records['provider.completed']['callback_ms'], 9)
        self.assertGreaterEqual(records['provider.completed']['duration_ms'], records['provider.completed']['callback_ms'])
        self.assertEqual(records['provider.first_text']['provider_call_id'], records['provider.completed']['provider_call_id'])

    def test_database_timing_omits_statement_and_values_even_on_error(self):
        from sqlalchemy import create_engine, text
        from app.db.timing import instrument_engine
        engine = instrument_engine(create_engine('sqlite://'))
        try:
            with patch('app.db.timing.emit') as emit, engine.connect() as connection:
                connection.execute(text('SELECT :value'), {'value': 'private-content'})
                with self.assertRaises(Exception): connection.execute(text('SELECT missing_private_column'))
            records = [call.kwargs for call in emit.call_args_list]
            self.assertEqual([r['outcome'] for r in records], ['success', 'failed'])
            self.assertTrue(all(r['duration_ms'] >= 0 for r in records))
            self.assertNotIn('private', json.dumps(records))
        finally:
            engine.dispose()

    def test_background_file_writer_drains_ordered_records(self):
        from app.core.observability.files import DailyFileHandler
        with tempfile.TemporaryDirectory() as directory:
            handler = DailyFileHandler(directory, queued=True)
            try:
                for i in range(30):
                    record = logging.LogRecord('mentra.events', logging.INFO, '', 1, 'event', (), None)
                    record.workflow_event = dict(event='timing.test', sequence=i, trace_id='trace')
                    handler.handle(record)
                handler.flush()
                rows = [json.loads(line) for path in Path(directory).glob('backend-*.log') for line in path.read_text().splitlines()]
                self.assertEqual([row['sequence'] for row in rows], list(range(30)))
                self.assertEqual({row['trace_id'] for row in rows}, {'trace'})
            finally:
                handler.close()
            handler.handle(record)
            handler.flush()
            self.assertEqual(handler._queue.unfinished_tasks, 0)
