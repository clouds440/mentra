from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.student_profile import router as profile_router
from app.api.routes.eduverse import router as eduverse_router
from app.api.routes.rag import router as rag_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.memories import router as memories_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(memories_router)
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(profile_router)
api_router.include_router(eduverse_router)
api_router.include_router(rag_router)
