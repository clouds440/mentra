"""Database-agnostic repository interfaces for learner domain objects."""

from contextlib import AbstractContextManager
from typing import Any, Protocol

from app.learner.models import (
    Concept,
    LearnerConceptState,
    LearningContext,
    LearningEvidence,
    Misconception,
)


class ConceptRepository(Protocol):
    def get_concept(self, concept_id: str) -> Concept | None: ...

    def get_concept_by_normalized_name(self, normalized_name: str) -> Concept | None: ...

    def find_by_normalized_alias(self, normalized_alias: str, min_confidence: float = 0.9) -> list[Concept]: ...

    def list_concepts(self, limit: int) -> list[Concept]: ...

    def search_concepts(self, normalized_query: str, limit: int) -> list[Concept]: ...

    def create_concept(self, concept: Concept) -> None: ...

    def add_alias(
        self,
        concept_id: str,
        alias: str,
        normalized_alias: str,
        source: str,
        confidence: float,
    ) -> None: ...

    def add_relation(
        self,
        source_concept_id: str,
        target_concept_id: str,
        relation_type: str,
        confidence: float,
    ) -> None: ...

    def list_related_concepts(
        self,
        concept_id: str,
        relation_type: str | None = None,
        limit: int = 20,
        min_confidence: float = 0,
    ) -> list[Concept]: ...


class LearningContextRepository(Protocol):
    def transaction(self, *, learner_ids: tuple[str, ...] | list[str] = (), ontology: bool = False) -> AbstractContextManager["LearningContextRepository"]: ...

    def get_context(self, learner_id: str, context_id: str) -> LearningContext | None: ...

    def find_context(
        self,
        learner_id: str,
        normalized_name: str,
    ) -> LearningContext | None: ...

    def list_for_learner(self, learner_id: str) -> list[LearningContext]: ...

    def save_context(self, context: LearningContext) -> None: ...


class EvidenceRepository(Protocol):
    def append_evidence(self, evidence: LearningEvidence) -> None: ...

    def find_evidence_by_source(
        self,
        learner_id: str,
        source_type: str,
        source_id: str,
        concept_id: str,
    ) -> LearningEvidence | None: ...

    def list_evidence(self, learner_id: str, concept_id: str) -> list[LearningEvidence]: ...


class LearnerStateRepository(Protocol):
    def get_state(
        self,
        learner_id: str,
        concept_id: str,
    ) -> LearnerConceptState | None: ...

    def save_state(self, state: LearnerConceptState) -> None: ...

    def list_states(self, learner_id: str) -> list[LearnerConceptState]: ...


class LearnerRepository(
    ConceptRepository,
    LearningContextRepository,
    EvidenceRepository,
    LearnerStateRepository,
    Protocol,
):
    """Combined persistence port required by the learner application service."""

    def transaction(self, *, learner_ids: tuple[str, ...] | list[str] = (),
                    ontology: bool = False) -> AbstractContextManager["LearnerRepository"]: ...

    def lock_learners(self, learner_ids: tuple[str, ...] | list[str]) -> None: ...

    def canonical_id(self, concept_id: str) -> str: ...

    def get_candidate(self, candidate_id: str, *, learner_id: str | None) -> dict[str, Any] | None: ...

    def get_candidate_for_review(self, candidate_id: str) -> dict[str, Any] | None: ...

    def copy_parent_contexts(self, parent_id: str, child_id: str) -> None: ...

    def resolve_candidate(self, candidate_id: str, resolution_status: str,
                          concept_id: str | None = None) -> None: ...

    def save_decision(self, evidence_id: str, status: str, reason: str, learner_id: str) -> None: ...

    def get_decision(self, evidence_id: str, learner_id: str) -> dict[str, Any] | None: ...

    def get_evidence(self, evidence_id: str, learner_id: str) -> LearningEvidence | None: ...

    def confirm_decision(self, evidence_id: str, source: str, learner_id: str) -> None: ...

    def supersede_decision(self, evidence_id: str, learner_id: str) -> None: ...

    def accepted_evidence(self, learner_id: str, concept_id: str) -> list[LearningEvidence]: ...

    def find_canonical_evidence_by_source(self, learner_id: str, source_type: str,
                                         source_id: str, concept_id: str) -> LearningEvidence | None: ...

    def context_concepts(self, learner_id: str, context_ids: list[str],
                         query_terms: list[str] | tuple[str, ...] = (), limit: int | None = None,
                         normalized_query: str = '') -> list[Concept]: ...

    def states_for_concepts(self, learner_id: str, concept_ids: list[str]) -> dict[str, LearnerConceptState]: ...

    def misconceptions_for_concepts(self, learner_id: str, concept_ids: list[str]) -> dict[str, list[str]]: ...

    def prerequisite_counts(self, concept_ids: list[str], context_ids: list[str] | None = None,
                            learner_id: str | None = None) -> dict[str, int]: ...

    def context_factors(self, learner_id: str, contexts: list[LearningContext]) -> dict[str, dict[str, float]]: ...

    def set_context_goal(self, context_id: str, concept_id: str, importance: float, target_difficulty: float, *, learner_id: str) -> None: ...

    def latest_item_evidence(self, learner_id: str, concept_id: str, item_id: str,
                             source_type: str | None = None, attempt_number: int | None = None,
                             session_id: str | None = None) -> LearningEvidence | None: ...

    def context_relevance(self, learner_id: str, context_ids: list[str]) -> dict[str, float]: ...

    def context_ids_for_terms(self, learner_id: str, terms: list[str]) -> set[str]: ...

    def canonical_concepts(self, concept_ids: list[str]) -> dict[str, Concept]: ...

    def audit(self, action: str, details: dict[str, Any], learner_id: str | None = None,
              concept_id: str | None = None) -> None: ...

    def list_audit(self, learner_id: str, concept_id: str, limit: int = 50) -> list[dict[str, Any]]: ...

    def merge_identity(self, source_id: str, target_id: str) -> list[str]: ...

    def resolve_misconception(self, learner_id: str, misconception_id: str) -> bool: ...

    def add_context_concept(self, context_id: str, concept_id: str, *, learner_id: str) -> None: ...

    def get_concept_context_ids(self, concept_id: str, *, learner_id: str) -> list[str]: ...

    def list_misconceptions(
        self,
        learner_id: str,
        concept_id: str,
    ) -> list[Misconception]: ...

    def save_misconception(self, misconception: Misconception) -> str: ...

    def save_candidate(
        self,
        candidate_id: str,
        proposed_name: str,
        normalized_name: str,
        context_id: str | None,
        metadata: dict[str, Any],
        *, learner_id: str | None,
    ) -> str: ...

    def list_candidates(self, limit: int = 100) -> list[dict[str, Any]]: ...
