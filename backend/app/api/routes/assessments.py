from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response, Query, UploadFile, File, Form
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.assessments.schemas import GenerationRequest, StartAttempt, SubmitAnswers, Assessment, Attempt
from pydantic import BaseModel, ConfigDict, Field

def private_response(response: Response): response.headers['Cache-Control'] = 'no-store'
router = APIRouter(prefix='/assessments', tags=['assessments'], dependencies=[Depends(private_response)])

class AssessmentPreferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    auto_add: bool
    expected_revision: int = Field(ge=0)

@router.get('/preferences')
async def preferences(request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.chat.settings, identity.learner_id)

@router.patch('/preferences')
async def update_preferences(body: AssessmentPreferences, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.chat.update_settings,
        identity.learner_id, body.auto_add, body.expected_revision)

@router.get('/chat-drafts/{identifier}')
async def chat_draft(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.chat.detail, identity.learner_id, str(identifier))

@router.post('/chat-drafts/{identifier}/publish')
async def publish_chat_draft(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.chat.publish, identity.learner_id, str(identifier))

@router.post('', response_model=Assessment)
async def generate(body: GenerationRequest, request: Request, identity=Depends(require_onboarded_identity)):
    return await request.app.state.orchestration_service.generate_assessment(identity.learner_id, body)

@router.get('')
async def list_assessments(request: Request, offset: int = Query(0, ge=0, le=200), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.list, identity.learner_id, offset)

@router.get('/attempts/{identifier}', response_model=Attempt)
async def attempt(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.attempt, identity.learner_id, str(identifier))

@router.post('/attempts/{identifier}/submission', response_model=Attempt)
async def submit(identifier: UUID, body: SubmitAnswers, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.submit, identity.learner_id, str(identifier), body)

@router.post('/attempts/{identifier}/source', response_model=Attempt)
async def source(identifier: UUID, request: Request, expected_revision: int = Form(ge=1), file: UploadFile = File(...), identity=Depends(require_onboarded_identity)):
    try:
        return await request.app.state.assessment_service.upload_paper_with_vision(identity.learner_id, str(identifier), expected_revision, file.file, file.filename)
    finally: await file.close()

@router.post('/attempts/{identifier}/corrections', response_model=Attempt)
async def correct(identifier: UUID, body: SubmitAnswers, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.correct, identity.learner_id, str(identifier), body)

@router.get('/{identifier}', response_model=Assessment)
async def detail(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.detail, identity.learner_id, str(identifier))

@router.get('/{identifier}/attempts', response_model=list[Attempt])
async def attempts(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.attempts, identity.learner_id, str(identifier))

@router.post('/{identifier}/attempts', response_model=Attempt)
async def start(identifier: UUID, body: StartAttempt, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.start, identity.learner_id, str(identifier), body)

@router.delete('/{identifier}', status_code=204)
async def remove(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    await run_in_threadpool(request.app.state.assessment_service.repository.remove, identity.learner_id, str(identifier))
