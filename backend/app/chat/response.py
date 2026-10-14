from .interactions import ChoiceCard
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.web_search import WebSource, SearchResult
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
    interactions: list[ChoiceCard] = Field(default_factory=list)
    assessment_cards: list[dict] = Field(default_factory=list)
    tool_warnings: list[dict] = Field(default_factory=list, max_length=16)
    web_sources: list[WebSource] = Field(default_factory=list, max_length=10)
    web_citations: list[str] = Field(default_factory=list, max_length=10)
    web_searches: list[SearchResult] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def validate_web_registry(self):
        tokens = [source.token for source in self.web_sources]
        urls = [source.url for source in self.web_sources]
        if any(not token for token in tokens) or len(tokens) != len(set(tokens)) or len(urls) != len(set(urls)):
            raise ValueError('Web source tokens and URLs must be unique.')
        if len(self.web_citations) != len(set(self.web_citations)) or not set(self.web_citations).issubset(tokens):
            raise ValueError('Web citations must resolve to returned evidence.')
        return self

    @field_validator('assessment_cards')
    @classmethod
    def latest_assessment_cards(cls, cards):
        # Several tool rounds may revisit the same assessment. Keep its latest
        # card once; different revised versions have different assessment IDs.
        unique = {}
        for card in cards:
            if card.get('generation_job_id'):
                key = ('generation', card['generation_job_id'])
            elif isinstance(card.get('assessment'), dict) and card['assessment'].get('id'):
                key = ('assessment', card['assessment']['id'])
            else:
                raise ValueError('Assessment cards require an assessment or generation job ID.')
            unique[key] = card
        return list(unique.values())


