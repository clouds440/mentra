def create_events_service(sessions, *, clock=None, learner=None):
    from app.history_management.repositories.events.postgres import EventRepository
    from .service import EventsService
    return EventsService(EventRepository(sessions, clock=clock), learner, clock=clock)
