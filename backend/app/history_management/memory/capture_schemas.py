"""One short structured background extraction, including the existing admission flags."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .validation import Admission

class CapturedMemory(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1, max_length=240)
    category: Literal['fact', 'goal', 'preference']
    evidence_quote: str = Field(min_length=1, max_length=1000)
    equivalent_memory_id: UUID | None = None
    admission: Admission

class MemoryCapture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[CapturedMemory] = Field(default_factory=list, max_length=6)
