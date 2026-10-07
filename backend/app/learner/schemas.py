from app.core.identifiers import LearnerId
"""Typed, serializable request and response contracts for learner services."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class LearnerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class ConceptResolutionRequest(LearnerSchema):
    label: str = Field(min_length=1, max_length=200)
    learner_id: LearnerId | None = None
    context_id: str | None = None
    surrounding_text: str | None = Field(default=None, max_length=4000)

    @model_validator(mode='after')
    def require_context_owner(self):
        if self.context_id and self.learner_id is None:
            raise ValueError('Contextual resolution requires learner_id')
        return self


class ConceptResolution(LearnerSchema):
    status: Literal["resolved", "ambiguous", "candidate", "rejected"]
    concept_id: str | None = None
    canonical_name: str | None = None
    confidence: float = Field(ge=0, le=1)
    method: str | None = None
    candidate_id: str | None = None
    alternatives: list[str] = Field(default_factory=list)


class EvidenceSubmissionRequest(LearnerSchema):
    learner_id: LearnerId
    concept_id: str = Field(min_length=1)
    source_type: Literal[
        "CHAT",
        "QUIZ",
        "MOCK_EXAM",
        "HANDWRITTEN_ASSESSMENT",
        "EXERCISE",
        "CALIBRATION",
        "MANUAL_CONFIRMATION",
    ]
    result: Literal["CORRECT", "PARTIAL", "INCORRECT", "UNKNOWN"]
    context_id: str | None = None
    source_id: str | None = None
    supersedes_evidence_id: str | None = None
    item_id: str | None = Field(default=None, min_length=1, max_length=300)
    session_id: str | None = Field(default=None, min_length=1, max_length=300)
    item_revision: int = Field(default=1, ge=1)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)
    difficulty: float | None = Field(default=None, ge=0, le=1)
    independence: float | None = Field(default=None, ge=0, le=1)
    hint_count: int = Field(default=0, ge=0)
    attempt_number: int | None = Field(default=None, ge=1)
    evidence_confidence: float = Field(default=1, ge=0, le=1)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_score_pair(self) -> "EvidenceSubmissionRequest":
        if (self.score is None) != (self.max_score is None):
            raise ValueError("score and max_score must be provided together")
        if self.score is not None and self.max_score is not None:
            if self.score > self.max_score:
                raise ValueError("score cannot exceed max_score")
            if ((self.result == 'CORRECT' and self.score != self.max_score) or
                    (self.result == 'INCORRECT' and self.score != 0) or
                    (self.result == 'PARTIAL' and not 0 < self.score < self.max_score)):
                raise ValueError('result must agree with score and max_score')
        return self

    @field_validator("occurred_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(timezone.utc)


class EvidenceSubmissionResult(LearnerSchema):
    evidence_id: str
    accepted: bool
    status: Literal["accepted", "pending", "duplicate"]
    concept_id: str
    state_version: int | None = None
    verification_required: bool = False


class ConceptStateRequest(LearnerSchema):
    learner_id: LearnerId
    concept_id: str = Field(min_length=1)


class ConceptStateResponse(LearnerSchema):
    learner_id: LearnerId
    concept_id: str
    mastery: float | None = Field(default=None, ge=0, le=1)
    estimate_confidence: float | None = Field(default=None, ge=0, le=1)
    retention_confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    independent_successes: int = Field(default=0, ge=0)
    hint_dependency: float | None = Field(default=None, ge=0, le=1)
    difficulty_tested: float | None = Field(default=None, ge=0, le=1)
    version: int = Field(default=0, ge=0)
    mastery_policy_version: str = "legacy"
    retention_policy_version: str = "legacy"
    verification_required: bool = False
    last_evidence_at: datetime | None = None
    last_verified_at: datetime | None = None
    last_demonstrated_at: datetime | None = None
    knowledge_status: Literal['insufficient_evidence', 'needs_practice', 'developing', 'demonstrated', 'needs_verification'] = 'insufficient_evidence'
    mastery_lower_bound: float = Field(default=0, ge=0, le=1)
    mastery_upper_bound: float = Field(default=1, ge=0, le=1)
    independent_item_count: int = 0
    recommended_difficulty: float = Field(default=0.3, ge=0, le=1)


class LearnerContextRequest(LearnerSchema):
    learner_id: LearnerId
    query: str = Field(min_length=1, max_length=4000)
    context_ids: list[str] | None = Field(default=None, max_length=20)
    max_concepts: int = Field(default=8, ge=1, le=50)
    include_related: bool = True


class PerformanceEstimate(LearnerSchema):
    expected_score: float = Field(ge=0, le=1)
    lower_bound: float = Field(ge=0, le=1)
    upper_bound: float = Field(ge=0, le=1)
    supported: bool
    evidence_weight: float = Field(ge=0)


class LearnerContextConcept(LearnerSchema):
    concept_id: str
    name: str
    mastery: float | None = Field(default=None, ge=0, le=1)
    estimate_confidence: float | None = Field(default=None, ge=0, le=1)
    retention_confidence: float | None = Field(default=None, ge=0, le=1)
    misconceptions: list[str] = Field(default_factory=list, max_length=3)
    knowledge_status: str = 'insufficient_evidence'
    mastery_lower_bound: float = Field(default=0, ge=0, le=1)
    mastery_upper_bound: float = Field(default=1, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    relevance: float = Field(default=0.5, ge=0, le=1)
    target_difficulty: float = Field(default=0.5, ge=0, le=1)
    target_performance: PerformanceEstimate | None = None
    verification_required: bool = False
    hint_dependency: float | None = Field(default=None, ge=0, le=1)


class LearnerContextPacket(LearnerSchema):
    active_contexts: list[str] = Field(default_factory=list, max_length=20)
    context_ids: list[str] = Field(default_factory=list, max_length=20)
    concepts: list[LearnerContextConcept] = Field(default_factory=list, max_length=50)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StudyRecommendationsRequest(LearnerSchema):
    learner_id: LearnerId
    context_ids: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=5, ge=1, le=50)


class StudyRecommendation(LearnerSchema):
    concept_id: str
    name: str
    reason: str
    priority: float = Field(ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    relevance: float = Field(default=0.5, ge=0, le=1)
    recommended_difficulty: float = Field(default=0.3, ge=0, le=1)
    knowledge_status: str = 'insufficient_evidence'


class VerificationCandidatesRequest(LearnerSchema):
    learner_id: LearnerId
    context_ids: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=5, ge=1, le=50)


class VerificationCandidate(LearnerSchema):
    concept_id: str
    name: str
    reason: str
    priority: float = Field(ge=0, le=1)
    mastery: float | None = None
    estimate_confidence: float | None = None
    retention_confidence: float | None = None
    recommended_difficulty: float = Field(default=0.5, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)


class ActivateLearningContextRequest(LearnerSchema):
    learner_id: LearnerId
    context_id: str = Field(min_length=1)
    exclusive: bool = True


class ResolveLearningContextRequest(LearnerSchema):
    learner_id: LearnerId
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    activate: bool = False


class ContextActivityRequest(LearnerSchema):
    learner_id: LearnerId
    context_id: str = Field(min_length=1)
    reason: str = Field(default="learning_activity", min_length=1, max_length=200)
    occurred_at: datetime | None = None


class ContextTransitionRequest(ContextActivityRequest):
    status: Literal["ACTIVE", "RELATED", "DORMANT", "ARCHIVED"]


class ConfirmEvidenceRequest(LearnerSchema):
    learner_id: LearnerId
    evidence_id: str = Field(min_length=1)
    confirmation_source: str = Field(min_length=1, max_length=200)


class LearningGoalRequest(LearnerSchema):
    learner_id: LearnerId
    context_id: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    target_difficulty: float = Field(default=0.5, ge=0, le=1)


class PerformancePredictionRequest(ConceptStateRequest):
    difficulty: float = Field(ge=0, le=1)


class PerformancePrediction(PerformanceEstimate):
    concept_id: str
    policy_version: str


class ActiveContextsRequest(LearnerSchema):
    learner_id: LearnerId


class LearningContextSummary(LearnerSchema):
    context_id: str
    name: str
    status: Literal["ACTIVE", "RELATED", "DORMANT", "ARCHIVED"]
    relevance_score: float | None = Field(default=None, ge=0, le=1)


class ActiveContextsResponse(LearnerSchema):
    contexts: list[LearningContextSummary] = Field(default_factory=list)
