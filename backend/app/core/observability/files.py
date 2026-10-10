"""Daily JSON logs shared safely by API and worker processes.

No file is renamed at midnight: each record selects its UTC calendar day.
An OS lock protects complete records, including across Docker containers sharing
the directory. Open/close per record also allows recovery after a sink failure.
"""
import logging
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from .formatters import EventFormatter


@contextmanager
def writer_lock(directory):
    with (directory / '.writer.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b'\0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class DailyFileHandler(logging.Handler):
    def __init__(self, directory):
        super().__init__()
        self.directory = Path(directory)
        self.setFormatter(EventFormatter('json'))
        self._last_failure = float('-inf')

    def emit(self, record):
        try:
            payload = (self.format(record) + '\n').encode('utf-8')
            day = datetime.fromtimestamp(record.created, timezone.utc).date().isoformat()
            self.directory.mkdir(parents=True, exist_ok=True)
            with writer_lock(self.directory):
                with (self.directory / f'backend-{day}.log').open('ab') as output:
                    output.write(payload)
                    output.flush()
        except Exception:
            # Never recurse through logging or expose raw exception messages.
            # Keep terminal logging working, and retry the file on the next record.
            now = monotonic()
            if now - self._last_failure >= 60:
                self._last_failure = now
                try:
                    stamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                    sys.stderr.write(json.dumps(dict(schema_version=1, timestamp=stamp,
                        level='ERROR', event='logging.file_write_failed', service='mentra-backend',
                        pid=os.getpid(), terminal_logging_active=True)) + '\n')
                except Exception:
                    pass
