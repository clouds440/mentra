"""Canonical registry and bounded, provider-optional semantic resolution."""

from difflib import SequenceMatcher
from typing import Protocol
from uuid import uuid4

from app.learner.exceptions import ConceptNotFoundError, LearnerError, LearningContextNotFoundError
from app.learner.models import Concept
from app.learner.normalization import lookup_forms, normalize, tokens
from app.learner.schemas import ConceptResolution, ConceptResolutionRequest


class SemanticResolver(Protocol):
    def search(self, label: str, context: str | None, limit: int) -> list[str]: ...
    def choose(self, label: str, candidates: list[Concept], context: str | None) -> tuple[str | None, float]: ...


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class ConceptService:
    def __init__(self, repository, semantic_resolver: SemanticResolver | None = None):
        self.repository = repository
        self.semantic_resolver = semantic_resolver

    def get(self, concept_id: str) -> Concept:
        concept = self.repository.get_concept(self.repository.canonical_id(concept_id))
        if concept is None:
            raise ConceptNotFoundError(concept_id)
        return concept

    def register(self, name: str, description: str | None = None, aliases=()) -> Concept:
        if not normalize(name) or len(name) > 200:
            raise LearnerError("Canonical name must contain between 1 and 200 characters")
        with self.repository.transaction(ontology=True) as repository:
            matches = {}
            for form in lookup_forms(name):
                direct = repository.get_concept_by_normalized_name(form)
                if direct:
                    matches[direct.id] = direct
                matches.update({c.id: c for c in repository.find_by_normalized_alias(form)})
            if len(matches) > 1:
                raise LearnerError('Canonical name has ambiguous aliases; review the registry first')
            existing = next(iter(matches.values()), None)
            concept = existing or Concept(str(uuid4()), name.strip(), description)
            if not existing:
                repository.create_concept(concept)
            for alias in (name, *aliases):
                for form in lookup_forms(alias):
                    repository.add_alias(concept.id, alias, form, "registry", 1.0)
        return concept

    def resolve(self, request: ConceptResolutionRequest) -> ConceptResolution:
        if request.context_id and not self.repository.get_context(request.learner_id, request.context_id):
            raise LearningContextNotFoundError(request.context_id)
        forms = lookup_forms(request.label)
        if not forms:
            return ConceptResolution(status="rejected", confidence=0, method="empty")
        matches = {}
        for form in forms:
            direct = self.repository.get_concept_by_normalized_name(form)
            if direct:
                matches[direct.id] = direct
            matches.update({c.id: c for c in self.repository.find_by_normalized_alias(form)})
        if request.context_id and len(matches) > 1:
            scoped = {key: c for key, c in matches.items()
                      if request.context_id in self.repository.get_concept_context_ids(key, learner_id=request.learner_id)}
            if scoped:
                matches = scoped
        if len(matches) == 1:
            concept = next(iter(matches.values()))
            return ConceptResolution(status="resolved", concept_id=concept.id,
                                     canonical_name=concept.canonical_name, confidence=1, method="exact_alias")
        candidates = dict(matches)
        for term in sorted(tokens(request.label))[:8]:
            candidates.update({c.id: c for c in self.repository.search_concepts(term, 20)})
        # Character similarity ranks suggestions only; it never establishes identity.
        ranked = sorted(candidates.values(), key=lambda c: (
            -SequenceMatcher(None, forms[0], normalize(c.canonical_name)).ratio(), c.id
        ))[:5]
        if self.semantic_resolver is not None:
            for concept_id in self.semantic_resolver.search(request.label, request.surrounding_text, 5)[:5]:
                concept = self.repository.get_concept(self.repository.canonical_id(concept_id))
                if concept and concept.id not in {c.id for c in ranked}:
                    ranked.append(concept)
            ranked = ranked[:8]
            if ranked:
                chosen, confidence = self.semantic_resolver.choose(request.label, ranked, request.surrounding_text)
                if chosen in {c.id for c in ranked} and 0.9 <= confidence <= 1:
                    concept = next(c for c in ranked if c.id == chosen)
                    return ConceptResolution(status="resolved", concept_id=chosen,
                                             canonical_name=concept.canonical_name,
                                             confidence=confidence, method="constrained_semantic")
        candidate_id = str(uuid4())
        with self.repository.transaction() as repository:
            candidate_id = repository.save_candidate(candidate_id, request.label, forms[0], request.context_id,
                                                       {"alternatives": [c.id for c in ranked]}, learner_id=request.learner_id)
            if repository.get_candidate(candidate_id, learner_id=request.learner_id)['resolution_status'] == 'DISCARDED':
                return ConceptResolution(status='rejected', confidence=1, method='reviewed_rejection', candidate_id=candidate_id)
        return ConceptResolution(status="ambiguous" if len(matches) > 1 else "candidate",
                                 confidence=0, method="unresolved", candidate_id=candidate_id,
                                 alternatives=[c.id for c in ranked])

    def resolve_candidate(self, candidate_id: str, concept_id: str | None = None, *, discard=False) -> Concept | None:
        with self.repository.transaction(ontology=True) as repository:
            candidate = repository.get_candidate_for_review(candidate_id)
            if not candidate or candidate['resolution_status'] != 'UNRESOLVED':
                raise LearnerError("Unresolved candidate not found")
            if discard:
                repository.resolve_candidate(candidate_id, "DISCARDED")
                return None
            concept = (repository.get_concept(repository.canonical_id(concept_id)) if concept_id else
                       repository.get_concept_by_normalized_name(candidate['normalized_name']))
            if concept_id and not concept:
                raise ConceptNotFoundError(concept_id)
            if not concept:
                concept = Concept(str(uuid4()), candidate['proposed_name'])
                repository.create_concept(concept)
            for form in lookup_forms(candidate['proposed_name']):
                repository.add_alias(concept.id, candidate['proposed_name'], form, 'reviewed_candidate', 1)
            repository.resolve_candidate(candidate_id, 'MERGED' if concept_id else 'PROMOTED', concept.id)
            if candidate['context_id']:
                repository.add_context_concept(candidate['context_id'], concept.id, learner_id=candidate['learner_id'])
            repository.audit('candidate_resolved', {'candidate_id': candidate_id}, concept_id=concept.id)
        return concept
