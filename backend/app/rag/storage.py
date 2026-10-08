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


class FileStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def path(self, key: str) -> Path:
        if not re.fullmatch(r'[0-9a-f]{32}', key):
            raise ValueError('Invalid storage reference')
        return self.root / key

    def store(self, file: BinaryIO, maximum: int) -> StoredBlob:
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            self.root.chmod(0o700)
        key = uuid4().hex
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
