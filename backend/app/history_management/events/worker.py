"""Lightweight reminder producer. No model, embedding or document initialization."""
import logging
import signal
from threading import Event


def main():
    from app.db.database import init_db, get_session_factory
    from app.notifications.factory import create_notifications
    from app.history_management.repositories.events.postgres import EventRepository
    from app.core.logging import configure_logging
    configure_logging('events-worker')
    init_db()
    sessions = get_session_factory()
    repository = EventRepository(sessions, notifications=create_notifications(sessions))
    stopping = Event()
    for name in (signal.SIGTERM, signal.SIGINT): signal.signal(name, lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            from app.core.logging import workflow_logger
            with workflow_logger.workflow('events.reminder_batch', quiet=True) as execution:
                count = repository.deliver_reminders()
                if execution.outcome == 'unknown':
                    execution.outcome = 'success'
                workflow_logger.event('reminder.batch', processed_count=count)
        except Exception:
            logging.getLogger('mentra').exception('Reminder batch failed; retrying bounded batch')
        stopping.wait(5)


if __name__ == '__main__': main()
