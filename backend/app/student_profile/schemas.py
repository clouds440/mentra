"""High-level teaching context. These contracts never describe concept mastery."""
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.core.identifiers import LearnerId


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)


class EducationLevel(str, Enum):
    PRIMARY = 'primary'
    MIDDLE = 'middle_school'
    HIGH = 'high_school'
    COLLEGE = 'college'
    UNDERGRADUATE = 'undergraduate'
    GRADUATE = 'graduate'
    OTHER = 'other'


class ProfileDetails(Contract):
    """Only the learner may write these fields; never an evaluator or interaction."""
    education_level: EducationLevel
    field_of_study: str = Field(min_length=1, max_length=120)
    learning_goal: str = Field(min_length=5, max_length=500)
    learning_preference: Literal['balanced', 'concise', 'examples_first', 'step_by_step', 'conceptual']
    explanation_depth: Literal['brief', 'standard', 'deep']

    @field_validator('field_of_study', 'learning_goal', mode='before')
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


Dimension = Literal['overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity']
DIMENSIONS = ('overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity')


class Estimate(Contract):
    value: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    effective_weight: float = Field(default=0, ge=0)
    successful_weight: float = Field(default=0, ge=0)
    last_evidence_at: datetime | None = None
    rationale: str | None = Field(default=None, max_length=240)


class Estimates(Contract):
    overall_proficiency: Estimate = Field(default_factory=Estimate)
    reasoning: Estimate = Field(default_factory=Estimate)
    quantitative: Estimate = Field(default_factory=Estimate)
    comprehension: Estimate = Field(default_factory=Estimate)
    domain_familiarity: Estimate = Field(default_factory=Estimate)


class StudentProfile(Contract):
    learner_id: LearnerId
    details: ProfileDetails | None = None
    details_source: str | None = Field(default=None, min_length=1, max_length=64)
    estimates: Estimates = Field(default_factory=Estimates)
    onboarding_phase: Literal['information', 'calibration', 'complete'] = 'information'
    calibration_status: Literal['not_started', 'in_progress', 'skipped', 'completed'] = 'not_started'
    evaluation_status: Literal['not_started', 'pending', 'evaluating', 'applied', 'failed', 'superseded'] = 'not_started'
    version: int = Field(default=1, ge=1)
    context_version: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(Contract):
    expected_version: int = Field(ge=1)
    details: ProfileDetails


class VersionRequest(Contract):
    expected_version: int = Field(ge=1)


class AnswerRequest(VersionRequest):
    question_id: str = Field(min_length=1, max_length=80)
    option_id: str = Field(min_length=1, max_length=16)


class Option(Contract):
    id: str
    text: str


class PublicQuestion(Contract):
    id: str
    prompt: str
    kind: Literal['mcq', 'true_false', 'selection'] = 'mcq'
    options: list[Option]


class Question(PublicQuestion):
    dimension: Dimension
    difficulty: float = Field(ge=0, le=1)
    correct_option_id: str


class CalibrationAttempt(Contract):
    id: LearnerId
    learner_id: LearnerId
    blueprint_version: str
    context_version: int
    details_snapshot: ProfileDetails
    questions: list[Question]
    answers: dict[str, str] = Field(default_factory=dict)
    status: Literal['in_progress', 'completed', 'skipped', 'superseded'] = 'in_progress'
    version: int = Field(default=1, ge=1)
    created_at: datetime
    completed_at: datetime | None = None


class CalibrationView(Contract):
    id: LearnerId
    blueprint_version: str
    questions: list[PublicQuestion]
    answers: dict[str, str]
    status: Literal['in_progress', 'completed', 'skipped', 'superseded']
    version: int


class EvidenceItem(Contract):
    """Deterministic results produced by a trusted assessment/interaction adapter."""
    id: str = Field(min_length=1, max_length=80)
    dimension: Dimension
    correct: bool
    difficulty: float | None = Field(default=None, ge=0, le=1)
    prompt: str | None = Field(default=None, max_length=2000)
    selected_option: str | None = Field(default=None, max_length=500)


class EvidenceInput(Contract):
    source_type: Literal['onboarding_calibration', 'assessment', 'interaction']
    source_id: str = Field(min_length=1, max_length=160)
    occurred_at: datetime
    items: list[EvidenceItem] = Field(min_length=1, max_length=32)
    reliability: float = Field(default=1, gt=0, le=1)

    @field_validator('occurred_at')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Evidence time must include a timezone')
        return value

    @field_validator('items')
    @classmethod
    def unique_items(cls, items):
        if len({item.id for item in items}) != len(items):
            raise ValueError('Evidence item IDs must be unique')
        return items


class Candidate(Contract):
    value: float | None = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(max_length=32)
    rationale: str = Field(max_length=240)

    @model_validator(mode='after')
    def unknown_requires_zero_confidence(self):
        if (self.value is None) != (self.confidence == 0):
            raise ValueError('Unknown estimates require a null value and zero confidence; an estimate needs positive confidence')
        return self


class AIEvaluation(Contract):
    """Exact structured AI output; factual/profile preference fields are forbidden."""
    overall_proficiency: Candidate
    reasoning: Candidate
    quantitative: Candidate
    comprehension: Candidate
    domain_familiarity: Candidate


class ProfileEvidence(Contract):
    id: LearnerId
    learner_id: LearnerId
    context_version: int
    calibration_attempt_id: LearnerId | None = None
    details_snapshot: ProfileDetails
    input: EvidenceInput
    status: Literal['pending', 'evaluating', 'applied', 'failed', 'superseded'] = 'pending'
    evaluation_token: str | None = None
    claimed_at: datetime | None = None
    evaluation: AIEvaluation | None = None
    policy_version: str | None = None
    applied_estimates: Estimates | None = None
    created_at: datetime


class CalibrationResult(Contract):
    profile: StudentProfile
    evidence_id: LearnerId


class ProfileContext(Contract):
    """Small bounded packet for future prompts, supplied as data, not instructions."""
    details: ProfileDetails
    estimates: dict[Dimension, dict[str, float | None]]
    estimate_scope: str = 'Provisional, relative to the stated education level; not IQ or concept mastery.'
