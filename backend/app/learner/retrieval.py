"""Context-aware compact packets and adaptive target selection."""

from heapq import nlargest
from dataclasses import replace

from app.learner.normalization import query_terms, normalize
from app.learner.scoring.signals import diagnostics, recommended_difficulty
from app.learner.schemas import (
    LearnerContextConcept, LearnerContextPacket, StudyRecommendation, VerificationCandidate, PerformanceEstimate,
)


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class RetrievalService:
    def __init__(self, repository, contexts, retention, ranking, clock, states):
        self.repository, self.contexts = repository, contexts
        self.retention, self.ranking, self.clock = retention, ranking, clock
        self.states = states

    def ranking_data(self, request):
        contexts = self.contexts.select(request.learner_id, request.context_ids)
        concepts = self.repository.context_concepts(request.learner_id, [c.id for c in contexts])
        ids = [c.id for c in concepts]
        states = self.states.load(request.learner_id, ids)
        prerequisites = self.repository.prerequisite_counts(ids, [c.id for c in contexts], request.learner_id)
        factors = self.repository.context_factors(request.learner_id, contexts)
        now = self.clock()
        return concepts, states, prerequisites, factors, now

    def recommend(self, request, verification=False, *, data=None):
        concepts, states, prerequisites, factors, now = data if data is not None else self.ranking_data(request)

        def ranked():
            for concept in concepts:
                state = states.get(concept.id)
                factor = factors.get(concept.id, dict(importance=0.5, relevance=0.5, target_difficulty=0.5))
                if factor['importance'] == 0:
                    continue
                prediction = self.states.predict(state, concept.id, factor['target_difficulty'])
                retention = self.retention.calculate(state, now) if state else None
                projected = replace(state, mastery=prediction.expected_score) if state and prediction.supported else state
                score, reason = self.ranking.score(projected, retention, prerequisites.get(concept.id, 0),
                                                   factor['relevance'], verification)
                challenge = recommended_difficulty(state)
                if state and state.mastery is not None and not prediction.supported and not state.verification_required:
                    score, reason, challenge = max(score, 0.75), 'difficulty_unverified', factor['target_difficulty']
                score *= (0.2 + 0.8 * factor['importance']) * (0.5 + 0.5 * factor['relevance'])
                status = diagnostics(state, retention)['knowledge_status']
                if verification:
                    yield VerificationCandidate(concept_id=concept.id, name=concept.canonical_name,
                          reason=reason, priority=score, mastery=state.mastery if state else None,
                          estimate_confidence=state.estimate_confidence if state else None,
                          retention_confidence=retention,
                          recommended_difficulty=challenge, importance=factor['importance'])
                else:
                    yield StudyRecommendation(concept_id=concept.id, name=concept.canonical_name,
                                              reason=reason, priority=score, recommended_difficulty=challenge,
                                              importance=factor['importance'], relevance=factor['relevance'], knowledge_status=status)
        return nlargest(request.limit, ranked(), key=lambda item: (item.priority, item.concept_id))

    def packet(self, request):
        contexts = self.contexts.select(request.learner_id, request.context_ids, request.query, request.include_related)
        context_ids = [c.id for c in contexts]
        included_contexts = {c.id: c for c in contexts}
        terms = query_terms(request.query)
        words = set(normalize(request.query).replace('?', '').split())
        if ('study' in words and ('should' in words or 'what' in words)) or 'weakest' in words or 'revise' in words:
            terms = []
        concepts = self.repository.context_concepts(request.learner_id, context_ids,
                                                    query_terms=terms, limit=request.max_concepts,
                                                    normalized_query=normalize(request.query)) if terms else []
        if not concepts:
            from app.learner.schemas import StudyRecommendationsRequest
            selected = self.recommend(StudyRecommendationsRequest(learner_id=request.learner_id,
                                      context_ids=context_ids, limit=request.max_concepts))
            selected_concepts = self.repository.canonical_concepts([item.concept_id for item in selected])
            concepts = [selected_concepts[item.concept_id] for item in selected]
        if request.include_related and concepts and len(concepts) < request.max_concepts:
            seen = {c.id for c in concepts}
            owned_contexts = {c.id: c for c in self.repository.list_for_learner(request.learner_id)}
            for concept in list(concepts):
                for related in self.repository.list_related_concepts(concept.id, limit=request.max_concepts, min_confidence=0.8):
                    if related.id not in seen and len(concepts) < request.max_concepts:
                        related_contexts = [owned_contexts[key] for key in self.repository.get_concept_context_ids(related.id, learner_id=request.learner_id)
                                            if key in owned_contexts]
                        accessible = [c for c in related_contexts if c.status != 'ARCHIVED' or c.id in context_ids]
                        if not accessible:
                            continue
                        if not any(c.id in context_ids for c in accessible) and len(context_ids) >= 20:
                            continue
                        concepts.append(related)
                        seen.add(related.id)
                        for context in accessible:
                            if context.id not in context_ids and len(context_ids) < 20:
                                context_ids.append(context.id)
                                included_contexts[context.id] = context
        ids = [c.id for c in concepts]
        states = self.states.load(request.learner_id, ids)
        misconceptions = self.repository.misconceptions_for_concepts(request.learner_id, ids)
        included = [included_contexts[key] for key in context_ids]
        factors = self.repository.context_factors(request.learner_id, included)
        now = self.clock()
        items = []
        for concept in concepts:
            state = states.get(concept.id)
            retention = self.retention.calculate(state, now) if state else None
            info = diagnostics(state, retention)
            factor = factors.get(concept.id, dict(importance=0.5, relevance=0.5, target_difficulty=0.5))
            prediction = self.states.predict(state, concept.id, factor['target_difficulty'])
            items.append(LearnerContextConcept(concept_id=concept.id, name=concept.canonical_name,
                         mastery=state.mastery if state else None,
                         estimate_confidence=state.estimate_confidence if state else None,
                         retention_confidence=retention, knowledge_status=info['knowledge_status'],
                         mastery_lower_bound=info['mastery_lower_bound'], mastery_upper_bound=info['mastery_upper_bound'],
                         target_performance=PerformanceEstimate.model_validate(prediction.model_dump(exclude={'concept_id', 'policy_version'})),
                         verification_required=state.verification_required if state else False,
                         hint_dependency=state.hint_dependency if state else None,
                         **factor,
                         misconceptions=misconceptions.get(concept.id, [])[:3]))
        return LearnerContextPacket(active_contexts=[c.name for c in contexts if c.status == 'ACTIVE'],
                                    context_ids=context_ids, concepts=items, generated_at=now)
