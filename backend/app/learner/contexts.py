"""Student-scoped context lifecycle and intentional access to dormant knowledge."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from app.learner.exceptions import LearningContextNotFoundError, LearnerError
from app.learner.models import LearningContext
from app.learner.normalization import normalize, tokens, query_terms
from app.learner.schemas import (
    ActivateLearningContextRequest, ContextActivityRequest, ContextTransitionRequest,
    LearningContextSummary, ResolveLearningContextRequest,
)


def summary(context: LearningContext) -> LearningContextSummary:
    return LearningContextSummary(context_id=context.id, name=context.name,
                                  status=context.status, relevance_score=context.relevance_score)


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class ContextService:
    def __init__(self, repository, clock, dormancy_days: int = 60):
        self.repository, self.clock = repository, clock
        self.dormancy_days = dormancy_days

    def require(self, learner_id: str, context_id: str, repository=None) -> LearningContext:
        context = (repository or self.repository).get_context(learner_id, context_id)
        if context is None:
            raise LearningContextNotFoundError(context_id)
        return context

    def resolve(self, request: ResolveLearningContextRequest) -> LearningContextSummary:
        with self.repository.transaction(learner_ids=[request.learner_id]) as repository:
            context = repository.find_context(request.learner_id, normalize(request.name))
            if context is None:
                context = LearningContext(str(uuid4()), request.learner_id, request.name, "RELATED",
                                          request.description, 0.5, self.clock())
                repository.save_context(context)
                repository.audit('context_created', {'name': request.name}, request.learner_id)
        if request.activate:
            return self.activate(ActivateLearningContextRequest(learner_id=request.learner_id, context_id=context.id))
        return summary(context)

    def activate(self, request: ActivateLearningContextRequest) -> LearningContextSummary:
        with self.repository.transaction(learner_ids=[request.learner_id]) as repository:
            context = self.require(request.learner_id, request.context_id, repository)
            if request.exclusive:
                for other in repository.list_for_learner(request.learner_id):
                    if other.id != context.id and other.status in ('ACTIVE', 'RELATED'):
                        repository.save_context(replace(other, status='DORMANT', relevance_score=0.1))
                        repository.audit('context_transition', {'context_id': other.id, 'status': 'DORMANT',
                                         'reason': 'explicit_context_switch'}, request.learner_id)
            context = replace(context, status='ACTIVE', relevance_score=1, last_activity_at=self.clock())
            repository.save_context(context)
            repository.audit('context_transition', {'context_id': context.id, 'status': 'ACTIVE',
                             'reason': 'explicit_activation'}, request.learner_id)
        return summary(context)

    def record_activity(self, request: ContextActivityRequest, repository=None) -> LearningContextSummary:
        if repository is None:
            with self.repository.transaction(learner_ids=[request.learner_id]) as transaction:
                return self.record_activity(request, transaction)
        context = self.require(request.learner_id, request.context_id, repository)
        occurred = request.occurred_at or self.clock()
        if occurred.tzinfo is None or occurred > self.clock() + timedelta(minutes=5):
            raise LearnerError('Context activity must have a valid, non-future timezone-aware timestamp')
        context = replace(context, last_activity_at=max(context.last_activity_at or occurred, occurred))
        repository.save_context(context)
        repository.audit('context_activity', {'context_id': context.id, 'reason': request.reason}, request.learner_id)
        return summary(context)

    def transition(self, request: ContextTransitionRequest) -> LearningContextSummary:
        if request.status == 'ACTIVE':
            return self.activate(ActivateLearningContextRequest(learner_id=request.learner_id,
                                                               context_id=request.context_id, exclusive=False))
        with self.repository.transaction(learner_ids=[request.learner_id]) as repository:
            context = self.require(request.learner_id, request.context_id, repository)
            context = replace(context, status=request.status,
                              relevance_score={'RELATED': 0.5, 'DORMANT': 0.1, 'ARCHIVED': 0}[request.status])
            repository.save_context(context)
            repository.audit('context_transition', request.model_dump(mode='json'), request.learner_id)
        return summary(context)

    def expire_inactive(self, learner_id: str) -> list[LearningContext]:
        cutoff = self.clock() - timedelta(days=self.dormancy_days)
        contexts = self.repository.list_for_learner(learner_id)
        stale = [c for c in contexts
                 if c.status in ('ACTIVE', 'RELATED') and c.last_activity_at and c.last_activity_at < cutoff]
        if stale:
            refreshed = {}
            with self.repository.transaction(learner_ids=[learner_id]) as repository:
                for old in stale:
                    current = self.require(learner_id, old.id, repository)
                    if current.status in ('ACTIVE', 'RELATED') and current.last_activity_at < cutoff:
                        current = replace(current, status='DORMANT', relevance_score=0.1)
                        repository.save_context(current)
                        repository.audit('context_transition', {'context_id': old.id, 'status': 'DORMANT',
                                         'reason': 'inactivity'}, learner_id)
                    refreshed[old.id] = current
            contexts = [refreshed.get(c.id, c) for c in contexts]
        return contexts

    def select(self, learner_id: str, context_ids: list[str] | None = None,
               query: str | None = None, include_related=True) -> list[LearningContext]:
        contexts = self.expire_inactive(learner_id)
        if context_ids is not None:
            owned = {c.id: c for c in contexts}
            for key in context_ids:
                if key not in owned:
                    raise LearningContextNotFoundError(key)
            return [replace(owned[key], relevance_score=1) for key in dict.fromkeys(context_ids)]
        selected = {c.id: c for c in contexts if c.status == 'ACTIVE' or
                    (include_related and c.status == 'RELATED')}
        if query:
            query_tokens = set(query_terms(query))
            matched = self.repository.context_ids_for_terms(learner_id, sorted(query_tokens))
            for context in contexts:
                if context.status != 'ARCHIVED' and tokens(context.name) & query_tokens:
                    matched.add(context.id)
            # Query aliases can intentionally recover dormant knowledge even when
            # the subject's name itself is absent (dictionary vs database table).
            focused = {c.id: replace(c, relevance_score=1) for c in contexts if c.id in matched and
                       c.status != 'ARCHIVED' and (include_related or c.status == 'ACTIVE')}
            if focused:
                selected = focused
        return list(selected.values())[:20] if query is not None else list(selected.values())
