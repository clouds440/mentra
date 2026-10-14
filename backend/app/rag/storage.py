"""Private immutable blobs. Generated keys, bounded streaming, no user paths."""
import hashlib
import os
import re
import time
from pathlib import Path
from uuid import uuid4
from app.core.exceptions import AppError
from app.rag.ports import StoredBlob
from typing import BinaryIO
from contextlib import contextmanager


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class FileStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._sweep = None

    def close(self):
        if self._sweep is not None:
            self._sweep.close()
            self._sweep = None

    def sweep_unknown_batch(self, referenced_keys, minimum_age, batch_size=100):
        if not self.root.exists():
            return
        if self._sweep is None:
            self._sweep = os.scandir(self.root)
        candidates = []
        try:
            for _ in range(max(1, min(batch_size, 1000))):
                entry = next(self._sweep, None)
                if entry is None:
                    self.close()
                    break
                if entry.is_file(follow_symlinks=False) and re.fullmatch(r'[0-9a-f]{32}', entry.name):
                    if time.time() - entry.stat().st_mtime > minimum_age:
                        candidates.append(entry.name)
            known = referenced_keys(candidates)
            for key in candidates:
                if key not in known:
                    with self._key_guard(key, blocking=False) as acquired:
                        if acquired and not referenced_keys([key]):
                            path = self.path(key)
                            if path.exists() and time.time() - path.stat().st_mtime > minimum_age:
                                self.remove(key)
        except BaseException:
            self.close()
            raise

    def path(self, key: str) -> Path:
        if not re.fullmatch(r'[0-9a-f]{32}', key):
            raise ValueError('Invalid storage reference')
        return self.root / key

    def store(self, file: BinaryIO, maximum: int) -> StoredBlob:
        return self._store(file, maximum, uuid4().hex)

    @contextmanager
    def staged_store(self, file, maximum):
        key = uuid4().hex
        with self._key_guard(key):
            yield self._store(file, maximum, key)

    @contextmanager
    def _key_guard(self, key, *, blocking=True):
        self.path(key)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ('.' + key + '.lock')
        lock = path.open('a+b')
        acquired = False
        try:
            if os.name == 'nt':
                import msvcrt
                if not path.stat().st_size:
                    lock.write(b'\0')
                    lock.flush()
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
                    acquired = True
                except OSError:
                    if blocking:
                        raise
            else:
                import fcntl
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
                    acquired = True
                except BlockingIOError:
                    pass
            yield acquired
        finally:
            if acquired:
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
            if acquired:
                path.unlink(missing_ok=True)

    def _store(self, file, maximum, key):
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            self.root.chmod(0o700)
        target = self.path(key)
        digest, size = hashlib.sha256(), 0
        try:
            with target.open('xb') as output:
                if os.name != 'nt':
                    target.chmod(0o600)
                while data := file.read(1024 * 1024):
                    size += len(data)
                    if size > maximum:
                        raise AppError('RAG_FILE_TOO_LARGE', 'Material exceeds the upload size limit.', 413)
                    digest.update(data)
                    output.write(data)
                output.flush()
                os.fsync(output.fileno())
            if not size:
                raise AppError('RAG_EMPTY_FILE', 'Choose a non-empty file.', 422)
            return dict(storage_key=key, size_bytes=size, file_hash=digest.hexdigest())
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def remove(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def sweep_unknown(self, known_keys: set[str], minimum_age: int) -> None:
        if not self.root.exists():
            return
        for path in self.root.iterdir():
            if path.is_file() and re.fullmatch(r'[0-9a-f]{32}', path.name) and path.name not in known_keys:
                if time.time() - path.stat().st_mtime > minimum_age:
                    self.remove(path.name)
