from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from typing import Literal
from uuid import UUID
from app.student_profile.dependencies import require_onboarded_identity
from app.learner.schemas import LearnerContextRequest, LearnerContextPacket, StudyRecommendation, VerificationCandidate, LearningProgressRequest, LearningProgressPage

def private_response(response: Response): response.headers['Cache-Control'] = 'no-store'
router = APIRouter(prefix='/learning', tags=['learning'], dependencies=[Depends(private_response)])

class LearningOverview(BaseModel):
    learner: LearnerContextPacket
    recommendations: list[StudyRecommendation]
    verification: list[VerificationCandidate]

class ConceptReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['confirm', 'discard']

@router.get('/concept-candidates')
async def pending_concepts(request: Request, identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.learner_service.get_pending_concepts, identity.learner_id)

@router.post('/concept-candidates/{identifier}')
async def review_concept(identifier: UUID, body: ConceptReview, request: Request, identity=Depends(require_onboarded_identity)):
    result = await run_in_threadpool(request.app.state.learner_service.review_owned_candidate,
        identity.learner_id, str(identifier), discard=body.decision=='discard')
    return dict(status='discarded' if result is None else 'confirmed', concept_id=result.id if result else None)

@router.get('', response_model=LearningOverview)
async def overview(request: Request, context_id: str | None = Query(None, min_length=1, max_length=100), identity=Depends(require_onboarded_identity)):
    engine, owner = request.app.state.learner_service, identity.learner_id
    ids = [context_id] if context_id else None
    def read():
        if ids: engine.get_context_summaries(owner, ids)
        targets = engine.get_study_targets(owner, ids, supported_verification=True)
        return LearningOverview(
            learner=engine.get_relevant_context(LearnerContextRequest(learner_id=owner, query='current learning progress', context_ids=ids, max_concepts=12, include_related=False)),
            recommendations=targets['recommendations'], verification=targets['verification'])
    return await run_in_threadpool(read)


@router.get('/understanding', response_model=LearningProgressPage)
async def understanding(request: Request, query: str = Query('', max_length=200),
                        context_id: str | None = Query(None, min_length=1, max_length=100),
                        limit: int = Query(10, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
                        identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(request.app.state.learner_service.get_learning_progress,
        LearningProgressRequest(learner_id=identity.learner_id, query=query,
            context_ids=[context_id] if context_id else None, limit=limit, offset=offset))
