from uuid import UUID
from fastapi import APIRouter, Request, Response, Depends, Query
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.notifications.schemas import InboxEdit, NotificationPreferencesEdit

router = APIRouter(prefix='/notifications', tags=['notifications'])


def service(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.notifications_service


@router.get('')
async def inbox(unread: bool = False, before: UUID | None = None, limit: int = Query(30, ge=1, le=50),
                app=Depends(service), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(app.inbox, identity.learner_id, unread=unread, before=str(before) if before else None, limit=limit)


@router.get('/preferences')
async def preferences(app=Depends(service), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(app.preferences, identity.learner_id)


@router.patch('/preferences')
async def set_preferences(body: NotificationPreferencesEdit, app=Depends(service), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(app.set_preferences, identity.learner_id, body)


@router.get('/sync')
async def sync(after: int = Query(0, ge=0), app=Depends(service), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(app.sync, identity.learner_id, after)


@router.patch('/{identifier}')
async def edit(identifier: UUID, body: InboxEdit, app=Depends(service), identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(app.edit, identity.learner_id, str(identifier), body)
