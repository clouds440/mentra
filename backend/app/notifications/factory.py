def create_notifications(sessions):
    from .service import NotificationsService
    from .repositories.postgres import NotificationRepository
    return NotificationsService(NotificationRepository(sessions))
