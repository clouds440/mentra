from app.core.identifiers import LearnerId
"""Learner-owned context selection, consumable by any RAG retrieval adapter."""

from datetime import datetime

from pydantic import Field

from app.learner.schemas import LearnerContextRequest, LearnerSchema


class LearnerRetrievalScope(LearnerSchema):
    learner_id: LearnerId
    context_ids: list[str]
    concept_ids: list[str]

    def qdrant_filter(self):
        # Compatibility for existing consumers; production retrieval uses typed
        # generation selectors. Vendor syntax belongs to the adapter only.
        from app.rag.qdrant_store import legacy_scope_filter
        return legacy_scope_filter(self.learner_id, self.context_ids)


class LearnerDocumentMetadata(LearnerSchema):
    document_id: str = Field(min_length=1)
    learner_id: LearnerId
    learning_context_id: str = Field(min_length=1)
    concept_ids: list[str] = Field(default_factory=list)
    status: str = 'ACTIVE'
    created_at: datetime
    last_used_at: datetime | None = None
    source: str = Field(min_length=1)


def resolve_retrieval_scope(learner, request: LearnerContextRequest) -> LearnerRetrievalScope:
    packet = learner.get_relevant_context(request)
    return LearnerRetrievalScope(learner_id=request.learner_id, context_ids=packet.context_ids,
                                  concept_ids=[c.concept_id for c in packet.concepts])
