"""Compatibility entry point and one-connection workflow logging API."""
import logging
import sys
from types import SimpleNamespace
from .observability import events
from .observability.events import ContextFilter, emit
from .observability.formatters import EventFormatter
from .observability.registration import connect_module, operation
from .observability.steps import Operation, workflow, set_outcome, start_task
from .observability.context import envelope
from .observability.errors import ServerErrorFilter
from .observability.files import DailyFileHandler

logger = logging.getLogger('mentra')
workflow_logger = SimpleNamespace(connect_module=connect_module, operation=operation,
    step=Operation, workflow=workflow, set_outcome=set_outcome, start_task=start_task,
    envelope=envelope, event=emit)


class SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record):
        pass


def configure_logging(process_role='api'):
    from app.core.config import settings
    events.process_role = process_role
    handler = SafeStreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.addFilter(ServerErrorFilter())
    handler.setFormatter(EventFormatter(settings.log_format or ('json' if settings.app_env == 'production' else 'console')))
    handler.setLevel(settings.log_level)
    root = logging.getLogger()
    for old in root.handlers:
        if getattr(old, '_mentra_owned', False):
            old.close()
    handlers = [handler]
    if settings.log_file_enabled:
        file_handler = DailyFileHandler(settings.log_directory)
        file_handler.addFilter(ContextFilter())
        file_handler.addFilter(ServerErrorFilter())
        file_handler.setLevel(settings.log_level)
        handlers.append(file_handler)
    for owned in handlers:
        owned._mentra_owned = True
    root.handlers = handlers
    root.setLevel(settings.log_level)
    for existing in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(existing, logging.Logger):
            existing.handlers = [h for h in existing.handlers if not isinstance(h, logging.StreamHandler)]
            existing.propagate = True
    for name in ('mentra', 'mentra.events', 'uvicorn', 'uvicorn.error', 'uvicorn.access', 'httpx', 'httpcore', 'sqlalchemy', 'openai'):
        target = logging.getLogger(name)
        target.handlers = []
        target.propagate = True
        target.setLevel(settings.log_level if name.startswith('mentra') or name.startswith('uvicorn') else logging.WARNING)
    logging.getLogger('uvicorn.access').disabled = True
    emit('process.started', role=process_role)
