from app.core.identifiers import LearnerId
"""Typed assessment boundary: targets in, question-level observations out.

Assessment/OCR implementations supply already graded observations. The learner
never generates questions, performs OCR, or delegates scoring to an LLM.
"""

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.learner.calibration import CalibrationRequest, calibration_targets
from app.learner.schemas import (
    EvidenceSubmissionRequest, LearnerSchema, StudyRecommendationsRequest, VerificationCandidatesRequest,
)


class ConceptGrade(LearnerSchema):
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    grade_confidence: float = Field(default=1, ge=0, le=1)
    difficulty: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode='after')
    def valid_score(self):
        if self.score > self.max_score:
            raise ValueError('Concept score cannot exceed its maximum')
        return self


class GradedQuestion(ConceptGrade):
    question_id: str = Field(min_length=1, max_length=100)
    concept_ids: list[str] = Field(min_length=1, max_length=20)
    difficulty: float = Field(ge=0, le=1)
    independence: float = Field(ge=0, le=1)
    hint_count: int = Field(default=0, ge=0)
    attempt_number: int = Field(default=1, ge=1)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    rubric: dict[str, Any] = Field(default_factory=dict)
    supersedes_evidence_ids: dict[str, str] = Field(default_factory=dict)
    item_id: str | None = Field(default=None, min_length=1, max_length=300)
    concept_grades: dict[str, ConceptGrade] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_concept_grades(self):
        ids = set(self.concept_ids)
        if len(ids) > 1 and set(self.concept_grades) != ids:
            raise ValueError('Multi-concept questions require a separate grade for every concept')
        if self.concept_grades and set(self.concept_grades) != ids:
            raise ValueError('Concept grades must match the tagged concepts exactly')
        if set(self.supersedes_evidence_ids) - ids:
            raise ValueError('Correction references must belong to the tagged concepts')
        return self


class AssessmentObservations(LearnerSchema):
    learner_id: LearnerId
    assessment_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)
    context_id: str = Field(min_length=1)
    source_type: Literal['QUIZ','MOCK_EXAM','HANDWRITTEN_ASSESSMENT','CALIBRATION','EXERCISE'] = 'QUIZ'
    occurred_at: datetime
    questions: list[GradedQuestion] = Field(min_length=1, max_length=100)


class LearnerAssessmentAdapter:
    def __init__(self, learner):
        self.learner = learner

    def targets(self, learner_id: str, context_ids=None, limit=5):
        return {'study': self.learner.get_study_recommendations(StudyRecommendationsRequest(
                    learner_id=learner_id, context_ids=context_ids, limit=limit)),
                'verification': self.learner.get_verification_candidates(VerificationCandidatesRequest(
                    learner_id=learner_id, context_ids=context_ids, limit=limit))}

    def calibration(self, request: CalibrationRequest):
        return calibration_targets(self.learner, request)

    def submit(self, request: AssessmentObservations):
        request = AssessmentObservations.model_validate(request.model_dump())
        observations = []
        seen_questions = set()
        for question in request.questions:
            if question.question_id in seen_questions:
                raise ValueError('Question IDs must be unique within an assessment revision')
            seen_questions.add(question.question_id)
            for concept_id in dict.fromkeys(question.concept_ids):
                grade = question.concept_grades.get(concept_id, question)
                result = 'CORRECT' if grade.score == grade.max_score else ('INCORRECT' if grade.score == 0 else 'PARTIAL')
                observations.append(EvidenceSubmissionRequest(
                    learner_id=request.learner_id, concept_id=concept_id, context_id=request.context_id,
                    source_type=request.source_type,
                    supersedes_evidence_id=question.supersedes_evidence_ids.get(concept_id),
                    source_id=json.dumps([request.assessment_id, question.question_id, request.revision,
                                          question.attempt_number], separators=(',', ':')),
                    item_id=question.item_id or json.dumps([request.assessment_id, question.question_id], separators=(',', ':')),
                    session_id=request.assessment_id, item_revision=request.revision,
                    result=result, score=grade.score, max_score=grade.max_score,
                    difficulty=grade.difficulty if grade.difficulty is not None else question.difficulty,
                    independence=question.independence,
                    hint_count=question.hint_count, attempt_number=question.attempt_number,
                    evidence_confidence=min(question.grade_confidence, grade.grade_confidence),
                    extraction_confidence=question.extraction_confidence, occurred_at=request.occurred_at,
                    metadata={'assessment_id': request.assessment_id, 'question_id': question.question_id,
                              'revision': request.revision, 'rubric': question.rubric},
                ))
        return self.learner.submit_evidence_batch(observations)
