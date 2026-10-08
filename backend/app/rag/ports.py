"""Ports used by current ingestion; adapters retain their own file/tool details."""
from pathlib import Path
from typing import BinaryIO, Protocol, TypedDict, Any, NotRequired


class StoredBlob(TypedDict):
    storage_key: str
    size_bytes: int
    file_hash: str
    media_type: NotRequired[str]


class PrivateSourceStorage(Protocol):
    def store(self, file: BinaryIO, maximum: int) -> StoredBlob: ...
    def path(self, key: str) -> Path: ...
    def remove(self, key: str) -> None: ...
    def sweep_unknown(self, known_keys: set[str], minimum_age: int) -> None: ...


class DocumentParser(Protocol):
    version: str
    def detect(self, path: Path, filename: str) -> str: ...
    def capabilities(self) -> dict[str, Any]: ...
    def parse(self, path: Path, media_type: str, max_pages: int, timeout: int) -> dict[str, Any]: ...
