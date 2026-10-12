from datetime import datetime
from typing import Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class GenerationRequest(Contract):
    client_request_id: UUID
    context_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=200)
    concept_names: list[str] = Field(default_factory=list, max_length=10)
    confirm_new_concepts: bool = False
    count: int = Field(default=5, ge=1, le=10)
    purpose: Literal['practice', 'verification', 'calibration'] = 'practice'
    question_format: Literal['written', 'mcq'] = 'written'
    grounded: bool = False
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    revision_draft_id: UUID | None = None
    revision_assessment_id: UUID | None = None
    revision_instructions: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def revision_target(self):
        targets = int(self.revision_draft_id is not None) + int(self.revision_assessment_id is not None)
        if targets > 1 or bool(targets) != bool(self.revision_instructions):
            raise ValueError('Revisions require exactly one source assessment and instructions.')
        return self

    def fingerprint_payload(self):
        # Preserve replay hashes for generation requests created before revisions
        # were supported. New optional defaults must not invalidate old retries.
        exclude = {'revision_draft_id','revision_assessment_id','revision_instructions'} if not self.revision_instructions else set()
        if self.question_format == 'written': exclude.add('question_format')
        return self.model_dump(mode='json', exclude=exclude)

from app.interactions.schemas import ChoiceOption as MCQOption

class GeneratedQuestion(Contract):
    prompt: str = Field(min_length=1, max_length=3000)
    concept_ids: list[str] = Field(min_length=1, max_length=5)
    difficulty: float = Field(ge=0, le=1)
    marks: float = Field(gt=0, le=20)
    options: list[MCQOption] = Field(default_factory=list, max_length=6)
    correct_option_id: str | None = None
    @model_validator(mode='after')
    def valid_options(self):
        if self.options:
            ids = [x.id for x in self.options]
            if len(ids) < 2 or len(set(ids)) != len(ids) or self.correct_option_id not in ids:
                raise ValueError('MCQs need unique options and a private correct option.')
        elif self.correct_option_id is not None: raise ValueError('Correct option requires options.')
        return self

    model_answer: str = Field(min_length=1, max_length=3000)
    rubric: str = Field(min_length=1, max_length=2000)
    source_tokens: list[str] = Field(default_factory=list, max_length=5)

class GeneratedAssessment(Contract):
    title: str = Field(min_length=1, max_length=200)
    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=10)


class AssessmentTargets(Contract):
    concept_names: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=1, max_length=5)

class ConceptGrade(Contract):
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    @model_validator(mode='after')
    def bounds(self):
        if self.score > self.max_score: raise ValueError('Score exceeds maximum.')
        return self

class QuestionGrade(Contract):
    question_id: str
    score: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    feedback: str = Field(min_length=1, max_length=2000)
    concept_grades: dict[str, ConceptGrade]
    misconceptions: list[str] = Field(default_factory=list, max_length=3)

class GradedAssessment(Contract):
    questions: list[QuestionGrade] = Field(min_length=1, max_length=10)

class PublicQuestionGrade(QuestionGrade):
    # Produced by the assessment domain after grading, never by the model.
    outcome: Literal['correct', 'partial', 'wrong'] | None = None
    correct_answer: str | None = None

class StartAttempt(Contract):
    client_request_id: UUID

class SaveDraftAnswers(Contract):
    expected_revision: int = Field(ge=1)
    answers: dict[str, str] = Field(max_length=10)

class SubmitAnswers(Contract):
    expected_revision: int = Field(ge=1)
    client_request_id: UUID
    answers: dict[str, str]
    transcription_confirmed: bool = False
    assistance: Literal['unknown', 'independent', 'assisted'] = 'unknown'

class PublicQuestion(Contract):
    options: list[MCQOption] = Field(default_factory=list)
    id: UUID
    prompt: str
    concept_ids: list[str]
    difficulty: float
    marks: float
    source_tokens: list[str]

class Assessment(Contract):
    id: UUID
    context_id: str
    title: str
    purpose: str
    revision: int
    created_at: datetime
    questions: list[PublicQuestion]
    sources: list[dict]

class Attempt(Contract):
    id: UUID
    assessment_id: UUID
    revision: int
    state: Literal['draft', 'pending_transcription', 'submitted', 'grading', 'graded', 'failed']
    attempt_number: int
    answers: dict[str, str]
    grades: list[PublicQuestionGrade] | None
    extraction: dict | None
    error: str | None
    evidence_status: Literal['pending', 'applied', 'partial', 'unavailable', 'none']
    created_at: datetime
    grade_revision: int = 1
    grade_history: list[dict] = Field(default_factory=list)
    assistance: Literal['unknown', 'independent', 'assisted'] = 'unknown'
    retry_pending: bool = False
