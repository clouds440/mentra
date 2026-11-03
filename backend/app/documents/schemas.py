from dataclasses import dataclass, field
from typing import TypedDict, Required, NotRequired


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
    visuals: NotRequired[list[dict]]


@dataclass
class DocumentContent:
    format: str
    media_type: str
    blocks: list[DocumentBlock]
    warnings: list[str]
    reader_revision: str
    visuals: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n\n'.join(block['text'] for block in self.blocks if block['text'].strip())
