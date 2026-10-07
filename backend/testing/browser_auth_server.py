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
    try:
        yield
    finally:
        cleanup_database()


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin],
                   allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(auth_router, prefix='/api/v1')
app.include_router(health_router, prefix='/api/v1')
app.include_router(profile_router, prefix='/api/v1')


def cleanup_database():
    database = app.state.test_database
    if database is not None:
        database.close()
        app.state.test_database = None


@app.post('/testing/cleanup', status_code=204)
def cleanup():
    # Playwright terminates processes forcibly on Windows; teardown calls this first.
    # This route exists only in this localhost test server, never the application API.
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
