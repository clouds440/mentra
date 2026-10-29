"""Concrete provider-independent facade. LangGraph nodes can inject this service."""

from collections.abc import Callable
from contextlib import contextmanager
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
    GeneratedConceptsRequest, LearningProgressRequest, LearningProgressPage, ProgressExplanation,
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
    @contextmanager
    def read_scope(self, sessions=None):
        """New service graph per read; the application singleton is never rebound."""
        with self.repository.read_scope(sessions) as repository:
            engine = LearnerEngine(repository, mastery_policy=self.mastery_policy,
                retention_policy=self.retention_policy, ranking_policy=self.retrieval.ranking,
                semantic_resolver=self.concepts.semantic_resolver,
                generated_concept_resolver=self.generated_concepts.resolver, clock=self.clock)
            engine.contexts._read_contexts = {}
            engine.states._read_states = {}
            engine.retrieval._ranking_cache = {}
            engine.retrieval._projection_cache = {}
            yield engine

    def __init__(self, repository: LearnerRepository, *, mastery_policy: MasteryPolicy | None = None,
                 retention_policy: RetentionPolicy | None = None, ranking_policy: RankingPolicy | None = None,
                 semantic_resolver: SemanticResolver | None = None, generated_concept_resolver=None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.mastery_policy = mastery_policy or HeuristicMasteryPolicy()
        self.retention_policy = retention_policy or ExponentialRetentionPolicy()
        self.concepts = ConceptService(repository, semantic_resolver)
        self.contexts = ContextService(repository, self.clock)
        from app.learner.generated_concepts import GeneratedConceptService
        self.generated_concepts = GeneratedConceptService(self.concepts, self.contexts, generated_concept_resolver)
        self.evidence = EvidenceService(repository, self.contexts, self.mastery_policy,
                                        self.retention_policy, self.clock)
        self.states = StateService(repository, self.evidence, self.mastery_policy, self.retention_policy, self.clock)
        self.retrieval = RetrievalService(repository, self.contexts, self.retention_policy,
                                          ranking_policy or WeightedRankingPolicy(), self.clock, self.states)
        from .organization import TopicService
        self.topics = TopicService(self, generated_concept_resolver)

    def register_concept(self, name: str, description: str | None = None, aliases: tuple[str, ...] = ()) -> Concept:
        """Trusted registry operation, never exposed as an unrestricted LLM tool."""
        return self.concepts.register(name, description, aliases)

    def resolve_concept(self, request: ConceptResolutionRequest) -> ConceptResolution:
        return self.concepts.resolve(request)

    async def resolve_generated_concepts(self, request: GeneratedConceptsRequest) -> list[Concept]:
        if self.generated_concepts.resolver is not None and hasattr(self.generated_concepts.resolver, 'organize'):
            self.topics.resolver = self.generated_concepts.resolver
            return await self.topics.resolve(request)
        return await self.generated_concepts.resolve(request)

    async def resolve_generated_concept_labels(self, request: GeneratedConceptsRequest) -> dict[str, str]:
        """Preserve input-label bindings even when canonical labels are renamed/merged."""
        if self.generated_concepts.resolver is not None and hasattr(self.generated_concepts.resolver, 'organize'):
            self.topics.resolver = self.generated_concepts.resolver
            values = await self.topics.resolve(request, _bindings=True)
            return {label:value.id for label,value in values.items()}
        # Compatibility for deployments without the topic organizer. Exact
        # aliases are reused by the legacy domain; never infer input order.
        values = await self.generated_concepts.resolve(request)
        names = {value.canonical_name.casefold():value.id for value in values}
        result = {}
        for label in request.labels:
            if label.casefold() not in names:
                one = await self.generated_concepts.resolve(request.model_copy(update={'labels':[label]}))
                if one: names[label.casefold()] = one[0].id
            if label.casefold() in names: result[label] = names[label.casefold()]
        return result

    async def resolve_encountered_concept(self, request: ConceptResolutionRequest) -> ConceptResolution:
        """A chat-mentioned skill may be organized, but never scored by mention."""
        from starlette.concurrency import run_in_threadpool
        if not request.context_id or not hasattr(self.generated_concepts.resolver, 'organize'):
            return await run_in_threadpool(self.resolve_concept, request)
        context = await run_in_threadpool(self.contexts.require, request.learner_id, request.context_id)
        values = await self.topics.resolve(GeneratedConceptsRequest(learner_id=request.learner_id,
            context_id=request.context_id, topic=(request.surrounding_text or context.name)[:200], labels=[request.label]), published=True)
        value = values[0]
        return ConceptResolution(status='resolved', concept_id=value.id, canonical_name=value.canonical_name,
            confidence=.8, method='organized_subskill')

    def get_learning_topics(self, request):
        return self.topics.page(request)

    def get_topic_subskills(self, request, topic_id):
        return self.topics.skills(request, topic_id)

    async def organize_learning_topics(self, owner, context_id, *, preview=False):
        return await self.topics.organize_existing(owner, context_id, preview=preview)

    def apply_topic_organization(self, owner, identifier, *, undo=False):
        return self.topics.apply_proposal(owner, identifier, undo=undo)

    def move_topic_subskill(self, owner, source, skill_id, target, operation, revision, *, undo=False):
        with self.repository.transaction(learner_ids=[owner]) as repository:
            result = repository.move_topic_skill(owner, source, skill_id, target, operation, revision, undo=undo)
            repository.publish_topic_skills(owner, [skill_id])
            return result

    def rename_learning_topic(self, owner, identifier, name, revision):
        with self.repository.transaction(learner_ids=[owner]) as repository:
            return repository.rename_topic(owner, identifier, name, revision)

    def publish_topic_skills_in_transaction(self, owner, ids, unit_of_work, context_id=None, topic_id=None):
        with self.repository.bound_transaction(unit_of_work, learner_ids=[owner]) as repository:
            if topic_id:
                memberships = repository.skill_memberships(owner, ids)
                if any(memberships.get(identifier, {}).get('topic_id') != str(topic_id) for identifier in ids):
                    from app.core.exceptions import AppError
                    raise AppError('ASSESSMENT_TARGET_CHANGED', 'A selected subskill moved to another topic. Refresh your targets before generating again.', 409)
            repository.publish_topic_skills(owner, ids)
            memberships = repository.skill_memberships(owner, ids)
            for identifier, membership in memberships.items():
                target_context = context_id or membership['context_id']
                if target_context is None:
                    continue
                self.contexts.require(owner, target_context, repository)
                repository.add_context_concept(target_context, identifier, learner_id=owner)

    def get_skill_topics(self, owner, ids):
        return self.repository.skill_memberships(owner, ids)

    def get_topic_practice_concepts(self, owner, context_id, topic_id, limit=5):
        self.contexts.require(owner, context_id)
        selected = self.repository.topic_practice_skills(owner, context_id, topic_id, self.clock(), min(20, limit))
        if not selected:
            from app.core.exceptions import AppError
            raise AppError('ASSESSMENT_TARGET_UNAVAILABLE', 'Choose a topic with available subskills.', 422)
        return selected

    def get_concept(self, concept_id: str) -> Concept:
        return self.concepts.get(concept_id)

    def canonical_concept_ids(self, concept_ids: list[str]) -> dict[str, str]:
        identifiers = list(dict.fromkeys(concept_ids))
        if len(identifiers) > 1024:
            raise LearnerError('Resolve at most 1024 concept IDs at once')
        result = self.repository.canonical_ids(identifiers)
        from app.learner.exceptions import ConceptNotFoundError
        for identifier in identifiers:
            if identifier not in result:
                raise ConceptNotFoundError(identifier)
        return result

    def get_concepts(self, concept_ids: list[str]) -> dict[str, Concept]:
        if len(concept_ids) > 1024:
            raise LearnerError('Read at most 1024 concepts at once')
        result = self.repository.canonical_concepts(concept_ids)
        from app.learner.exceptions import ConceptNotFoundError
        for identifier in concept_ids:
            if identifier not in result:
                raise ConceptNotFoundError(identifier)
        return result

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

    def get_context_page(self, learner_id, offset=0, limit=100, status=None):
        if offset < 0 or not 1 <= limit <= 100 or status not in (None, 'ACTIVE', 'RELATED', 'DORMANT', 'ARCHIVED'):
            raise LearnerError('Invalid context page')
        return [summary(c) for c in self.repository.page_for_learner(learner_id, offset, limit, status)]

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

    def get_learning_progress(self, request: LearningProgressRequest) -> LearningProgressPage:
        return self.retrieval.progress(request)

    def get_progress_explanation(self, learner_id: str, concept_id: str, context_id: str | None = None) -> ProgressExplanation:
        from .progress_explanation import explain
        return explain(self, learner_id, concept_id, context_id)

    def get_practice_concepts(self, learner_id: str, context_id: str, concept_ids: list[str]) -> list[Concept]:
        """Read exact targets only when linked to this owned context; no writes."""
        from app.core.exceptions import AppError
        self.contexts.require(learner_id, context_id)
        if not concept_ids or len(concept_ids) > 20:
            raise AppError('ASSESSMENT_TARGET_UNAVAILABLE', 'Choose available practice topics.', 422)
        ids = list(dict.fromkeys(concept_ids))
        rows = self.repository.context_concepts(learner_id, [context_id], concept_ids=ids, limit=20)
        by_id = {row.id: row for row in rows}
        if any(identifier not in by_id for identifier in ids):
            raise AppError('ASSESSMENT_TARGET_UNAVAILABLE', 'A practice topic is no longer available in this learning context.', 404)
        memberships = self.repository.skill_memberships(learner_id, ids)
        return [replace(by_id[identifier], canonical_name=memberships.get(identifier, {}).get('label', by_id[identifier].canonical_name)) for identifier in ids]

    def get_study_targets(self, learner_id, context_ids=None, limit=5, *, supported_verification=False):
        """One consistent ranking input set for recommendations and verification."""
        request = StudyRecommendationsRequest(learner_id=learner_id, context_ids=context_ids, limit=limit)
        data = self.retrieval.ranking_data(request)
        return dict(recommendations=self.retrieval.recommend(request, data=data),
                    verification=self.retrieval.recommend(request, verification=True, data=data, supported_only=supported_verification))

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
