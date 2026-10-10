from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def create_notifications(sessions):
    from .service import NotificationsService
    from .repositories.postgres import NotificationRepository
    return NotificationsService(NotificationRepository(sessions))
