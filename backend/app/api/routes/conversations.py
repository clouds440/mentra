from uuid import UUID
from fastapi import APIRouter, Depends, Request, Query
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.auth.dependencies import require_identity
from app.chat.schemas import SendTurn, EditConversation
from app.rag.schemas import ChatSelection
from .chat import generate_reply

router = APIRouter(prefix='/conversations', tags=['conversations'])


def service(request: Request):
    return request.app.state.conversation_service


@router.get('/sync')
async def sync(request: Request, cursor: int | None = Query(None, ge=0), active: UUID | None = None,
               identity=Depends(require_identity)):
    return await run_in_threadpool(service(request).repository.sync, identity.learner_id, cursor, str(active) if active else None)


@router.get('')
async def recent(request: Request, cursor: str | None = Query(None, max_length=300), limit: int = Query(40, ge=1, le=100),
                 identity=Depends(require_identity)):
    return await run_in_threadpool(service(request).repository.recent, identity.learner_id, cursor, limit)


@router.post('/turns')
async def send(body: SendTurn, request: Request, stream: bool = False, identity=Depends(require_onboarded_identity)):
    stream = stream or request.headers.get('prefer') == 'respond-async'
    async def generate(messages, selection, scope):
        response = await generate_reply(messages, ChatSelection(**selection), request, identity, service(request).policy, scope)
        return response.model_dump(mode='json')
    return await service(request).send(identity.learner_id, body, generate, with_scope=True, wait=not stream)


@router.get('/{conversation_id}/turns/{turn_id}/events')
async def activity_events(conversation_id: UUID, turn_id: UUID, request: Request,
                          attempt: int = Query(1, ge=1), after: int = Query(0, ge=0, le=256),
                          identity=Depends(require_onboarded_identity)):
    import asyncio
    import json
    from datetime import datetime, timezone
    from fastapi.encoders import jsonable_encoder
    from starlette.responses import StreamingResponse
    from app.chat.repositories.activity import ActivityRepository
    from app.core.exceptions import AppError
    repo = ActivityRepository(service(request).repository.sessions)
    owner, cid, tid = identity.learner_id, str(conversation_id), str(turn_id)
    cursor = request.headers.get('last-event-id')
    if cursor:
        try:
            attempt, after = map(int, cursor.split(':'))
            if attempt < 1 or not 0 <= after <= 256:
                raise ValueError()
        except ValueError:
            raise AppError('ACTIVITY_CURSOR_INVALID', 'Invalid activity cursor.', 422)
    initial = await run_in_threadpool(repo.page, owner, cid, tid, attempt, after)

    async def events():
        nonlocal attempt, after
        page = initial
        # Bounded connections reconnect via their last durable cursor.
        for _ in range(110):
            if await request.is_disconnected():
                return
            if page['reset']:
                attempt, after = page['attempt'], 0
                yield 'event: reset\ndata: {}\n\n'
            for event in page['events']:
                after = event['sequence']
                yield f'id: {attempt}:{after}\nevent: activity\ndata: {json.dumps(event)}\n\n'
            if page['state'] != 'RUNNING' or page['lease_until'] <= datetime.now(timezone.utc):
                status = await run_in_threadpool(service(request).repository.status, owner, cid, tid, True)
                yield f'event: terminal\ndata: {json.dumps(jsonable_encoder(status))}\n\n'
                return
            yield ': heartbeat\n\n'
            await asyncio.sleep(1)
            try:
                page = await run_in_threadpool(repo.page, owner, cid, tid, attempt, after)
            except AppError:
                yield 'event: unavailable\ndata: {}\n\n'
                return
    return StreamingResponse(events(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@router.get('/{conversation_id}/messages')
async def messages(conversation_id: UUID, request: Request, before: int | None = Query(None, ge=1),
                   after: int | None = Query(None, ge=0), limit: int = Query(40, ge=1, le=100), identity=Depends(require_onboarded_identity)):
    from app.core.exceptions import AppError
    if before is not None and after is not None:
        raise AppError('CHAT_CURSOR_INVALID', 'Choose one pagination direction.', 422)
    return await run_in_threadpool(service(request).repository.history, identity.learner_id, str(conversation_id), before, after, limit)


@router.get('/{conversation_id}/status')
async def status(conversation_id: UUID, request: Request, turn_id: UUID | None = None,
                 incremental: bool = False, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).repository.status, identity.learner_id, str(conversation_id), str(turn_id) if turn_id else None, incremental)


@router.patch('/{conversation_id}')
async def rename(conversation_id: UUID, body: EditConversation, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).repository.edit, identity.learner_id, str(conversation_id), body.expected_revision, body.title)


@router.delete('/{conversation_id}')
async def remove(conversation_id: UUID, request: Request, expected_revision: int = Query(ge=1), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).repository.edit, identity.learner_id, str(conversation_id), expected_revision, None, True)
