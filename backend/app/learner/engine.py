"""Concrete provider-independent facade. LangGraph nodes can inject this service."""

from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import datetime, timezone
from uuid import uuid4

from app.learner.concepts import ConceptService
from app.learner.contexts import ContextService, summary
from app.learner.evidence import EvidenceService
from app.learner.exceptions import LearnerError, ConceptNotFoundError
from app.learner.models import Concept, Misconception, LearnerConceptState, LearningEvidence
from app.learner.repositories.protocols import LearnerRepository
from app.learner.concepts import SemanticResolver
from app.learner.normalization import lookup_forms
from app.learner.ranking import WeightedRankingPolicy, RankingPolicy
from app.learner.retrieval import RetrievalService
from app.learner.state import StateService
from app.learner.scoring import ExponentialRetentionPolicy, HeuristicMasteryPolicy, MasteryPolicy, RetentionPolicy
from app.learner.schemas import (
    ActiveContextsResponse, ConceptStateResponse, ActiveContextsRequest,
    ConceptResolutionRequest, ConceptResolution, ConceptStateRequest,
    LearnerContextRequest, LearnerContextPacket, StudyRecommendationsRequest, StudyRecommendation,
    VerificationCandidatesRequest, VerificationCandidate, ActivateLearningContextRequest,
    LearningContextSummary, ResolveLearningContextRequest, ContextActivityRequest,
    ContextTransitionRequest, EvidenceSubmissionRequest, EvidenceSubmissionResult, ConfirmEvidenceRequest,
    LearningGoalRequest, PerformancePredictionRequest, PerformancePrediction,
)


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'get_relevant_context': {'input': lambda args: dict(max_concepts=args['request'].max_concepts),
                            'result': lambda value: dict(concept_count=len(value.concepts), context_count=len(value.context_ids))},
})
class LearnerEngine:
    def __init__(self, repository: LearnerRepository, *, mastery_policy: MasteryPolicy | None = None,
                 retention_policy: RetentionPolicy | None = None, ranking_policy: RankingPolicy | None = None,
                 semantic_resolver: SemanticResolver | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.mastery_policy = mastery_policy or HeuristicMasteryPolicy()
        self.retention_policy = retention_policy or ExponentialRetentionPolicy()
        self.concepts = ConceptService(repository, semantic_resolver)
        self.contexts = ContextService(repository, self.clock)
        self.evidence = EvidenceService(repository, self.contexts, self.mastery_policy,
                                        self.retention_policy, self.clock)
        self.states = StateService(repository, self.evidence, self.mastery_policy, self.retention_policy, self.clock)
        self.retrieval = RetrievalService(repository, self.contexts, self.retention_policy,
                                          ranking_policy or WeightedRankingPolicy(), self.clock, self.states)

    def register_concept(self, name: str, description: str | None = None, aliases: tuple[str, ...] = ()) -> Concept:
        """Trusted registry operation, never exposed as an unrestricted LLM tool."""
        return self.concepts.register(name, description, aliases)

    def resolve_concept(self, request: ConceptResolutionRequest) -> ConceptResolution:
        return self.concepts.resolve(request)

    def get_concept(self, concept_id: str) -> Concept:
        return self.concepts.get(concept_id)

    def get_related_concepts(self, concept_id: str, relation_type: str | None = None, limit: int = 20) -> list[Concept]:
        return self.repository.list_related_concepts(self.get_concept(concept_id).id, relation_type, min(50, limit))

    def add_concept_relation(self, source_id: str, target_id: str, relation_type: str, confidence: float = 1.0) -> None:
        with self.repository.transaction(ontology=True) as repository:
            source_id, target_id = repository.canonical_id(source_id), repository.canonical_id(target_id)
            if (source_id == target_id or relation_type not in ('PARENT_OF', 'PREREQUISITE_OF', 'RELATED_TO')
                    or not 0 <= confidence <= 1 or not repository.get_concept(source_id) or not repository.get_concept(target_id)):
                raise LearnerError('Invalid concept relation')
            repository.add_relation(source_id, target_id, relation_type, confidence)

    def link_context_concept(self, learner_id: str, context_id: str, concept_id: str) -> None:
        with self.repository.transaction(learner_ids=[learner_id]) as repository:
            self.contexts.require(learner_id, context_id, repository)
            canonical_id = repository.canonical_id(concept_id)
            if repository.get_concept(canonical_id) is None:
                raise LearnerError('Canonical concept not found')
            repository.add_context_concept(context_id, canonical_id, learner_id=learner_id)

    def set_learning_goal(self, request: LearningGoalRequest) -> None:
        with self.repository.transaction(learner_ids=[request.learner_id]) as repository:
            self.contexts.require(request.learner_id, request.context_id, repository)
            concept_id = repository.canonical_id(request.concept_id)
            if not repository.get_concept(concept_id):
                raise ConceptNotFoundError(request.concept_id)
            repository.set_context_goal(request.context_id, concept_id, request.importance, request.target_difficulty, learner_id=request.learner_id)
            repository.audit('learning_goal', request.model_dump(), request.learner_id, concept_id)

    def review_candidate(self, candidate_id: str, concept_id: str | None = None, *, discard: bool = False) -> Concept | None:
        return self.concepts.resolve_candidate(candidate_id, concept_id, discard=discard)

    def get_pending_concepts(self, learner_id):
        return [dict(id=row['id'], label=row['proposed_name'], context_id=row['context_id'])
                for row in self.repository.list_owned_candidates(learner_id)]

    def review_owned_candidate(self, learner_id, candidate_id, *, discard=False):
        candidate = self.repository.get_candidate(candidate_id, learner_id=learner_id)
        if not candidate:
            from app.core.exceptions import AppError
            raise AppError('CONCEPT_CANDIDATE_NOT_FOUND', 'Concept candidate unavailable.', 404)
        if candidate['context_id']:
            self.contexts.require(learner_id, candidate['context_id'])
        if candidate['resolution_status'] != 'UNRESOLVED':
            if discard and candidate['resolution_status'] == 'DISCARDED': return None
            if not discard and candidate['resolution_status'] in ('PROMOTED','MERGED'):
                return self.get_concept(candidate['resolved_concept_id'])
            from app.core.exceptions import AppError
            raise AppError('CONCEPT_REVIEW_CONFLICT', 'This concept was already reviewed differently.', 409)
        return self.review_candidate(candidate_id, discard=discard)

    def resolve_learning_context(self, request: ResolveLearningContextRequest) -> LearningContextSummary:
        return self.contexts.resolve(request)

    def activate_learning_context(self, request: ActivateLearningContextRequest) -> LearningContextSummary:
        return self.contexts.activate(request)

    def record_context_activity(self, request: ContextActivityRequest) -> LearningContextSummary:
        return self.contexts.record_activity(request)

    def transition_context_state(self, request: ContextTransitionRequest) -> LearningContextSummary:
        return self.contexts.transition(request)

    def get_active_contexts(self, request: ActiveContextsRequest) -> ActiveContextsResponse:
        contexts = self.contexts.select(request.learner_id, include_related=False)
        return ActiveContextsResponse(contexts=[summary(c) for c in contexts])

    def get_context_summaries(self, learner_id: str, context_ids: list[str] | None = None) -> list[LearningContextSummary]:
        """Read canonical owned contexts without resolving or activating them."""
        if context_ids is not None:
            return [summary(self.contexts.require(learner_id, key)) for key in dict.fromkeys(context_ids)]
        return [summary(c) for c in self.repository.list_for_learner(learner_id)]

    def get_related_contexts(self, learner_id: str, query: str) -> list[LearningContextSummary]:
        return [summary(c) for c in self.contexts.select(learner_id, query=query) if c.status != 'ACTIVE']

    def submit_evidence(self, request: EvidenceSubmissionRequest) -> EvidenceSubmissionResult:
        return self.evidence.submit(request)

    def submit_evidence_batch(self, requests: list[EvidenceSubmissionRequest]) -> list[EvidenceSubmissionResult]:
        if not 1 <= len(requests) <= 2000:
            raise LearnerError('Evidence batches must contain between 1 and 2000 observations')
        with self.repository.transaction(learner_ids=sorted({r.learner_id for r in requests})) as repository:
            return [self.evidence.submit(request, repository) for request in requests]

    def confirm_evidence(self, request: ConfirmEvidenceRequest) -> EvidenceSubmissionResult:
        """Trusted confirmed-transcription path; no agent tool exposes this method."""
        return self.evidence.confirm(request)

    def submit_evidence_batch_in_transaction(self, requests, unit_of_work, *, transcription_confirmation=None):
        """Trusted composed persistence boundary; never exposed as an AI tool."""
        if not 1 <= len(requests) <= 100:
            raise LearnerError('Composed evidence batches require 1 to 100 observations')
        with self.repository.bound_transaction(unit_of_work, learner_ids={request.learner_id for request in requests}) as repository:
            results = [self.evidence.submit(request, repository) for request in requests]
            if transcription_confirmation is not None:
                results = [self.evidence.confirm(ConfirmEvidenceRequest(learner_id=request.learner_id,
                    evidence_id=result.evidence_id, confirmation_source=transcription_confirmation), repository)
                    if result.status == 'pending' and request.source_type == 'HANDWRITTEN_ASSESSMENT' else result
                    for request, result in zip(requests, results)]
            return results

    def withdraw_assessment_evidence_in_transaction(self, learner_id, evidence_ids, session_id, unit_of_work):
        """Invalidate a corrected grade without deleting its immutable observations."""
        with self.repository.bound_transaction(unit_of_work, learner_ids={learner_id}) as repository:
            concepts = set()
            for identifier in dict.fromkeys(evidence_ids):
                evidence = repository.get_evidence(identifier, learner_id)
                if not evidence or evidence.session_id != session_id or not evidence.source_id.startswith('assessment:'):
                    raise LearnerError('Assessment evidence does not belong to this attempt')
                decision = repository.get_decision(identifier, learner_id)
                if decision and decision['status'] == 'ACCEPTED':
                    repository.supersede_decision(identifier, learner_id)
                    concepts.add(repository.canonical_id(evidence.concept_id))
                    repository.audit('assessment_evidence_withdrawn', {'evidence_id': identifier}, learner_id, evidence.concept_id)
            for concept in sorted(concepts):
                self.evidence.recompute(learner_id, concept, repository)

    def get_concept_state(self, request: ConceptStateRequest) -> ConceptStateResponse | None:
        key = self.get_concept(request.concept_id).id
        state = self.states.load(request.learner_id, [key]).get(key)
        return self._state_response(state)

    def _state_response(self, state: LearnerConceptState | None) -> ConceptStateResponse | None:
        return self.states.response(state)

    def get_concept_states(self, learner_id: str, concept_ids: list[str]) -> list[ConceptStateResponse | None]:
        keys = list(dict.fromkeys(concept_ids))
        concepts = self.repository.canonical_concepts(keys)
        for key in keys:
            if key not in concepts:
                raise ConceptNotFoundError(key)
        states = self.states.load(learner_id, [c.id for c in concepts.values()])
        return [self._state_response(states.get(concepts[key].id)) for key in keys]

    def predict_performance(self, request: PerformancePredictionRequest) -> PerformancePrediction:
        concept_id = self.get_concept(request.concept_id).id
        state = self.states.load(request.learner_id, [concept_id]).get(concept_id)
        return self.states.predict(state, concept_id, request.difficulty)

    def find_latest_item_evidence(self, learner_id: str, concept_id: str, item_id: str) -> LearningEvidence | None:
        return self.repository.latest_item_evidence(learner_id, self.get_concept(concept_id).id, item_id)

    def get_relevant_context(self, request: LearnerContextRequest) -> LearnerContextPacket:
        return self.retrieval.packet(request)

    def get_study_recommendations(self, request: StudyRecommendationsRequest) -> list[StudyRecommendation]:
        return self.retrieval.recommend(request)

    def get_study_targets(self, learner_id, context_ids=None, limit=5):
        """One consistent ranking input set for recommendations and verification."""
        request = StudyRecommendationsRequest(learner_id=learner_id, context_ids=context_ids, limit=limit)
        data = self.retrieval.ranking_data(request)
        return dict(recommendations=self.retrieval.recommend(request, data=data),
                    verification=self.retrieval.recommend(request, verification=True, data=data))

    def get_verification_candidates(self, request: VerificationCandidatesRequest) -> list[VerificationCandidate]:
        return self.retrieval.recommend(request, verification=True)

    def recompute_learner_state(self, learner_id: str, concept_id: str) -> LearnerConceptState | None:
        return self.evidence.recompute(learner_id, self.get_concept(concept_id).id)

    def record_misconception(self, learner_id: str, concept_id: str, description: str,
                             confidence: float, context_id: str | None = None) -> Misconception:
        if not description.strip() or len(description) > 1000 or not 0 <= confidence <= 1:
            raise LearnerError('Invalid misconception')
        with self.repository.transaction(learner_ids=[learner_id]) as repository:
            if context_id:
                self.contexts.require(learner_id, context_id, repository)
            concept_id = repository.canonical_id(concept_id)
            if not repository.get_concept(concept_id):
                raise LearnerError('Concept not found')
            observation = Misconception(str(uuid4()), learner_id, concept_id, description,
                                         confidence, 'ACTIVE', context_id)
            observation = replace(observation, id=repository.save_misconception(observation))
            repository.audit('misconception_observed', {'description': description}, learner_id, concept_id)
        return observation

    def resolve_misconception(self, learner_id: str, misconception_id: str) -> bool:
        with self.repository.transaction(learner_ids=[learner_id]) as repository:
            return repository.resolve_misconception(learner_id, misconception_id)

    def explain_state(self, learner_id: str, concept_id: str) -> dict:
        """Internal audit output, intentionally separate from normal prompt packets."""
        concept_id = self.get_concept(concept_id).id
        state = self.repository.get_state(learner_id, concept_id)
        return {'state': asdict(state) if state else None,
                'accepted_evidence_ids': [e.id for e in self.repository.accepted_evidence(learner_id, concept_id)],
                'audit': self.repository.list_audit(learner_id, concept_id)}

    def merge_concepts(self, source_id: str, target_id: str) -> Concept:
        with self.repository.transaction(ontology=True) as repository:
            source_id, target_id = repository.canonical_id(source_id), repository.canonical_id(target_id)
            source, target = repository.get_concept(source_id), repository.get_concept(target_id)
            if not source or not target or source_id == target_id:
                raise LearnerError('Merge requires two distinct existing canonical concepts')
            students = repository.merge_identity(source_id, target_id)
            for form in lookup_forms(source.canonical_name):
                repository.add_alias(target_id, source.canonical_name, form, 'concept_merge', 1)
            for student in students:
                self.evidence.recompute(student, target_id, repository)
            repository.audit('concept_merge', {'source_id': source_id}, concept_id=target_id)
        return target

    def split_concept(self, parent_id: str, children: list[str]) -> list[Concept]:
        """Preserve broad evidence on the parent; children start unobserved."""
        if len(children) < 2 or len(set(children)) != len(children):
            raise LearnerError('Split requires at least two distinct names')
        from app.learner.normalization import normalize
        with self.repository.transaction(ontology=True) as repository:
            parent = repository.get_concept(repository.canonical_id(parent_id))
            if not parent:
                raise LearnerError('Parent concept not found')
            result = []
            for name in children:
                if not normalize(name) or len(name) > 200 or repository.get_concept_by_normalized_name(normalize(name)):
                    raise LearnerError('Split children must be new canonical names')
                if any(repository.find_by_normalized_alias(form) for form in lookup_forms(name)):
                    raise LearnerError('Split children must not duplicate existing aliases')
                child = Concept(str(uuid4()), name)
                repository.create_concept(child)
                for form in lookup_forms(name):
                    repository.add_alias(child.id, name, form, 'concept_split', 1)
                repository.add_relation(parent.id, child.id, 'PARENT_OF', 1)
                repository.copy_parent_contexts(parent.id, child.id)
                result.append(child)
            repository.audit('concept_split', {'children': [c.id for c in result]}, concept_id=parent.id)
        return result
