"""Lightweight reminder producer. No model, embedding or document initialization."""
import logging
import signal
from threading import Event


def main():
    from app.db.database import init_db, get_session_factory
    from app.notifications.factory import create_notifications
    from app.history_management.repositories.events.postgres import EventRepository
    init_db()
    sessions = get_session_factory()
    repository = EventRepository(sessions, notifications=create_notifications(sessions))
    stopping = Event()
    for name in (signal.SIGTERM, signal.SIGINT): signal.signal(name, lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            count = repository.deliver_reminders()
            logging.getLogger('mentra').info('Reminder worker heartbeat; processed=%d', count)
        except Exception:
            logging.getLogger('mentra').exception('Reminder batch failed; retrying bounded batch')
        stopping.wait(5)


if __name__ == '__main__': main()
