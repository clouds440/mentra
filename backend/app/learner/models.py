"""Provider- and persistence-independent Learner Engine domain objects."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

LearningContextStatus = Literal["ACTIVE", "RELATED", "DORMANT", "ARCHIVED"]
EvidenceSource = Literal[
    "CHAT",
    "QUIZ",
    "MOCK_EXAM",
    "HANDWRITTEN_ASSESSMENT",
    "EXERCISE",
    "CALIBRATION",
    "MANUAL_CONFIRMATION",
]
EvidenceResult = Literal["CORRECT", "PARTIAL", "INCORRECT", "UNKNOWN"]


@dataclass(frozen=True, slots=True)
class Concept:
    id: str
    canonical_name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class LearningContext:
    id: str
    learner_id: str
    name: str
    status: LearningContextStatus
    description: str | None = None
    relevance_score: float | None = None
    last_activity_at: datetime | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class LearnerConceptState:
    learner_id: str
    concept_id: str
    mastery: float | None = None
    estimate_confidence: float | None = None
    retention_confidence: float | None = None
    evidence_count: int = 0
    independent_successes: int = 0
    hint_dependency: float | None = None
    difficulty_tested: float | None = None
    last_evidence_at: datetime | None = None
    last_verified_at: datetime | None = None
    version: int = 0
    policy_data: dict[str, Any] = field(default_factory=dict)
    mastery_policy_version: str = "legacy"
    retention_policy_version: str = "legacy"
    verification_required: bool = False
    last_demonstrated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LearningEvidence:
    id: str
    learner_id: str
    concept_id: str
    source_type: str
    result: EvidenceResult
    occurred_at: datetime
    context_id: str | None = None
    source_id: str | None = None
    supersedes_evidence_id: str | None = None
    item_id: str | None = None
    session_id: str | None = None
    item_revision: int = 1
    score: float | None = None
    max_score: float | None = None
    difficulty: float | None = None
    independence: float | None = None
    hint_count: int = 0
    attempt_number: int | None = None
    evidence_confidence: float | None = None
    extraction_confidence: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Misconception:
    id: str
    learner_id: str
    concept_id: str
    description: str
    confidence: float
    status: Literal["ACTIVE", "RESOLVED"]
    context_id: str | None = None
