from pathlib import Path
from typing import Protocol
from app.documents.schemas import DocumentPayload


class FormatReader(Protocol):
    formats: tuple[str, ...]
    def available(self) -> bool: ...
    def read(self, path: Path, kind: str, max_pages: int) -> DocumentPayload: ...
