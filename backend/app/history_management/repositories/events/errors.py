"""Map known persistence races/timeouts without hiding unexpected SQL failures."""
from functools import wraps
from sqlalchemy.exc import DBAPIError
from app.core.exceptions import AppError


def database_errors(method):
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except DBAPIError as error:
            original = error.orig
            constraint = getattr(getattr(original, 'diag', None), 'constraint_name', None)
            if constraint == 'fk_hm_event_learner_id_learning_context':
                raise AppError('CONTEXT_NOT_FOUND', 'Learning context not found.', 404) from None
            if getattr(original, 'sqlstate', None) in {'55P03', '57014'}:
                raise AppError('EVENTS_UNAVAILABLE', 'Events are busy. Retry or recover the operation using its request ID.', 503) from None
            raise
    return guarded
