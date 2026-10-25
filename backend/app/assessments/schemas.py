from datetime import datetime
from enum import Enum
from typing import Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class AssessmentAssistance(str, Enum):
    unknown = 'unknown'
    independent = 'independent'
    assisted = 'assisted'


class AttemptScoring(Contract):
    raw_score: float = Field(ge=0)
    adjusted_score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    multiplier: float = Field(gt=0, le=1)
    reported_assistance: AssessmentAssistance
    policy: Literal['self-reported-assistance-v1']


QuestionFormat = str

class PlannedPart(Contract):
    path: list[str] = Field(default_factory=list)
    question_type: str = 'written'
    answer_mode: Literal['text', 'single_choice', 'multiple_choice'] = 'text'
    marks: float = Field(default=1, gt=0)
    brief: str = ''
    context: str = ''

class PlannedQuestion(Contract):
    number: int = Field(ge=1)
    context: str = ''
    parts: list[PlannedPart] = Field(min_length=1)

class PaperSection(Contract):
    title: str = Field(min_length=1, max_length=100)
    question_count: int = Field(default=0, ge=0)
    question_type: str = 'written'
    part_marks: list[float] = Field(default_factory=list)
    questions: list[PlannedQuestion] = Field(default_factory=list)
    instructions: str = ''

    @model_validator(mode='after')
    def marks_valid(self):
        if self.questions:
            self.question_count = len(self.questions)
        elif self.question_count < 1 or not self.part_marks:
            raise ValueError('Provide questions or a question count and part marks.')
        if any(mark <= 0 for mark in self.part_marks):
            raise ValueError('Each part must carry positive marks.')
        if not self.questions and self.question_type in ('mcq', 'true_false') and len(self.part_marks) != 1:
            raise ValueError('Objective questions have one answer.')
        return self

class PaperInfo(Contract):
    duration_minutes: int | None = Field(default=None, ge=1)
    total_marks: float = Field(gt=0)
    question_count: int = Field(ge=1)
    instructions: str = 'Answer all questions. Show your working where appropriate. Marks are shown for each part.'
    sections: list[PaperSection] = Field(min_length=1)

def limit_sections(sections, limit=20):
    remaining, result = limit, []
    for original in sections:
        if remaining <= 0: break
        section = original.model_copy(deep=True)
        if section.questions: section.questions = section.questions[:remaining]; section.question_count = len(section.questions)
        else: section.question_count = min(section.question_count, remaining)
        remaining -= section.question_count
        result.append(section)
    return result

class AssessmentDesign(Contract):
    title: str
    instructions: str = 'Answer all questions. Show your working where appropriate.'
    duration_minutes: int = Field(default=60, ge=1)
    sections: list[PaperSection] = Field(min_length=1)

