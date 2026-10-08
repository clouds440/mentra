from typing import Literal
from pydantic import BaseModel, Field
from app.rag.schemas import SourceReference, ChatSelection


class ChatResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    sources: list[SourceReference] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    retrieval_status: str = 'no_eligible_sources'
    retrieval_warning: str | None = None
    retrieval_scope: ChatSelection | None = None
    history_references: list[dict] = Field(default_factory=list)
    memory_references: list[dict] = Field(default_factory=list)


