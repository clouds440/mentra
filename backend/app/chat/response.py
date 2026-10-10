from typing import Literal
from pydantic import BaseModel, Field, field_validator
from app.rag.schemas import SourceReference, ChatSelection


class ChatResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    conversation_title: str | None = Field(default=None, max_length=80)
    sources: list[SourceReference] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    retrieval_status: str = 'no_eligible_sources'
    retrieval_warning: str | None = None
    retrieval_scope: ChatSelection | None = None
    history_references: list[dict] = Field(default_factory=list)
    memory_references: list[dict] = Field(default_factory=list)
    event_proposals: list[dict] = Field(default_factory=list)
    event_references: list[dict] = Field(default_factory=list)
    assessment_cards: list[dict] = Field(default_factory=list)

    @field_validator('assessment_cards')
    @classmethod
    def latest_assessment_cards(cls, cards):
        # Several tool rounds may revisit the same assessment. Keep its latest
        # card once; different revised versions have different assessment IDs.
        unique = {}
        for card in cards:
            unique[card['assessment']['id']] = card
        return list(unique.values())


