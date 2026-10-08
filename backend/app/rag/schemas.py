"""Public RAG contracts; ownership is always bound by the caller, never HTTP data."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class RAGSchema(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SearchRequest(RAGSchema):
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal['STANDARD', 'SOURCE_SPECIFIC', 'CROSS_CONTEXT', 'CONCEPT_FOCUSED'] = 'STANDARD'
    context_ids: list[str] | None = Field(default=None, max_length=20)
    document_ids: list[str] | None = Field(default=None, max_length=20)
    concept_ids: list[str] | None = Field(default=None, max_length=20)
    include_archived: bool = False
    limit: int = Field(default=8, ge=1, le=20)
    token_budget: int = Field(default=2400, ge=100, le=4000)


class ChatSelection(RAGSchema):
    mode: Literal['STANDARD', 'SOURCE_SPECIFIC', 'CROSS_CONTEXT'] = 'STANDARD'
    context_ids: list[str] | None = Field(default=None, max_length=20)
    document_ids: list[str] | None = Field(default=None, max_length=20)
    include_archived: bool = False


class AssessmentGroundingRequest(RAGSchema):
    """Internal approved study-source scope; not an ordinary chat/HTTP mode."""
    query: str = Field(min_length=1, max_length=4000)
    approved_document_ids: list[str] = Field(min_length=1, max_length=20)
    context_ids: list[str] | None = Field(default=None, max_length=20)
    include_archived: bool = False
    limit: int = Field(default=8, ge=1, le=20)


class DocumentUpdate(RAGSchema):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    context_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)
    archived: bool | None = None


class RevisionRequest(RAGSchema):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=120)


class SourceSpan(RAGSchema):
    page: int | None = None
    slide: int | None = None
    block: int
    start: int
    end: int
    method: str = 'native'


class SourceReference(RAGSchema):
    token: str
    document_id: str
    version_id: str
    generation_id: str
    chunk_id: str
    title: str
    heading_path: list[str]
    spans: list[SourceSpan]
    excerpt: str
    warnings: list[str] = Field(default_factory=list)
    include_archived: bool = False


class RetrievedChunk(RAGSchema):
    content: str
    score: float
    score_type: str
    source: SourceReference
    context_ids: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    dense_rank: int | None = None
    lexical_rank: int | None = None
    reranker_rank: int | None = None


class RetrievalDiagnostics(RAGSchema):
    request_id: str = ''
    timings_ms: dict[str, float] = Field(default_factory=dict)
    eligible_documents: int = 0
    dense_candidates: int = 0
    lexical_candidates: int = 0
    hydrated_candidates: int = 0
    rejected_candidates: int = 0
    query_cache_hit: bool = False
    reranking: Literal['disabled', 'ok', 'fallback'] = 'disabled'


class RetrievalResult(RAGSchema):
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    status: Literal['ok', 'no_eligible_sources', 'no_matches', 'degraded']
    context_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    token_use: int = 0
    pipeline_version: str = 'dense-lexical-rrf-v1'
    diagnostics: RetrievalDiagnostics = Field(default_factory=RetrievalDiagnostics)
    mode: str = 'STANDARD'
