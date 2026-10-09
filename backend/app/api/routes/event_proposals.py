from uuid import UUID
from fastapi import APIRouter, Request, Depends, Response
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.history_management.events.proposals import ProposalDecision, EventProposal

def private_response(response: Response): response.headers['Cache-Control'] = 'no-store'
router = APIRouter(prefix='/event-proposals', tags=['event proposals'], dependencies=[Depends(private_response)])

@router.get('', response_model=list[EventProposal])
async def proposals(request: Request, conversation_id: UUID | None = None, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.event_proposal_service.list, identity.learner_id, str(conversation_id) if conversation_id else None)

@router.get('/{identifier}', response_model=EventProposal)
async def detail(identifier: UUID, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.event_proposal_service.detail, identity.learner_id, str(identifier))

@router.post('/{identifier}/decisions', response_model=EventProposal)
async def decide(identifier: UUID, body: ProposalDecision, request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.event_proposal_service.decide, identity.learner_id, str(identifier), body)
