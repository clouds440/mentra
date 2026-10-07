"""Public service boundary consumed by API, LangChain, and other modules."""

from typing import Protocol

from app.learner.models import Concept, LearnerConceptState, Misconception, LearningEvidence

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
    LearnerContextPacket,
    LearnerContextRequest,
    LearningContextSummary,
    StudyRecommendation,
    StudyRecommendationsRequest,
    VerificationCandidate,
    VerificationCandidatesRequest,
    ResolveLearningContextRequest,
    ContextActivityRequest,
    ContextTransitionRequest,
    ConfirmEvidenceRequest,
    LearningGoalRequest, PerformancePredictionRequest, PerformancePrediction,
)


class LearnerService(Protocol):
    """Injectable facade for all supported Learner Engine operations.

    Implementations own policy and persistence. Consumers should depend on
    this interface and its schemas, never on learner tables or repositories.
    """

    def resolve_concept(
        self,
        request: ConceptResolutionRequest,
    ) -> ConceptResolution: ...

    def submit_evidence(
        self,
        request: EvidenceSubmissionRequest,
    ) -> EvidenceSubmissionResult: ...

    def get_concept_state(
        self,
        request: ConceptStateRequest,
    ) -> ConceptStateResponse | None: ...

    def get_relevant_context(
        self,
        request: LearnerContextRequest,
    ) -> LearnerContextPacket: ...

    def get_study_recommendations(
        self,
        request: StudyRecommendationsRequest,
    ) -> list[StudyRecommendation]: ...

    def get_verification_candidates(
        self,
        request: VerificationCandidatesRequest,
    ) -> list[VerificationCandidate]: ...

    def activate_learning_context(
        self,
        request: ActivateLearningContextRequest,
    ) -> LearningContextSummary: ...

    def get_active_contexts(
        self,
        request: ActiveContextsRequest,
    ) -> ActiveContextsResponse: ...

    def get_concept(self, concept_id: str) -> Concept: ...

    def get_related_concepts(self, concept_id: str, relation_type: str | None = None,
                             limit: int = 20) -> list[Concept]: ...

    def resolve_learning_context(self, request: ResolveLearningContextRequest) -> LearningContextSummary: ...

    def record_context_activity(self, request: ContextActivityRequest) -> LearningContextSummary: ...

    def transition_context_state(self, request: ContextTransitionRequest) -> LearningContextSummary: ...

    def get_related_contexts(self, learner_id: str, query: str) -> list[LearningContextSummary]: ...

    def get_concept_states(self, learner_id: str, concept_ids: list[str]) -> list[ConceptStateResponse | None]: ...

    def set_learning_goal(self, request: LearningGoalRequest) -> None: ...

    def predict_performance(self, request: PerformancePredictionRequest) -> PerformancePrediction: ...

    def find_latest_item_evidence(self, learner_id: str, concept_id: str, item_id: str) -> LearningEvidence | None: ...

    def submit_evidence_batch(self, requests: list[EvidenceSubmissionRequest]) -> list[EvidenceSubmissionResult]: ...

    def confirm_evidence(self, request: ConfirmEvidenceRequest) -> EvidenceSubmissionResult: ...

    def register_concept(self, name: str, description: str | None = None,
                          aliases: tuple[str, ...] = ()) -> Concept: ...

    def link_context_concept(self, learner_id: str, context_id: str, concept_id: str) -> None: ...

    def add_concept_relation(self, source_id: str, target_id: str,
                             relation_type: str, confidence: float = 1.0) -> None: ...

    def review_candidate(self, candidate_id: str, concept_id: str | None = None,
                          *, discard: bool = False) -> Concept | None: ...

    def record_misconception(self, learner_id: str, concept_id: str, description: str,
                             confidence: float, context_id: str | None = None) -> Misconception: ...

    def resolve_misconception(self, learner_id: str, misconception_id: str) -> bool: ...

    def recompute_learner_state(self, learner_id: str, concept_id: str) -> LearnerConceptState | None: ...

    def merge_concepts(self, source_id: str, target_id: str) -> Concept: ...

    def split_concept(self, parent_id: str, children: list[str]) -> list[Concept]: ...

    def explain_state(self, learner_id: str, concept_id: str) -> dict: ...
