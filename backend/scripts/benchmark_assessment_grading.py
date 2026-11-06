"""Synthetic known-rubric grading through the current API and durable worker.

TEST_DATABASE_URL is mandatory. Provider-backed written cases are opt-in.
Timings exclude idle queue polling; no learner/evidence update is on the result path.
"""
import argparse,asyncio,json,statistics,time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI
from httpx import AsyncClient,ASGITransport
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from testing.files import create_test_files
from app.core.config import settings
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.assessments.schemas import GenerationRequest,GeneratedAssessment,GeneratedQuestion
from app.assessments.service import create_assessments
from app.assessments.worker import AssessmentWorker
from app.api.routes.assessments import router
from app.student_profile.dependencies import require_onboarded_identity

async def main(args):
    owner=learner_id('alice');db=PostgresSandbox();results=[]
    try:
        learner=LearnerEngine(db.repository)
        context=learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=owner,name='Force benchmark'))
        skill=learner.register_concept('Force and acceleration benchmark');learner.link_context_concept(owner,context.context_id,skill.id)
        llm=MentraLLM(ModelFactory(settings));service=create_assessments(db.sessions,llm,learner,files=create_test_files(db.sessions))
        app=FastAPI();app.include_router(router,prefix='/api/v1');app.state.assessment_service=service
        app.dependency_overrides[require_onboarded_identity]=lambda:SimpleNamespace(learner_id=owner)
        calls=[];invoke=llm.ainvoke
        async def track(source,*a,**k):
            start=time.monotonic()
            try:return await invoke(source,*a,**k)
            finally:calls.append(dict(source=source.value,ms=round(1000*(time.monotonic()-start),2)))
        llm.ainvoke=track
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            for kind,count in [('mcq',args.choice_samples),('written',args.written_samples)]:
                if not count:continue
                for index in range(count):
                    qs=[GeneratedQuestion(prompt=f'A {mass} kg block has a net force of {mass*2} N. Calculate its acceleration and show the formula.',
                        concept_ids=[skill.id],marks=2,difficulty=.3,question_type='mcq' if kind=='mcq' else 'short_answer',
                        model_answer='a = F/m = 2 m/s².',rubric='1 mark for a = F/m; 1 mark for 2 m/s². Accept equivalent notation. Wrong acceleration with a correct formula earns 1 mark.',
                        **(dict(options=[dict(id='a',label='2 m/s²'),dict(id='b',label='4 m/s²')],correct_option_id='a') if kind=='mcq' else {})) for mass in (2,3,4,5,6)]
                    request=GenerationRequest(client_request_id=uuid4(),context_id=context.context_id,topic='Net force',count=5)
                    assessment=service.repository.save(owner,request,GeneratedAssessment(title='Known-rubric force benchmark',questions=qs),[])
                    response=await client.post(f'/api/v1/assessments/{assessment.id}/attempts',json=dict(client_request_id=str(uuid4())));response.raise_for_status();attempt=response.json()
                    answer='a' if kind=='mcq' else ('a = F/m = 2 m/s².' if index%3==0 else 'a = F/m, but I obtained 4 m/s².' if index%3==1 else 'Acceleration is 4 m/s².')
                    answers={str(q.id):answer for q in assessment.questions};calls.clear();start=time.monotonic()
                    response=await client.post(f"/api/v1/assessments/attempts/{attempt['id']}/submission",json=dict(client_request_id=str(uuid4()),expected_revision=1,answers=answers,assistance='independent'));response.raise_for_status()
                    await AssessmentWorker(service).run_once()
                    response=await client.get(f"/api/v1/assessments/attempts/{attempt['id']}");response.raise_for_status();result=response.json()
                    expected=10 if kind=='mcq' or index%3==0 else 5 if index%3==1 else 0
                    row=dict(kind=kind,index=index,published_ms=round(1000*(time.monotonic()-start),2),state=result['state'],calls=list(calls),
                        expected_score=expected,observed_score=sum(q['score'] for q in result['grades'] or []),answers_preserved=result['answers']==answers,evidence_status=result['evidence_status'])
                    results.append(row);print(json.dumps(row),flush=True)
                    args.output.write_text(json.dumps(dict(scope=__doc__,samples=results),indent=2),encoding='utf-8')
        summary={}
        for kind in ('mcq','written'):
            values=sorted(row['published_ms'] for row in results if row['kind']==kind)
            if values:summary[kind]=dict(samples=len(values),median_ms=statistics.median(values),p95_ms=values[__import__('math').ceil(.95*len(values))-1])
        report=dict(scope=__doc__,summary=summary,samples=results,quality_scope='Simple synthetic arithmetic rubrics only; not independent educational/grading validation.')
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)
        return 0 if all(row['state']=='graded' and row['answers_preserved'] and row['observed_score']==row['expected_score'] for row in results) else 2
    finally:db.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--choice-samples',type=int,default=30);parser.add_argument('--written-samples',type=int,default=0)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not 0<=args.choice_samples<=100 or not 0<=args.written_samples<=100 or args.choice_samples+args.written_samples==0:parser.error('Choose 1–100 samples per requested path')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    raise SystemExit(asyncio.run(main(args)))
