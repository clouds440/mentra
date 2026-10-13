"""Resolve AI-selected practice targets without treating them as learner evidence."""
from typing import Protocol
from app.core.exceptions import AppError
from app.learner.schemas import ConceptResolutionRequest, GeneratedConceptsRequest
from app.learner.normalization import normalize
from app.learner.exceptions import ConceptAssistanceUnavailable
from app.core.logging import workflow_logger


class GeneratedConceptResolver(Protocol):
    async def expand(self, labels, topic): ...
    async def match(self, labels, candidates, topic): ...


class GeneratedConceptService:
    def __init__(self, concepts, contexts, resolver=None):
        self.concepts, self.contexts, self.resolver = concepts, contexts, resolver

    def shortlist(self, resolutions, terms):
        candidates = {}
        for resolution in resolutions:
            for identifier in resolution.alternatives:
                concept = self.concepts.get(identifier)
                candidates[concept.id] = concept
                if len(candidates) >= 40: return list(candidates.values())
        for term in dict.fromkeys(normalize(term) for term in terms):
            for concept in self.concepts.repository.search_concepts(term, 8):
                candidates[concept.id] = concept
                if len(candidates) >= 40: return list(candidates.values())
        return list(candidates.values())

    def promote(self, owner, candidate_id, match=None):
        try:
            return self.concepts.resolve_candidate(candidate_id, match)
        except Exception:
            current = self.concepts.repository.get_candidate(candidate_id, learner_id=owner)
            if not current or current['resolution_status'] not in ('PROMOTED', 'MERGED'): raise
            return self.concepts.get(current['resolved_concept_id'])

    def commit(self, owner, context_id, label, resolution, match=None):
        if resolution.status == 'rejected':
            return None  # Preserve an explicitly discarded candidate.
        if resolution.status == 'resolved':
            concept = self.concepts.get(resolution.concept_id)
        else:
            candidate = self.concepts.repository.get_candidate(resolution.candidate_id, learner_id=owner)
            if not candidate or candidate['context_id'] != context_id:
                raise AppError('CONCEPT_CANDIDATE_NOT_FOUND', 'Practice target unavailable.', 404)
            if candidate['resolution_status'] in ('PROMOTED', 'MERGED'):
                concept = self.concepts.get(candidate['resolved_concept_id'])
            elif resolution.status == 'ambiguous' and match is None:
                # Do not guess among existing meanings. A subject-qualified
                # identity lets practice proceed without merging unrelated IDs.
                original = resolution.candidate_id
                qualified = f'{self.contexts.require(owner, context_id).name}: {label}'
                if len(qualified) > 200:
                    from hashlib import sha256
                    qualified = f'{qualified[:179]} [{sha256(qualified.encode()).hexdigest()[:16]}]'
                resolution = self.concepts.resolve(ConceptResolutionRequest(
                    learner_id=owner, context_id=context_id, label=qualified))
                if resolution.status == 'rejected': return None
                if resolution.status == 'resolved': concept = self.concepts.get(resolution.concept_id)
                elif resolution.status == 'candidate': concept = self.promote(owner, resolution.candidate_id)
                else: raise AppError('CONCEPT_IDENTITY_UNAVAILABLE', 'Practice target could not be identified.', 409)
                concept = self.promote(owner, original, concept.id)
            else:
                # The server authorizes new AI-selected practice targets. Existing
                # matching IDs gain an alias, retaining all prior evidence/history.
                concept = self.promote(owner, resolution.candidate_id, match)
        with self.concepts.repository.transaction(learner_ids=[owner]) as repository:
            self.contexts.require(owner, context_id, repository)
            repository.add_context_concept(context_id, concept.id, learner_id=owner)
        return concept

    async def resolve(self, request: GeneratedConceptsRequest):
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(self.contexts.require, request.learner_id, request.context_id)
        labels = list(dict.fromkeys(request.labels))
        resolutions = [await run_in_threadpool(self.concepts.resolve, ConceptResolutionRequest(
            learner_id=request.learner_id, context_id=request.context_id, label=label,
            surrounding_text=request.topic)) for label in labels]
        unresolved = [(label, result) for label, result in zip(labels, resolutions) if result.status in ('candidate', 'ambiguous')]
        matches, equivalents = {}, {}
        if unresolved and self.resolver is not None:
            pending = [label for label, _ in unresolved]
            candidates = []
            if await run_in_threadpool(self.concepts.repository.list_concepts, 1):
                terms = []
                try:
                    terms = (await self.resolver.expand(pending, request.topic)).terms
                except ConceptAssistanceUnavailable:
                    workflow_logger.event('concept.resolution_fallback', stage='search_terms')
                candidates = await run_in_threadpool(self.shortlist, [result for _, result in unresolved], [*pending, *terms])
            if candidates or len(pending) > 1:
                try:
                    proposed = (await self.resolver.match(pending, candidates, request.topic)).matches
                except ConceptAssistanceUnavailable:
                    workflow_logger.event('concept.resolution_fallback', stage='match')
                    proposed = []
                allowed = {concept.id for concept in candidates}
                seen = set()
                invalid = set()
                for match in proposed:
                    if match.label not in pending or match.label in seen or (match.concept_id is not None and match.concept_id not in allowed):
                        invalid.add(match.label)
                        continue
                    if match.equivalent_label is not None and match.equivalent_label not in pending[:pending.index(match.label)]:
                        invalid.add(match.label)
                        continue
                    seen.add(match.label)
                    if match.concept_id is not None and match.confidence >= .9: matches[match.label] = match.concept_id
                    if match.equivalent_label is not None and match.confidence >= .9: equivalents[match.label] = match.equivalent_label
                for label in invalid:
                    matches.pop(label, None)
                    equivalents.pop(label, None)
                if invalid:
                    workflow_logger.event('concept.resolution_fallback', stage='invalid_match', count=len(invalid))
        concepts, resolved_labels = {}, {}
        for label, resolution in zip(labels, resolutions):
            match = matches.get(label) or resolved_labels.get(equivalents.get(label))
            concept = await run_in_threadpool(self.commit, request.learner_id, request.context_id, label, resolution, match)
            if concept:
                concepts[concept.id] = concept
                resolved_labels[label] = concept.id
        if not concepts:
            raise AppError('ASSESSMENT_TARGETS_REQUIRED', 'No usable practice targets were available.', 422)
        return list(concepts.values())
