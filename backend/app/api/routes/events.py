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


@router.get('/page')
async def agenda_page(request: Request, after: datetime | None = None, before: datetime | None = None,
        status: str | None = Query('scheduled', pattern='^(scheduled|completed|cancelled)$'),
        kind: str | None = Query(None, pattern='^(quiz|exam|assignment|deadline|study|other)$'),
        query: str = Query('', max_length=200), cursor: str | None = Query(None, max_length=1000),
        limit: int = Query(30, ge=1, le=50), selected: UUID | None = None,
        identity=Depends(require_onboarded_identity)):
    def read():
        from app.db.reads import read_sessions
        from app.history_management.events.service import EventsService
        from app.history_management.repositories.events.postgres import EventRepository
        from app.history_management.repositories.events.proposals import EventProposalRepository
        source = service(request).repository
        with read_sessions(source.sessions) as sessions:
            events = EventRepository(sessions, clock=source.clock, capacity=source.capacity)
            page = EventsService(events, clock=source.clock).list(identity.learner_id,
                dict(after=after, before=before, status=status, kind=kind, query=query), cursor, limit)
            detail = events.detail(identity.learner_id, str(selected)) if selected else None
            proposals, proposals_error = None, False
            if cursor is None:
                # Proposals are an independent section: their outage must not
                # prevent reading the agenda, as with the separate endpoints.
                try:
                    original = request.app.state.event_proposal_service.repository
                    proposals = EventProposalRepository(sessions, events, clock=original.clock).list(identity.learner_id)
                except Exception:
                    sessions.session.rollback()
                    proposals_error = True
            return dict(page, detail=detail, proposals=proposals, proposals_error=proposals_error)
    return await run_in_threadpool(read)


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


@router.get('/{event_id}/calendar')
async def calendar_export(event_id: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    from app.history_management.events.calendar import calendar_file
    event = await run_in_threadpool(service(request).detail, identity.learner_id, str(event_id))
    from app.files.exports import calendar_asset
    from app.files.delivery import deliver
    file_id,binding_id=await run_in_threadpool(calendar_asset,request.app.state.files_service,identity.learner_id,
        str(event_id),event['revision'],calendar_file(EventDetail.model_validate(event)))
    return await deliver(request,identity.learner_id,file_id,binding_id)


@router.patch('/{event_id}', response_model=EventOutcome)
async def edit(event_id: UUID, body: EventEdit, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).edit, identity.learner_id, str(event_id), body)


@router.delete('/{event_id}', response_model=EventOutcome)
async def remove(event_id: UUID, request: Request, client_request_id: UUID,
                 expected_revision: int = Query(ge=1), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).remove, identity.learner_id, str(event_id), expected_revision, str(client_request_id))
