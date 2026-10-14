"""Daily JSON logs shared safely by API and worker processes.

No file is renamed at midnight: each record selects its UTC calendar day.
An OS lock protects complete records, including across Docker containers sharing
the directory. Open/close per record also allows recovery after a sink failure.
"""
import logging
from queue import Queue, Full
from threading import Thread, Lock
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from time import monotonic, sleep

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
            deadline = monotonic() + 1
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if monotonic() >= deadline:
                        raise TimeoutError('Log writer is busy') from None
                    sleep(.02)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            deadline = monotonic() + 1
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if monotonic() >= deadline:
                        raise TimeoutError('Log writer is busy') from None
                    sleep(.02)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class DailyFileHandler(logging.Handler):
    def __init__(self, directory, *, queued=False, retention_days=14, max_file_bytes=64 * 1024 * 1024,
                 queue_bytes=8 * 1024 * 1024, shutdown_seconds=2):
        super().__init__()
        self.directory = Path(directory)
        self.setFormatter(EventFormatter('json'))
        self._last_failure = float('-inf')
        self._queue = Queue(maxsize=4096) if queued else None
        self._worker = None
        self.retention_days, self.max_file_bytes = retention_days, max_file_bytes
        self.queue_bytes, self.shutdown_seconds = queue_bytes, shutdown_seconds
        self._pending_bytes, self._pruned_day = 0, None
        self._budget_lock = Lock()
        if queued:
            self._worker = Thread(target=self._drain, name='mentra-log-writer', daemon=True)
            self._worker.start()

    def emit(self, record):
        if self._closed:
            return
        try:
            payload = (self.format(record) + '\n').encode('utf-8')
            day = datetime.fromtimestamp(record.created, timezone.utc).date().isoformat()
            if self._queue is not None:
                with self._budget_lock:
                    if self._pending_bytes + len(payload) > self.queue_bytes:
                        self._report_failure()
                        return
                    self._pending_bytes += len(payload)
                try:
                    self._queue.put_nowait((day, payload))
                except Full:
                    with self._budget_lock:
                        self._pending_bytes -= len(payload)
                    self._report_failure()
            else:
                self._write(day, payload)
        except Exception:
            self._report_failure()

    def _write(self, day, payload):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with writer_lock(self.directory):
                today = datetime.now(timezone.utc).date()
                if self._pruned_day != today:
                    cutoff = (today - timedelta(days=self.retention_days)).isoformat()
                    import re
                    for old in self.directory.glob('backend-*.log'):
                        if re.fullmatch(r'backend-\d{4}-\d{2}-\d{2}\.log', old.name) and old.name[8:18] < cutoff:
                            old.unlink(missing_ok=True)
                    self._pruned_day = today
                target = self.directory / f'backend-{day}.log'
                if (target.stat().st_size if target.exists() else 0) + len(payload) > self.max_file_bytes:
                    self._report_failure()
                    return
                with target.open('ab') as output:
                    output.write(payload)
                    output.flush()
        except Exception:
            self._report_failure()

    def _report_failure(self):
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


    def _drain(self):
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self._write(*item)
            finally:
                if item is not None:
                    with self._budget_lock:
                        self._pending_bytes -= len(item[1])
                self._queue.task_done()

    def flush(self):
        if self._queue is not None and self._worker is not None:
            deadline = monotonic() + self.shutdown_seconds
            with self._queue.all_tasks_done:
                while self._queue.unfinished_tasks:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        self._report_failure()
                        return
                    self._queue.all_tasks_done.wait(remaining)

    def close(self):
        # Handler.handle uses this same lock: no producer can enqueue behind
        # the shutdown sentinel and leave a later flush waiting forever.
        self.acquire()
        try:
            if self._worker is not None:
                self.flush()
                try:
                    self._queue.put_nowait(None)
                except Full:
                    dropped = self._queue.get_nowait()
                    if dropped is not None:
                        with self._budget_lock:
                            self._pending_bytes -= len(dropped[1])
                    self._queue.task_done()
                    self._queue.put_nowait(None)
                    self._report_failure()
                self._worker.join(timeout=self.shutdown_seconds)
                self._worker = None
            super().close()
        finally:
            self.release()
