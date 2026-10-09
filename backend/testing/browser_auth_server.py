"""Browser tests use real auth endpoints and an isolated migrated PostgreSQL schema."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.auth.repositories.postgres import PostgresIdentityRepository
from app.auth.service import AuthService
from app.auth.tokens import ExternalTokenVerifier
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from testing.postgres import PostgresSandbox
from testing.profile_evaluator import TestProfileEvaluator
from testing.profile_evaluator import UnavailableTestProfileEvaluator
from pydantic import BaseModel
from typing import Literal
import asyncio
import tempfile
from qdrant_client import QdrantClient
from app.learner.engine import LearnerEngine
from app.rag.repositories.postgres import RAGRepository
from app.rag.service import RAGService
from app.rag.storage import FileStorage
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.worker import IngestionWorker
from app.api.routes.rag import router as rag_router
from app.api.routes.chat import router as chat_router
from app.langchain.chat_service import ChatService
from app.chat.repositories.postgres import ChatRepository
from app.chat.service import ConversationService
from app.api.routes.conversations import router as conversations_router
from testing.rag import TestEmbedding, TestChatFactory
from testing.history_model import HistoryChatFactory
from app.langchain.llm import MentraLLM
from app.history_management.factory import create_history_management
from app.api.routes.memories import router as memories_router
from app.student_profile.repositories.postgres import PostgresStudentProfileRepository
from app.student_profile.service import StudentProfileService
from app.api.routes.student_profile import router as profile_router


@asynccontextmanager
async def lifespan(application):
    database = PostgresSandbox(seed_learners=False)
    application.state.test_database = database
    application.state.auth_service = AuthService(
        PostgresIdentityRepository(database.sessions), ExternalTokenVerifier({}))
    application.state.student_profile_service = StudentProfileService(
        PostgresStudentProfileRepository(database.sessions), TestProfileEvaluator())
    storage = tempfile.TemporaryDirectory()
    embedding = TestEmbedding()
    vector = QdrantVectorStore(settings.model_copy(update={'qdrant_url':'http://test', 'qdrant_api_key':'test', 'qdrant_collection':'browser'}),
                               embedding, QdrantClient(':memory:', force_disable_check_same_thread=True))
    application.state.rag_service = RAGService(RAGRepository(database.sessions), LearnerEngine(database.repository),
        embedding, vector, FileStorage(storage.name), settings)
    application.state.learner_service = LearnerEngine(database.repository)
    llm = MentraLLM(HistoryChatFactory())
    application.state.chat_service = ChatService(llm)
    application.state.conversation_service = ConversationService(ChatRepository(database.sessions))
    application.state.history_management = create_history_management(database.sessions, llm, application.state.student_profile_service)
    from app.notifications.factory import create_notifications
    application.state.notifications_service = create_notifications(database.sessions)
    application.state.history_management.events.repository.notifications = application.state.notifications_service
    from app.history_management.events.proposal_service import create_event_proposals
    application.state.event_proposal_service = create_event_proposals(database.sessions, application.state.history_management.events)
    from app.assessments.service import create_assessments
    application.state.assessment_service = create_assessments(database.sessions, llm, application.state.learner_service, application.state.rag_service)
    from app.assessments.worker import AssessmentWorker
    grading_worker = AssessmentWorker(application.state.assessment_service)
    from app.chat.attachments import AttachmentService
    from app.chat.repositories.attachments import AttachmentRepository
    from app.langchain.orchestration_service import OrchestrationService
    application.state.attachment_service = AttachmentService(AttachmentRepository(database.sessions))
    application.state.orchestration_service = OrchestrationService(application.state.chat_service,
        rag=application.state.rag_service, history=application.state.history_management,
        attachments=application.state.attachment_service, event_proposals=application.state.event_proposal_service,
        assessments=application.state.assessment_service)
    worker = IngestionWorker(application.state.rag_service)
    stopping = asyncio.Event()

    async def process_jobs():
        while not stopping.is_set():
            await asyncio.to_thread(worker.run_once)
            await asyncio.to_thread(application.state.history_management.events.repository.deliver_reminders)
            await grading_worker.run_once()
            await asyncio.sleep(0.2)

    task = asyncio.create_task(process_jobs())
    application.state.rag_stopping = stopping
    application.state.rag_worker_task = task
    try:
        yield
    finally:
        await application.state.conversation_service.close()
        stopping.set()
        await task
        vector.close()
        storage.cleanup()
        cleanup_database()


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin],
                   allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(auth_router, prefix='/api/v1')
app.include_router(health_router, prefix='/api/v1')
app.include_router(profile_router, prefix='/api/v1')
app.include_router(rag_router, prefix='/api/v1')
app.include_router(chat_router, prefix='/api/v1')
app.include_router(conversations_router, prefix='/api/v1')
app.include_router(memories_router, prefix='/api/v1')
from app.api.routes.chat_attachments import router as attachments_router
app.include_router(attachments_router, prefix='/api/v1')
from app.api.routes.events import router as events_router
from app.api.routes.notifications import router as notifications_router
app.include_router(events_router, prefix='/api/v1')
app.include_router(notifications_router, prefix='/api/v1')
from app.api.routes.event_proposals import router as event_proposals_router
app.include_router(event_proposals_router, prefix='/api/v1')
from app.api.routes.learning import router as learning_router
app.include_router(learning_router, prefix='/api/v1')
from app.api.routes.assessments import router as assessments_router
app.include_router(assessments_router, prefix='/api/v1')


def cleanup_database():
    database = app.state.test_database
    if database is not None:
        database.close()
        app.state.test_database = None


@app.post('/testing/cleanup', status_code=204)
async def cleanup():
    # Playwright terminates processes forcibly on Windows; teardown calls this first.
    # This route exists only in this localhost test server, never the application API.
    app.state.rag_stopping.set()
    await app.state.rag_worker_task
    cleanup_database()
    return Response(status_code=204)


class EvaluatorMode(BaseModel):
    mode: Literal['available', 'unavailable']


@app.post('/testing/profile-evaluator', status_code=204)
def test_evaluator(body: EvaluatorMode):
    app.state.student_profile_service.evidence.evaluator = TestProfileEvaluator() if body.mode == 'available' else UnavailableTestProfileEvaluator()
    return Response(status_code=204)

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=18003, log_level='warning')
