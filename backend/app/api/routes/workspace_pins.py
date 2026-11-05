from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select

from app.auth.repositories.tables import learner
from app.core.exceptions import AppError
from app.student_profile.dependencies import require_onboarded_identity
from app.workspace.schemas import PanelResource
from app.workspace.tables import pins

router = APIRouter(prefix='/workspace/pins', tags=['workspace'])


def private(response: Response):
    response.headers['Cache-Control'] = 'no-store'


def sessions(request: Request):
    return request.app.state.conversation_service.repository.sessions


@router.get('', dependencies=[Depends(private)])
def list_pins(request: Request, identity=Depends(require_onboarded_identity)):
    with sessions(request)() as session:
        return [dict(row) for row in session.execute(select(pins.c.id, pins.c.source)
            .where(pins.c.learner_id == identity.learner_id)
            .order_by(pins.c.created_at.desc(), pins.c.id)).mappings()]


@router.post('', dependencies=[Depends(private)])
def pin(source: PanelResource, request: Request, identity=Depends(require_onboarded_identity)):
    owner = identity.learner_id
    data = source.model_dump(mode='json', exclude_none=True)
    key = sha256(json.dumps({name: value for name, value in data.items() if name != 'title'}, sort_keys=True).encode()).hexdigest()
    with sessions(request).begin() as session:
        # Serialize deduplication and the per-account limit.
        session.execute(select(learner.c.id).where(learner.c.id == owner).with_for_update()).scalar_one()
        old = session.execute(select(pins.c.id, pins.c.source).where(
            pins.c.learner_id == owner, pins.c.resource_key == key)).mappings().first()
        if old:
            return dict(old)
        if session.scalar(select(func.count()).select_from(pins).where(pins.c.learner_id == owner)) >= 100:
            raise AppError('WORKSPACE_PIN_LIMIT', 'Remove a pinned source before adding another. You can keep up to 100 pins.', 422)
        identifier = str(uuid4())
        session.execute(pins.insert().values(learner_id=owner, id=identifier, resource_key=key,
            source=data, created_at=datetime.now(timezone.utc)))
        return dict(id=identifier, source=data)


@router.delete('/{pin_id}', status_code=204, dependencies=[Depends(private)])
def unpin(pin_id: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    with sessions(request).begin() as session:
        session.execute(delete(pins).where(pins.c.learner_id == identity.learner_id, pins.c.id == str(pin_id)))
