from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.files.schemas import FileReference
from app.files.delivery import deliver

def private_response(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/chat-attachments', tags=['chat attachments'], dependencies=[Depends(private_response)])


class LibraryAdmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID
    context_ids: list[str] = Field(min_length=1, max_length=20)


@router.post('')
async def upload(request: Request, body: 'FileReference', identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.attachment_service.attach,identity.learner_id,str(body.file_id))


@router.delete('/{identifier}', status_code=204)
async def remove(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    await run_in_threadpool(request.app.state.attachment_service.repository.remove, identity.learner_id, str(identifier))


@router.get('/{identifier}')
async def detail(identifier: UUID, conversation_id: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.attachment_service.repository.detail,
        identity.learner_id, str(identifier), str(conversation_id))


@router.post('/{identifier}/library')
async def library(identifier: UUID, body: LibraryAdmission, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.attachment_service.add_to_library,
        identity.learner_id, str(identifier), str(body.conversation_id), body.context_ids, request.app.state.rag_service)


@router.get('/{identifier}/source')
async def source(identifier: UUID, conversation_id: UUID, request: Request,
                 identity=Depends(require_onboarded_identity)):
    original = await run_in_threadpool(request.app.state.attachment_service.original,
        identity.learner_id, str(identifier), str(conversation_id))
    return await deliver(request,identity.learner_id,original['file_id'],original['binding_id'],'inline')
