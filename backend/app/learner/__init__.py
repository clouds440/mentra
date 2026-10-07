"""Public, provider-independent contracts for the Mentra Learner Engine."""

from app.learner.exceptions import (
    ConceptNotFoundError,
    InvalidEvidenceError,
    LearnerError,
    LearningContextNotFoundError,
)
from app.learner.schemas import (
    ActivateLearningContextRequest,
    ActiveContextsRequest,
    ActiveContextsResponse,
    ConceptResolution,
    ConceptResolutionRequest,
    ConceptStateRequest,
    ConceptStateResponse,
    EvidenceSubmissionRequest,
    EvidenceSubmissionResult,
    LearnerContextConcept,
    LearnerContextPacket,
    LearnerContextRequest,
    LearningContextSummary,
    StudyRecommendation,
    StudyRecommendationsRequest,
    VerificationCandidate,
    VerificationCandidatesRequest,
)
from app.learner.services import LearnerService

__all__ = [
    "ActivateLearningContextRequest",
    "ActiveContextsRequest",
    "ActiveContextsResponse",
    "ConceptNotFoundError",
    "ConceptResolution",
    "ConceptResolutionRequest",
    "ConceptStateRequest",
    "ConceptStateResponse",
    "EvidenceSubmissionRequest",
    "EvidenceSubmissionResult",
    "InvalidEvidenceError",
    "LearnerContextConcept",
    "LearnerContextPacket",
    "LearnerContextRequest",
    "LearnerError",
    "LearnerService",
    "LearningContextNotFoundError",
    "LearningContextSummary",
    "StudyRecommendation",
    "StudyRecommendationsRequest",
    "VerificationCandidate",
    "VerificationCandidatesRequest",
]

from app.learner.engine import LearnerEngine
from app.learner.schemas import (ResolveLearningContextRequest, ContextActivityRequest, ContextTransitionRequest,
                                ConfirmEvidenceRequest, LearningGoalRequest, PerformancePredictionRequest, PerformancePrediction,
                                PerformanceEstimate)

__all__ += ["LearnerEngine", "ResolveLearningContextRequest", "ContextActivityRequest", "ContextTransitionRequest", "ConfirmEvidenceRequest"]
__all__ += ["LearningGoalRequest", "PerformancePredictionRequest", "PerformancePrediction", "PerformanceEstimate"]
