"""No dependency on Events, Chat, Learner, a model, or a scheduler."""
from app.core.exceptions import AppError
from .schemas import NotificationDraft


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'publish': {'result': lambda value: dict(domain_status=value['outcome']), 'outcome': lambda value: 'skipped' if value['outcome'] == 'disabled' else 'success'},
})
class NotificationsService:
    def __init__(self, repository, producers=('events',)):
        self.repository, self.producers = repository, frozenset(producers)

    def publish(self, transaction, draft: NotificationDraft):
        if draft.producer not in self.producers:
            raise AppError('NOTIFICATION_PRODUCER_INVALID', 'Unknown notification producer.', 422)
        return self.repository.publish(transaction, draft)

    def remove_target(self, transaction, target_kind, target_id):
        return self.repository.remove_target(transaction, target_kind, target_id)

    def inbox(self, owner, **filters): return self.repository.inbox(owner, **filters)
    def edit(self, owner, identifier, request): return self.repository.edit(owner, identifier, request)
    def preferences(self, owner): return self.repository.preferences(owner)
    def set_preferences(self, owner, request): return self.repository.set_preferences(owner, request)
    def sync(self, owner, after): return self.repository.sync(owner, after)
