from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from typing import Literal
from uuid import UUID
from app.student_profile.dependencies import require_onboarded_identity
from app.learner.schemas import LearnerContextRequest, LearnerContextPacket, StudyRecommendation, VerificationCandidate, LearningProgressRequest, LearningProgressPage
from app.learner.schemas import ProgressExplanation

def private_response(response: Response): response.headers['Cache-Control'] = 'no-store'
router = APIRouter(prefix='/learning', tags=['learning'], dependencies=[Depends(private_response)])

class LearningOverview(BaseModel):
    learner: LearnerContextPacket
    recommendations: list[StudyRecommendation]
    verification: list[VerificationCandidate]


def read_overview(engine, owner, context_id=None):
    ids = [context_id] if context_id else None
    if ids:
        engine.get_context_summaries(owner, ids)
    targets = engine.get_study_targets(owner, ids, supported_verification=True)
    return LearningOverview(
        learner=engine.get_relevant_context(LearnerContextRequest(learner_id=owner,
            query='current learning progress', context_ids=ids, max_concepts=12, include_related=False)),
        recommendations=targets['recommendations'], verification=targets['verification'])


@router.get('/page')
async def progress_page(request: Request, context_id: str | None = Query(None, min_length=1, max_length=100),
                        identity=Depends(require_onboarded_identity)):
    def read():
        with request.app.state.learner_service.read_scope() as engine:
            owner = identity.learner_id
            return dict(overview=read_overview(engine, owner, context_id),
                contexts=sorted(engine.get_context_summaries(owner), key=lambda value: value.context_id),
                candidates=engine.get_pending_concepts(owner),
                understanding=engine.get_learning_progress(LearningProgressRequest(learner_id=owner,
                    context_ids=[context_id] if context_id else None, limit=10)))
    return await run_in_threadpool(read)

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
    def read():
        with request.app.state.learner_service.read_scope() as engine:
            return read_overview(engine, identity.learner_id, context_id)
    return await run_in_threadpool(read)


@router.get('/understanding', response_model=LearningProgressPage)
async def understanding(request: Request, query: str = Query('', max_length=200),
                        context_id: str | None = Query(None, min_length=1, max_length=100),
                        limit: int = Query(10, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
                        identity=Depends(require_onboarded_identity)):
    def read():
        with request.app.state.learner_service.read_scope() as engine:
            return engine.get_learning_progress(LearningProgressRequest(learner_id=identity.learner_id,
                query=query, context_ids=[context_id] if context_id else None, limit=limit, offset=offset))
    return await run_in_threadpool(read)


@router.get('/understanding/{identifier}', response_model=ProgressExplanation)
async def explanation(identifier: UUID, request: Request,
        context_id: str | None = Query(None, min_length=1, max_length=100),
        identity=Depends(require_onboarded_identity)):
    def read():
        value = request.app.state.learner_service.get_progress_explanation(identity.learner_id, str(identifier), context_id)
        references = [(str(item.assessment_id), str(item.attempt_id), item.grade_revision)
            for item in value.recent_evidence if item.assessment_id and item.attempt_id]
        available = request.app.state.assessment_service.repository.available_evidence_sources(identity.learner_id, references)
        return value.model_copy(update={'recent_evidence': [item.model_copy(update={'source_available':
            (str(item.assessment_id), str(item.attempt_id), item.grade_revision) in available}) for item in value.recent_evidence]})
    return await run_in_threadpool(read)
