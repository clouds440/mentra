"""Authenticated event routes; fixed paths precede UUID resource paths."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.history_management.events.schemas import (EventCreate, EventEdit, PreferencesEdit,
    TemporalPreview, TemporalPreviewResult, EventOutcome, EventDetail, EventPage, EventPreferences, EventSummary, EventSync)

def private_response(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/events', tags=['events'], dependencies=[Depends(private_response)])


def service(request):
    return request.app.state.history_management.events


@router.post('/temporal-preview', response_model=TemporalPreviewResult)
async def temporal_preview(body: TemporalPreview, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).temporal_preview, identity.learner_id, body)


@router.get('/preferences', response_model=EventPreferences)
async def preferences(request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).preferences, identity.learner_id)


@router.patch('/preferences', response_model=EventPreferences)
async def set_preferences(body: PreferencesEdit, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).set_preferences, identity.learner_id, body)


@router.get('/summary', response_model=EventSummary)
async def summary(request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).summary, identity.learner_id)


@router.get('/operations/{client_request_id}', response_model=EventOutcome)
async def operation(client_request_id: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).operation, identity.learner_id, str(client_request_id))


@router.get('/sync', response_model=EventSync)
async def sync(request: Request, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).sync, identity.learner_id, after, limit)


@router.get('', response_model=EventPage)
async def events(request: Request, after: datetime | None = None, before: datetime | None = None,
                 status: str | None = Query('scheduled', pattern='^(scheduled|completed|cancelled)$'),
                 kind: str | None = Query(None, pattern='^(quiz|exam|assignment|deadline|study|other)$'),
                 query: str = Query('', max_length=200), cursor: str | None = Query(None, max_length=1000),
                 limit: int = Query(30, ge=1, le=50), identity=Depends(require_onboarded_identity)):
    filters = dict(after=after, before=before, status=status, kind=kind, query=query)
    return await run_in_threadpool(service(request).list, identity.learner_id, filters, cursor, limit)


@router.post('', response_model=EventOutcome)
async def create(body: EventCreate, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).create, identity.learner_id, body)


@router.get('/{event_id}', response_model=EventDetail)
async def detail(event_id: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).detail, identity.learner_id, str(event_id))


@router.patch('/{event_id}', response_model=EventOutcome)
async def edit(event_id: UUID, body: EventEdit, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).edit, identity.learner_id, str(event_id), body)


@router.delete('/{event_id}', response_model=EventOutcome)
async def remove(event_id: UUID, request: Request, client_request_id: UUID,
                 expected_revision: int = Query(ge=1), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).remove, identity.learner_id, str(event_id), expected_revision, str(client_request_id))
