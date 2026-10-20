"""Ports used by current ingestion; adapters retain their own file/tool details."""
from pathlib import Path
from typing import Protocol, Any


class DocumentParser(Protocol):
    version: str
    def detect(self, path: Path, filename: str) -> str: ...
    def capabilities(self) -> dict[str, Any]: ...
    def parse(self, path: Path, media_type: str, max_pages: int, timeout: int) -> dict[str, Any]: ...
