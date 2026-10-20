from app.core.config import settings
from app.db.database import get_session_factory
from .service import FilesService
from .provider import CloudinaryProvider


def create_files(sessions=None, config=None):
    config = config or settings
    return FilesService(
        sessions or get_session_factory(), CloudinaryProvider(config), config
    )
