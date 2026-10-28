from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response, Query
from app.files.schemas import FileReference
from pydantic import Field


class AssessmentSource(FileReference):
    expected_revision: int = Field(ge=1)
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.assessments.schemas import GenerationRequest, AssessmentIntent, StartAttempt, SubmitAnswers, SaveDraftAnswers, Assessment, Attempt
from pydantic import BaseModel, ConfigDict, Field
from app.assessments.schemas import RetryGrading
from app.assessments.schemas import MistakePracticeRequest

def private_response(response: Response): response.headers['Cache-Control'] = 'no-store'
router = APIRouter(prefix='/assessments', tags=['assessments'], dependencies=[Depends(private_response)])


@router.get('/page')
async def assessment_page(request: Request, offset: int = Query(0, ge=0, le=200),
        view: str = Query('assessments', pattern='^(assessments|create)$'), assessment_id: UUID | None = None,
        identity=Depends(require_onboarded_identity)):
    def read():
        from app.db.reads import read_sessions
        from app.assessments.repositories.postgres import AssessmentRepository
        from app.assessments.repositories.list_view import summaries
        source = request.app.state.assessment_service.repository
        with read_sessions(source.sessions) as sessions:
            repository = AssessmentRepository(sessions, clock=source.clock, files=source.files)
            page = summaries(repository, identity.learner_id, offset) if view == 'assessments' else dict(items=[], next_offset=None)
            contexts = []
            if view == 'create':
                with request.app.state.learner_service.read_scope(sessions) as learner:
                    contexts = sorted(learner.get_context_summaries(identity.learner_id), key=lambda value: value.context_id)
            identifier = str(assessment_id) if assessment_id and view == 'assessments' else None
            return dict(page, contexts=contexts,
                detail=repository.detail(identity.learner_id, identifier) if identifier else None,
                attempts=repository.attempts(identity.learner_id, identifier) if identifier else [])
    return await run_in_threadpool(read)

@router.get('/mistakes')
async def mistake_history(request: Request, assessment_id: list[UUID] = Query(default=[], max_length=200),
                          topic_id: list[str] = Query(default=[], max_length=200), offset: int = Query(default=0, ge=0),
                          context_id: list[str] = Query(default=[], max_length=200),
                          limit: int = Query(default=30, ge=1, le=30), recent: bool = False,
                          identity=Depends(require_onboarded_identity)):
    from app.assessments.repositories.revision_practice import list_mistakes
    return await run_in_threadpool(list_mistakes, request.app.state.assessment_service.repository,
        identity.learner_id, list(map(str, assessment_id)), topic_id, offset, context_id, limit, recent)

from app.assessments.schemas import RevisionPracticeRequest

@router.post('/mistakes/practice')
async def revision_practice(body: RevisionPracticeRequest, request: Request, identity=Depends(require_onboarded_identity)):
    from app.assessments.repositories.revision_practice import enqueue_revision
    return await run_in_threadpool(enqueue_revision, request.app.state.assessment_service, identity.learner_id, body)

@router.post('/generation-jobs')
async def queue_generation(body: AssessmentIntent, request: Request, identity=Depends(require_onboarded_identity)):
    return await request.app.state.assessment_service.queue_generation(identity.learner_id, body)

@router.get('/generation-jobs/{identifier}')
async def generation_job(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.generation_jobs.get, identity.learner_id, str(identifier))

@router.post('/generation-jobs/{identifier}/retry')
async def retry_generation(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.generation_jobs.retry, identity.learner_id, str(identifier))


class StopGeneration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)


@router.post('/generation-jobs/{identifier}/stop')
async def stop_generation(identifier: UUID, body: StopGeneration, request: Request, identity=Depends(require_onboarded_identity)):
    value = await run_in_threadpool(request.app.state.assessment_service.generation_jobs.stop,
        identity.learner_id, str(identifier), body.expected_revision)
    if value['state'] == 'stopped' and value.get('source_turn_id'):
        conversation_service = request.app.state.conversation_service
        page = await run_in_threadpool(conversation_service.repository.status, identity.learner_id,
            value['conversation_id'], value['source_turn_id'])
        await conversation_service.stop(identity.learner_id, value['conversation_id'], value['source_turn_id'],
            page['turn']['attempt'], stopped_job=(value['id'], value['revision']))
    return value

@router.put('/attempts/{identifier}/draft', response_model=Attempt)
async def save_draft(identifier: UUID, body: SaveDraftAnswers,
                     request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.save_draft_answers,
                                  identity.learner_id, str(identifier), body)

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

@router.post('/attempts/{identifier}/practice', response_model=Assessment)
async def practise_mistakes(identifier: UUID, body: MistakePracticeRequest, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.practise_mistakes,
        identity.learner_id, str(identifier), body)

@router.post('/attempts/{identifier}/submission', response_model=Attempt)
async def submit(identifier: UUID, body: SubmitAnswers, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.submit, identity.learner_id, str(identifier), body)

@router.post('/attempts/{identifier}/source', response_model=Attempt)
async def source(identifier: UUID, request: Request, body: 'AssessmentSource', identity=Depends(require_onboarded_identity)):
    from app.db.admission import request_capacity
    async with request_capacity(request, identity.learner_id, 'parse', seconds=600):
        return await request.app.state.assessment_service.upload_paper_with_vision(identity.learner_id, str(identifier), body.expected_revision, str(body.file_id))

@router.post('/attempts/{identifier}/retry', response_model=Attempt)
async def retry(identifier: UUID, body: RetryGrading, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.retry_grading,
        identity.learner_id, str(identifier), body)

@router.post('/attempts/{identifier}/corrections', response_model=Attempt)
async def correct(identifier: UUID, body: SubmitAnswers, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.assessment_service.repository.correct, identity.learner_id, str(identifier), body)

@router.get('/{identifier}/paper.pdf')
async def question_paper(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    from app.assessments.question_paper import render_question_paper
    from app.core.exceptions import AppError
    def render():
        service = request.app.state.assessment_service
        try:
            assessment = service.repository.detail(identity.learner_id, str(identifier))
        except AppError as error:
            if error.code != 'ASSESSMENT_NOT_FOUND': raise
            assessment = service.chat.question_paper(identity.learner_id, str(identifier))
        return render_question_paper(assessment)
    data = await run_in_threadpool(render)
    return Response(data, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="mentra-question-paper-{identifier}.pdf"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

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
