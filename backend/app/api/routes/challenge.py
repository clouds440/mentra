from fastapi import APIRouter,Depends,Request,Query,Response
from starlette.concurrency import run_in_threadpool
from app.student_profile.dependencies import require_onboarded_identity
from app.challenge.schemas import ChallengeControl
from app.challenge.repositories.controls import page,change

def private(response:Response):response.headers['Cache-Control']='no-store'
router=APIRouter(prefix='/learner/challenge-preferences',tags=['learning'],dependencies=[Depends(private)])

@router.get('')
async def preferences(request:Request,after:str=Query('',max_length=64),limit:int=Query(20,ge=1,le=50),
        identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(page,request.app.state.assessment_service.repository,identity.learner_id,after,limit)

@router.post('')
async def update_preferences(body:ChallengeControl,request:Request,identity=Depends(require_onboarded_identity)):
    return await run_in_threadpool(change,request.app.state.assessment_service.repository,identity.learner_id,body)
