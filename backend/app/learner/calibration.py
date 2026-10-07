from app.core.identifiers import LearnerId
"""Initial assessment targets, without treating self-report as demonstrated mastery."""

from pydantic import Field

from app.learner.schemas import LearnerSchema, VerificationCandidatesRequest


class CalibrationRequest(LearnerSchema):
    learner_id: LearnerId
    context_id: str = Field(min_length=1)
    question_count: int = Field(default=4, ge=3, le=5)
    self_reported_level: float | None = Field(default=None, ge=0, le=1)


class CalibrationTarget(LearnerSchema):
    concept_id: str
    name: str
    difficulty: float = Field(ge=0, le=1)
    reason: str


def calibration_targets(learner, request: CalibrationRequest) -> list[CalibrationTarget]:
    candidates = learner.get_verification_candidates(VerificationCandidatesRequest(
        learner_id=request.learner_id, context_ids=[request.context_id], limit=request.question_count,
    ))
    start = 0.2 + 0.4 * (request.self_reported_level if request.self_reported_level is not None else 0.25)
    targets = []
    if candidates:
        for index in range(request.question_count):
            concept = candidates[index % len(candidates)]
            targets.append(CalibrationTarget(concept_id=concept.concept_id, name=concept.name,
                           difficulty=min(0.9, start + 0.1 * index), reason=concept.reason))
    return targets
