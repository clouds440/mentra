from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging, logger
from app.db.database import init_db
from app.db.database import get_session_factory
from app.chat.repositories.postgres import ChatRepository
from app.chat.service import ConversationService
from app.langchain.chat_service import ChatService
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import model_factory
from app.learner.factory import create_learner_engine
from app.auth.factory import create_auth_service
from app.student_profile.factory import create_student_profile_service
from app.rag.embeddings import SentenceTransformerEmbeddingService
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.vector_store import VectorStore
from app.rag.factory import create_rag_service
from app.rag.upload_limit import MaterialUploadLimit
from app.history_management.factory import create_history_management


def create_app() -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None, None]:
        init_db()
        embedding_service = SentenceTransformerEmbeddingService(settings)
        vector_store: VectorStore = QdrantVectorStore(settings, embedding_service)
        try:
            application.state.learner_service = create_learner_engine()
            application.state.auth_service = create_auth_service()
            application.state.llm = MentraLLM(model_factory)
            application.state.student_profile_service = create_student_profile_service(model_factory, application.state.llm)
            application.state.embedding_service = embedding_service
            application.state.vector_store = vector_store
            application.state.rag_service = create_rag_service(application.state.learner_service, embedding_service, vector_store)
            application.state.model_factory = model_factory
            application.state.chat_service = ChatService(application.state.llm)
            application.state.conversation_service = ConversationService(ChatRepository(get_session_factory()))
            application.state.history_management = create_history_management(get_session_factory(), application.state.llm,
                application.state.student_profile_service, application.state.learner_service)
            logger.info("Mentra backend started successfully.")
            yield
        finally:
            if hasattr(application.state, 'conversation_service'):
                await application.state.conversation_service.close()
            if hasattr(application.state, 'rag_service'):
                application.state.rag_service.close()
            vector_store.close()

    app = FastAPI(
        title="Mentra API",
        version="0.1.0",
        description="Adaptive AI learning companion backend.",
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    app.add_middleware(MaterialUploadLimit, maximum=settings.rag_max_upload_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins + [settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"message": "Welcome to Mentra API"}

    return app


app = create_app()
