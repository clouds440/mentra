from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from app.student_profile.dependencies import require_onboarded_identity
from app.workspace.schemas import PanelResource
from app.workspace.repositories.pins import PinRepository

router = APIRouter(prefix='/workspace/pins', tags=['workspace'])

def private(response: Response):
    response.headers['Cache-Control'] = 'no-store'

def repository(request: Request):
    return PinRepository(request.app.state.conversation_service.repository.sessions)

@router.get('', dependencies=[Depends(private)])
def list_pins(request: Request, identity=Depends(require_onboarded_identity)):
    return repository(request).list(identity.learner_id)

@router.post('', dependencies=[Depends(private)])
def pin(source: PanelResource, request: Request, identity=Depends(require_onboarded_identity)):
    return repository(request).add(identity.learner_id, source.model_dump(mode='json', exclude_none=True))

@router.delete('/{pin_id}', status_code=204, dependencies=[Depends(private)])
def unpin(pin_id: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    repository(request).remove(identity.learner_id, str(pin_id))
