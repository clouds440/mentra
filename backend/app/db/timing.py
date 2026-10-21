"""SQL latency without statements, bind values, credentials, or user data."""
import logging
from time import monotonic
from sqlalchemy import event
from app.core.observability.events import emit
from app.core.observability.context import current
from functools import wraps


def record(name, value=1):
    collector = current.get()
    if collector is not None:
        with collector.lock:
            collector.database[name] = collector.database.get(name, 0) + value


def instrument_engine(engine):
    @event.listens_for(engine, 'checkout')
    def checkout(*args):
        record('checkouts')

    # These driver calls are outside cursor execution and used to be invisible.
    for name, label in [('do_ping', 'ping'), ('do_commit', 'commit'), ('do_rollback', 'rollback'), ('connect', 'connect')]:
        original = getattr(engine.dialect, name)
        @wraps(original)
        def timed(*args, _original=original, _label=label, **kwargs):
            started = monotonic()
            try:
                return _original(*args, **kwargs)
            finally:
                record(_label + '_count')
                record(_label + '_ms', (monotonic() - started) * 1000)
        setattr(engine.dialect, name, timed)
    @event.listens_for(engine, 'before_cursor_execute')
    def before(connection, cursor, statement, parameters, context, executemany):
        context._mentra_started = monotonic()

    def finish(context, outcome):
        started = getattr(context, '_mentra_started', None)
        if started is not None:
            context._mentra_started = None
            elapsed = (monotonic() - started) * 1000
            record('queries')
            record('query_ms', elapsed)
            compiled = getattr(context, 'compiled', None)
            statement = getattr(compiled, 'statement', None)
            kind = 'select' if getattr(statement, 'is_select', False) else 'insert' if getattr(statement, 'is_insert', False) else 'update' if getattr(statement, 'is_update', False) else 'delete' if getattr(statement, 'is_delete', False) else 'command'
            emit('db.query', level=logging.DEBUG if outcome == 'success' else logging.WARNING,
                 operation=kind, duration_ms=round(elapsed, 3), outcome=outcome)

    @event.listens_for(engine, 'after_cursor_execute')
    def after(connection, cursor, statement, parameters, context, executemany):
        finish(context, 'success')

    @event.listens_for(engine, 'handle_error')
    def error(context):
        if context.execution_context is not None:
            finish(context.execution_context, 'failed')

    return engine
