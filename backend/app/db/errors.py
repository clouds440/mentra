"""Infrastructure-only SQL failure translation; write outcomes remain uncertain."""
from sqlalchemy.exc import DBAPIError, TimeoutError


def database_busy(error):
    return isinstance(error, TimeoutError) or isinstance(error, DBAPIError) and (
        getattr(error.orig, 'sqlstate', None) in {'55P03', '57014', '53300', '08000', '08003', '08006', '08001'}
        or error.connection_invalidated or type(error.orig).__name__ == 'ConnectionTimeout')


async def handle_database_error(request, error):
    from app.core.exception_handlers import _error_response, handle_unexpected_error
    if database_busy(error):
        return _error_response('DATABASE_BUSY', 'The database is busy. Recover the operation using its request ID before retrying.', 503)
    return await handle_unexpected_error(request, error)


def register_database_handlers(app):
    app.add_exception_handler(DBAPIError, handle_database_error)
    app.add_exception_handler(TimeoutError, handle_database_error)
