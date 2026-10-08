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
async def send(body: SendTurn, request: Request, identity=Depends(require_onboarded_identity)):
    async def generate(messages, selection):
        response = await generate_reply(messages, ChatSelection(**selection), request, identity, service(request).policy)
        return response.model_dump(mode='json')
    return await service(request).send(identity.learner_id, body, generate)


@router.get('/{conversation_id}/messages')
async def messages(conversation_id: UUID, request: Request, before: int | None = Query(None, ge=1),
                   after: int | None = Query(None, ge=0), limit: int = Query(40, ge=1, le=100), identity=Depends(require_onboarded_identity)):
    from app.core.exceptions import AppError
    if before is not None and after is not None:
        raise AppError('CHAT_CURSOR_INVALID', 'Choose one pagination direction.', 422)
    return await run_in_threadpool(service(request).repository.history, identity.learner_id, str(conversation_id), before, after, limit)


@router.get('/{conversation_id}/status')
async def status(conversation_id: UUID, request: Request, turn_id: UUID | None = None, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).repository.status, identity.learner_id, str(conversation_id), str(turn_id) if turn_id else None)


@router.patch('/{conversation_id}')
async def rename(conversation_id: UUID, body: EditConversation, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).repository.edit, identity.learner_id, str(conversation_id), body.expected_revision, body.title)


@router.delete('/{conversation_id}')
async def remove(conversation_id: UUID, request: Request, expected_revision: int = Query(ge=1), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(service(request).repository.edit, identity.learner_id, str(conversation_id), expected_revision, None, True)