class GenerationRequest(Contract):
    client_request_id: UUID
    context_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=200)
    concept_names: list[str] = Field(default_factory=list)
    concept_ids: list[UUID] = Field(default_factory=list, max_length=20)
    confirm_new_concepts: bool = False
    count: int | None = Field(default=5, ge=1)
    purpose: Literal['practice', 'verification', 'calibration'] = 'practice'
    question_format: QuestionFormat = 'written'
    question_formats: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list, max_length=12)
    duration_minutes: int | None = Field(default=None, ge=1)
    total_marks: float | None = Field(default=None, gt=0)
    paper_sections: list[PaperSection] = Field(default_factory=list)
    instructions: str = ''
    level: str | None = Field(default=None, max_length=200)
    result_style: Literal['marks', 'grade', 'feedback'] = 'marks'
    grounded: bool = False
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    revision_draft_id: UUID | None = None
    revision_assessment_id: UUID | None = None
    revision_instructions: str = ''

    @model_validator(mode='before')
    @classmethod
    def format_aliases(cls, value):
        if isinstance(value, dict) and isinstance(value.get('count'), int) and value['count'] > 20:
            value = dict(value, count=20)
        if isinstance(value, dict) and isinstance(value.get('question_format'), str):
            aliases = {'mock_exam':'mock_paper','exam_paper':'mock_paper','exam':'mock_paper','multiple_choice':'mcq',
                       'true/false':'true_false','true-false':'true_false','short_answers':'short_answer','multi_select':'multiple_select'}
            value = dict(value)
            value['question_format'] = aliases.get(value['question_format'].lower(), value['question_format'])
        return value

    @model_validator(mode='after')
    def revision_target(self):
        if self.concept_ids and not self.context_id:
            raise ValueError('Exact practice topics require a learning context.')
        if self.question_formats:
            aliases = {'multiple_choice':'mcq', 'multi_select':'multiple_select', 'true/false':'true_false', 'short_answers':'short_answer'}
            self.question_formats = list(dict.fromkeys(aliases.get(value.lower(), value.lower()) for value in self.question_formats))
            if any(value in ('auto', 'mixed', 'mock_paper') for value in self.question_formats):
                raise ValueError('Select concrete question types, or leave formats empty for automatic selection.')
            if self.count is not None and self.count < len(self.question_formats):
                raise ValueError('Choose at least one question per selected format.')
            self.question_format = self.question_formats[0] if len(self.question_formats) == 1 else 'mixed'
        targets = int(self.revision_draft_id is not None) + int(self.revision_assessment_id is not None)
        if targets and self.concept_ids:
            raise ValueError('Revisions retain their original concepts; exact practice targets require a new assessment.')
        if targets > 1 or bool(targets) != bool(self.revision_instructions):
            raise ValueError('Revisions require exactly one source assessment and instructions.')
        if sum(section.question_count for section in self.paper_sections) > 20:
            self.paper_sections = limit_sections(self.paper_sections)
            if self.total_marks is not None:
                self.total_marks = sum(sum(part.marks for question in section.questions for part in question.parts)
                    if section.questions else section.question_count*sum(section.part_marks) for section in self.paper_sections)
        if self.paper_sections and self.count is not None and sum(section.question_count for section in self.paper_sections) != self.count:
            raise ValueError('Section question counts must equal the requested count.')
        return self

    def fingerprint_payload(self):
        # Preserve replay hashes for generation requests created before revisions
        # were supported. New optional defaults must not invalidate old retries.
        exclude = {'revision_draft_id','revision_assessment_id','revision_instructions'} if not self.revision_instructions else set()
        if not self.question_formats: exclude.add('question_formats')
        if not self.concept_ids: exclude.add('concept_ids')
        if self.question_format == 'written': exclude.add('question_format')
        if not self.paper_sections: exclude.add('paper_sections')
        if self.total_marks is None: exclude.add('total_marks')
        if self.duration_minutes is None or self.question_format != 'mock_paper': exclude.add('duration_minutes')
        if not self.instructions: exclude.add('instructions')
        if self.level is None: exclude.add('level')
        # Omitted style remains replay-compatible with pre-automation requests.
        if self.result_style in ('marks', None): exclude.add('result_style')
        return self.model_dump(mode='json', exclude=exclude)

class AssessmentIntent(GenerationRequest):
    """A user can ask for an assessment without completing a configuration form."""
    context_id: str | None = Field(default=None, min_length=1, max_length=100)
    topic: str | None = Field(default=None, min_length=1, max_length=200)
    count: int | None = Field(default=None, ge=1)
    question_format: str = 'auto'
    result_style: Literal['marks', 'grade', 'feedback'] | None = None

    @model_validator(mode='before')
    @classmethod
    def optional_blanks(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            for key in ('context_id','topic','level'):
                if isinstance(value.get(key), str) and not value[key].strip(): value[key] = None
        return value

class AssessmentSelection(Contract):
    topic: str = Field(min_length=1, max_length=200)
    context_id: str | None = None
    question_format: str = 'mixed'
    level: str | None = Field(default=None, max_length=200)
    result_style: Literal['marks', 'grade', 'feedback'] = 'marks'
    concept_names: list[str] = Field(default_factory=list)

class AssessmentPreferences(Contract):
    level: str | None = None
    result_style: Literal['marks', 'grade', 'feedback'] = 'marks'

class MCQOption(Contract):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1)

