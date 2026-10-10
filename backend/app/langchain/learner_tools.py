"""Learner tools usable by LangChain or LangGraph, bound to trusted workflow scope.

Bind identity in server orchestration, never let a model choose a student ID.
Evidence recording is opt-in and carries immutable server-supplied provenance.
"""

from datetime import datetime
from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import Field

from app.learner.schemas import (
    ActiveContextsRequest, ConceptResolutionRequest, EvidenceSubmissionRequest,
    LearnerContextRequest, LearnerSchema, StudyRecommendationsRequest, VerificationCandidatesRequest,
)


class ContextToolInput(LearnerSchema):
    query: str = Field(min_length=1, max_length=4000)
    context_ids: list[str] | None = Field(default=None, max_length=20)
    max_concepts: int = Field(default=8, ge=1, le=8)


class RankingToolInput(LearnerSchema):
    context_ids: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=5, ge=1, le=5)


class ResolutionToolInput(LearnerSchema):
    label: str = Field(min_length=1, max_length=200)
    context_id: str | None = None
    surrounding_text: str | None = Field(default=None, max_length=4000)


class ObservationToolInput(LearnerSchema):
    concept_id: str = Field(min_length=1)
    result: Literal['CORRECT', 'PARTIAL', 'INCORRECT', 'UNKNOWN']
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)
    difficulty: float | None = Field(default=None, ge=0, le=1)
    independence: float | None = Field(default=None, ge=0, le=1)
    hint_count: int = Field(default=0, ge=0)
    attempt_number: int | None = Field(default=None, ge=1)


class ObservationProvenance(LearnerSchema):
    source_type: Literal['CHAT', 'QUIZ', 'MOCK_EXAM', 'EXERCISE', 'CALIBRATION', 'HANDWRITTEN_ASSESSMENT']
    source_id: str = Field(min_length=1)
    occurred_at: datetime
    context_id: str | None = None
    evidence_confidence: float = Field(ge=0, le=1)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    item_id: str | None = Field(default=None, min_length=1, max_length=300)
    session_id: str | None = Field(default=None, min_length=1, max_length=300)
    item_revision: int = Field(default=1, ge=1)


def create_learner_tools(learner, learner_id: str, *, provenance: ObservationProvenance | None = None):
    from app.core.identifiers import canonical_learner_id
    learner_id = canonical_learner_id(learner_id)

    def active():
        return learner.get_active_contexts(ActiveContextsRequest(learner_id=learner_id)).model_dump(mode='json')

    def context(**kwargs):
        return learner.get_relevant_context(LearnerContextRequest(learner_id=learner_id, **kwargs)).model_dump(mode='json')

    def recommendations(**kwargs):
        return [r.model_dump(mode='json') for r in learner.get_study_recommendations(
            StudyRecommendationsRequest(learner_id=learner_id, **kwargs))]

    def verification(**kwargs):
        return [r.model_dump(mode='json') for r in learner.get_verification_candidates(
            VerificationCandidatesRequest(learner_id=learner_id, **kwargs))]

    def resolve(**kwargs):
        if not kwargs.get('context_id'):
            active_contexts = learner.get_active_contexts(ActiveContextsRequest(learner_id=learner_id)).contexts
            if len(active_contexts) == 1:
                kwargs['context_id'] = active_contexts[0].context_id
        if kwargs.get('context_id'):
            # Validate scope through the public read contract before resolution.
            learner.get_relevant_context(LearnerContextRequest(learner_id=learner_id, query=kwargs['label'],
                                         context_ids=[kwargs['context_id']], max_concepts=1))
        return learner.resolve_concept(ConceptResolutionRequest(learner_id=learner_id, **kwargs)).model_dump(mode='json')

    tools = [
        StructuredTool.from_function(active, name='get_active_learning_contexts', description='Get current learning contexts.'),
        StructuredTool.from_function(context, name='get_relevant_learner_context', args_schema=ContextToolInput,
                                     description='Get a compact learner packet relevant to the current question.'),
        StructuredTool.from_function(recommendations, name='get_study_recommendations', args_schema=RankingToolInput,
                                     description='Get deterministic study priorities for current or requested contexts.'),
        StructuredTool.from_function(recommendations, name='get_student_weaknesses', args_schema=RankingToolInput,
                                     description='Get ranked study weaknesses for current or requested contexts.'),
        StructuredTool.from_function(verification, name='get_verification_candidates', args_schema=RankingToolInput,
                                     description='Get concepts to verify, with suggested difficulty and reasons.'),
        StructuredTool.from_function(resolve, name='resolve_student_concept', args_schema=ResolutionToolInput,
                                     description='Resolve a label to canonical identity; ambiguous labels stay candidates.'),
    ]
    if provenance is not None:
        def record(**kwargs):
            return learner.submit_evidence(EvidenceSubmissionRequest(
                learner_id=learner_id, **provenance.model_dump(), **kwargs,
            )).model_dump(mode='json')

        tools.append(StructuredTool.from_function(record, name='record_learning_evidence', args_schema=ObservationToolInput,
                     description='Record an observed answer under the current server-authorized source. Never set mastery.'))
    return tools
