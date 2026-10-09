from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.student_profile.dependencies import require_onboarded_identity
from app.learner.schemas import LearnerContextRequest, LearnerContextPacket, StudyRecommendationsRequest, StudyRecommendation, VerificationCandidatesRequest, VerificationCandidate

def private_response(response: Response): response.headers['Cache-Control'] = 'no-store'
router = APIRouter(prefix='/learning', tags=['learning'], dependencies=[Depends(private_response)])

class LearningOverview(BaseModel):
    learner: LearnerContextPacket
    recommendations: list[StudyRecommendation]
    verification: list[VerificationCandidate]

@router.get('', response_model=LearningOverview)
async def overview(request: Request, context_id: str | None = Query(None, min_length=1, max_length=100), identity=Depends(require_onboarded_identity)):
    engine, owner = request.app.state.learner_service, identity.learner_id
    ids = [context_id] if context_id else None
    def read():
        if ids: engine.get_context_summaries(owner, ids)
        return LearningOverview(
            learner=engine.get_relevant_context(LearnerContextRequest(learner_id=owner, query='current learning progress', context_ids=ids, max_concepts=12, include_related=False)),
            recommendations=engine.get_study_recommendations(StudyRecommendationsRequest(learner_id=owner, context_ids=ids, limit=5)),
            verification=engine.get_verification_candidates(VerificationCandidatesRequest(learner_id=owner, context_ids=ids, limit=5)))
    return await run_in_threadpool(read)
