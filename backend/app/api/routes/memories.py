from uuid import UUID
from fastapi import APIRouter, Depends, Request, Query
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.history_management.schemas import MemoryCreate, MemoryEdit, PreferencesEdit

router = APIRouter(prefix='/memories', tags=['memories'])


def repository(request):
    return request.app.state.history_management.repository


@router.get('/preferences')
async def preferences(request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(repository(request).preferences, identity.learner_id)


@router.patch('/preferences')
async def change_preferences(body: PreferencesEdit, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(repository(request).set_preferences, identity.learner_id, body)


@router.get('/history/{conversation_id}')
async def history(conversation_id: UUID, request: Request, sequence: int = Query(ge=1), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.history_management.reader.window, identity.learner_id, str(conversation_id), sequence)


@router.get('')
async def memories(request: Request, query: str = Query('', max_length=300), status: str | None = Query(None, pattern='^(active|pending|conflict)$'),
                   cursor: str | None = Query(None, max_length=300), limit: int = Query(30, ge=1, le=50), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(repository(request).list, identity.learner_id, query, status, cursor, limit)


@router.post('')
async def create(body: MemoryCreate, request: Request, identity=Depends(require_onboarded_identity)):
    result = await run_in_threadpool(repository(request).write, identity.learner_id, body.content, body.category,
        'manual:' + str(body.client_request_id), pinned=body.pinned, expires_at=body.expires_at)
    if not result.get('memory'):
        from app.core.exceptions import AppError
        raise AppError('MEMORY_SAVE_REJECTED', 'This save was already deleted. Create a new memory explicitly to save it again.', 409)
    return result


@router.get('/{memory_id}')
async def detail(memory_id: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(repository(request).detail, identity.learner_id, str(memory_id))


@router.patch('/{memory_id}')
async def edit(memory_id: UUID, body: MemoryEdit, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(repository(request).edit, identity.learner_id, str(memory_id), body)


@router.delete('/{memory_id}')
async def remove(memory_id: UUID, request: Request, expected_revision: int = Query(ge=1), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(repository(request).remove, identity.learner_id, str(memory_id), expected_revision)
