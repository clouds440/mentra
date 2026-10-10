from app.core.config import settings
from app.db.database import get_session_factory
from app.rag.repositories.postgres import RAGRepository
from app.rag.service import RAGService
from app.rag.storage import FileStorage


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def create_rag_service(learner, embedding, vector_store):
    return RAGService(RAGRepository(get_session_factory()), learner, embedding, vector_store,
                      FileStorage(settings.rag_storage_dir), settings)
