from app.core.config import settings
from app.db.database import get_session_factory
from app.auth.repositories.postgres import PostgresIdentityRepository
from app.auth.service import AuthService
from app.auth.tokens import ExternalTokenVerifier


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def create_auth_service():
    return AuthService(PostgresIdentityRepository(get_session_factory()),
        ExternalTokenVerifier(settings.auth_external_providers), session_seconds=settings.auth_session_seconds)
