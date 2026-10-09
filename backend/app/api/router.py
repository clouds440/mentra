from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.student_profile import router as profile_router
from app.api.routes.eduverse import router as eduverse_router
from app.api.routes.rag import router as rag_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.memories import router as memories_router
from app.api.routes.events import router as events_router
from app.api.routes.chat_attachments import router as attachments_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.event_proposals import router as event_proposals_router
from app.api.routes.learning import router as learning_router
from app.api.routes.assessments import router as assessments_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(memories_router)
api_router.include_router(events_router)
api_router.include_router(attachments_router)
api_router.include_router(notifications_router)
api_router.include_router(event_proposals_router)
api_router.include_router(learning_router)
api_router.include_router(assessments_router)
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(profile_router)
api_router.include_router(eduverse_router)
api_router.include_router(rag_router)
