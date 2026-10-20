from app.core.config import settings
from app.db.database import get_session_factory
from app.rag.repositories.postgres import RAGRepository
from app.rag.service import RAGService
from app.files.factory import create_files


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def create_rag_service(learner, embedding, vector_store, files=None):
    from app.db.admission import Admission
    files=files or create_files()
    return RAGService(RAGRepository(get_session_factory(),files), learner, embedding, vector_store,
                      files, settings, admission=Admission(get_session_factory(), settings=settings))
