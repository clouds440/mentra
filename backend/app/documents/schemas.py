from dataclasses import dataclass
from typing import TypedDict, Required


class DocumentBlock(TypedDict, total=False):
    text: Required[str]
    heading_path: list[str]
    page: int
    slide: int
    method: str
    language: str


class DocumentPayload(TypedDict):
    blocks: list[DocumentBlock]
    warnings: list[str]


@dataclass
class DocumentContent:
    format: str
    media_type: str
    blocks: list[DocumentBlock]
    warnings: list[str]
    reader_revision: str

    @property
    def text(self) -> str:
        return '\n\n'.join(block['text'] for block in self.blocks if block['text'].strip())