class GeneratedQuestion(Contract):
    question_type: str | None = None
    answer_mode: Literal['text', 'single_choice', 'multiple_choice'] | None = None
    context: str = ''
    concept_names: list[str] = Field(default_factory=list)
    section: str | None = Field(default=None, max_length=100)
    number: int | None = Field(default=None, ge=1)
    part: str | None = None
    prompt: str = Field(min_length=1)
    concept_ids: list[str] = Field(default_factory=list)
    difficulty: float = Field(ge=0, le=1)
    marks: float = Field(gt=0)
    options: list[MCQOption] = Field(default_factory=list)
    correct_option_id: str | None = None
    correct_option_ids: list[str] = Field(default_factory=list)
    @model_validator(mode='after')
    def valid_options(self):
        if self.options:
            ids = [x.id for x in self.options]
            correct = self.correct_option_ids or ([self.correct_option_id] if self.correct_option_id else [])
            if len(ids) < 2 or len(set(ids)) != len(ids) or not correct or set(correct) - set(ids):
                raise ValueError('MCQs need unique options and a private correct option.')
            self.answer_mode = 'multiple_choice' if self.correct_option_ids else 'single_choice'
        elif self.correct_option_id is not None or self.correct_option_ids: raise ValueError('Correct option requires options.')
        else: self.answer_mode = 'text'
        return self

    model_answer: str = Field(min_length=1)
    rubric: str = Field(min_length=1)
    source_tokens: list[str] = Field(default_factory=list, max_length=5)

class GeneratedAssessmentBatch(Contract):
    """Internal content output; validated paper structure stays server-owned."""
    title: str = Field(min_length=1, max_length=200)
    questions: list[GeneratedQuestion] = Field(min_length=1)


class GeneratedAssessment(GeneratedAssessmentBatch):
    paper: PaperInfo | None = None


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
    concept_grades: dict[str, ConceptGrade] = Field(default_factory=dict)
    misconceptions: list[str] = Field(default_factory=list, max_length=3)

class GradedAssessment(Contract):
    questions: list[QuestionGrade] = Field(min_length=1)

class PublicQuestionGrade(QuestionGrade):
    # Produced by the assessment domain after grading, never by the model.
    outcome: Literal['correct', 'partial', 'wrong'] | None = None
    correct_answer: str | None = None

class StartAttempt(Contract):
    client_request_id: UUID

class MistakePracticeRequest(Contract):
    client_request_id: UUID
    expected_grade_revision: int = Field(ge=1)
    question_ids: list[UUID] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def unique_questions(self):
        if len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError('Choose each question once.')
        return self

class RevisionPracticeRequest(Contract):
    context_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=200)
    client_request_id: UUID
    assessment_ids: list[UUID] = Field(default_factory=list, max_length=200)
    topic_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=200)
    count: int = Field(default=5, ge=1, le=20)

class RetryGrading(Contract):
    client_request_id: UUID
    expected_revision: int = Field(ge=1)

class SaveDraftAnswers(Contract):
    expected_revision: int = Field(ge=1)
    answers: dict[str, str]
    assistance: AssessmentAssistance | None = None

class SubmitAnswers(Contract):
    expected_revision: int = Field(ge=1)
    client_request_id: UUID
    answers: dict[str, str]
    transcription_confirmed: bool = False
    assistance: AssessmentAssistance = AssessmentAssistance.unknown

class PublicQuestion(Contract):
    question_type: str | None = None
    answer_mode: Literal['text', 'single_choice', 'multiple_choice'] | None = None
    context: str = ''
    section: str | None = None
    number: int | None = None
    part: str | None = None
    options: list[MCQOption] = Field(default_factory=list)
    id: UUID
    prompt: str
    concept_ids: list[str]
    difficulty: float
    marks: float
    source_tokens: list[str]

class PracticeSource(Contract):
    assessment_id: UUID
    attempt_id: UUID
    grade_revision: int = Field(ge=1)
    known_exposure: Literal[True] = True
    instructions: str = ''
    reference_questions: list[PublicQuestion] = Field(default_factory=list)

class AttemptSummary(Contract):
    count: int = 0
    latest_state: str | None = None
    graded_attempt_id: UUID | None = None
    graded_attempt_number: int = 0
    correct: int = 0
    incorrect: int = 0
    partial: int = 0

class Assessment(Contract):
    attempt_summary: AttemptSummary | None = None
    tags: list[str] = Field(default_factory=list)
    source_assessment_ids: list[UUID] = Field(default_factory=list)
    practice_source: PracticeSource | None = None
    preferences: AssessmentPreferences = Field(default_factory=AssessmentPreferences)
    paper: PaperInfo | None = None
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
    assistance: AssessmentAssistance = AssessmentAssistance.unknown
    reported_assistance: AssessmentAssistance = AssessmentAssistance.unknown
    scoring: AttemptScoring | None = None
    retry_pending: bool = False
