from datetime import datetime, timedelta, timezone
from app.core.exceptions import AppError
from .contracts import EventsRepository
from .temporal import preview


class EventsService:
    def __init__(self, repository: EventsRepository, learner=None, *, clock=None):
        self.repository = repository
        self.learner = learner
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _context(self, owner, draft):
        if draft.context_id is None:
            return
        from app.learner.exceptions import LearningContextNotFoundError
        if self.learner is None:
            raise AppError('CONTEXT_UNAVAILABLE', 'Learning context lookup is unavailable.', 503)
        try:
            self.learner.get_context_summaries(owner, [draft.context_id])
        except LearningContextNotFoundError:
            raise AppError('CONTEXT_NOT_FOUND', 'Learning context not found.', 404) from None

    def create(self, owner, body):
        if body.context_id is not None:
            replay = self.repository.replay(owner, str(body.client_request_id),
                ['create', body.model_dump(mode='json', exclude={'client_request_id'})])
            if replay is not None:
                return replay
        self._context(owner, body)
        return self.repository.create(owner, body)

    def edit(self, owner, identifier, body):
        if body.details is not None:
            if body.details.context_id is not None:
                replay = self.repository.replay(owner, str(body.client_request_id),
                    ['edit', identifier, body.model_dump(mode='json', exclude={'client_request_id'})])
                if replay is not None:
                    return replay
            self._context(owner, body.details)
        return self.repository.edit(owner, identifier, body)

    def remove(self, owner, identifier, revision, operation):
        return self.repository.remove(owner, identifier, revision, operation)

    def detail(self, owner, identifier):
        return self.repository.detail(owner, identifier)

    def list(self, owner, filters, cursor=None, limit=30):
        if not 1 <= limit <= 50:
            raise AppError('INVALID_PAGE', 'Choose between 1 and 50 events.', 422)
        for value in (filters.get('after'), filters.get('before')):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None or not 1899 <= value.year <= 2201):
                raise AppError('INVALID_RANGE', 'Choose aware dates between 1899 and 2201.', 422)
        start = filters.get('after') or self.clock().astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        start = start.astimezone(timezone.utc)
        end = (filters.get('before') or start + timedelta(days=90)).astimezone(timezone.utc)
        if end <= start or end - start > timedelta(days=366):
            raise AppError('INVALID_RANGE', 'Choose an aware date range of at most one year.', 422)
        return self.repository.list(owner, dict(filters, after=start, before=end), cursor, limit)

    def preferences(self, owner):
        return self.repository.preferences(owner)

    def set_preferences(self, owner, body):
        return self.repository.set_preferences(owner, body)

    def operation(self, owner, identifier):
        return self.repository.operation(owner, identifier)

    def sync(self, owner, after, limit=100):
        if after < 0 or not 1 <= limit <= 100:
            raise AppError('INVALID_CURSOR', 'Invalid synchronization cursor or limit.', 422)
        return self.repository.sync(owner, after, limit)

    def summary(self, owner):
        return self.repository.summary(owner)

    def temporal_preview(self, owner, body):
        return preview(body, self.preferences(owner), self.clock())
