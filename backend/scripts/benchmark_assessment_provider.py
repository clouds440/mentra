"""Live configured provider, synthetic students, isolated PostgreSQL only."""
import argparse,asyncio, json, time, statistics
from pathlib import Path
from fastapi import FastAPI
from httpx import AsyncClient,ASGITransport
from types import SimpleNamespace
from app.api.routes.assessments import router
from app.student_profile.dependencies import require_onboarded_identity
from uuid import uuid4
from app.core.config import settings
from app.langchain.model_factory import ModelFactory
from app.langchain.llm import MentraLLM
from app.langchain.concept_identity import ConceptIdentityResolver
from app.learner import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.assessments.schemas import AssessmentIntent
from app.assessments.service import create_assessments
from app.assessments.generation_worker import AssessmentGenerationWorker
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from testing.files import create_test_files

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--samples',type=int,default=30)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--private-corpus',action='store_true',help='Also save private generated keys for independent review; protect this directory')
args=parser.parse_args()
if not 1<=args.samples<=1000:parser.error('--samples must be 1–1000')
mode,samples='current-api',args.samples
output=args.output;output.mkdir(parents=True,exist_ok=True)
result = dict(mode=mode, provider=settings.ai_model, database='isolated local PostgreSQL', samples=[])
topics = ['Net force and acceleration: introductory physics',
          'Python list concatenation and indexing: introductory programming',
          'الحروف العربية: تمييز أشكال الباء والتاء والثاء للمبتدئين']

async def main():
    factory = ModelFactory(settings)
    factory.validate_configuration()
    for index in range(samples):
        db = PostgresSandbox()
        try:
            owner = learner_id('alice')
            llm = MentraLLM(factory)
            learner = LearnerEngine(db.repository, generated_concept_resolver=ConceptIdentityResolver(llm))
            context = learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=owner,name=topics[index%3]))
            service = create_assessments(db.sessions,llm,learner,files=create_test_files(db.sessions))
            app=FastAPI();app.include_router(router,prefix='/api/v1');app.state.assessment_service=service;app.state.learner_service=learner
            app.dependency_overrides[require_onboarded_identity]=lambda:SimpleNamespace(learner_id=owner)
            client=AsyncClient(transport=ASGITransport(app=app),base_url='http://test')
            calls = []
            original = llm.ainvoke
            async def observe(source,*args,**kwargs):
                start=time.monotonic()
                try: return await original(source,*args,**kwargs)
                finally: calls.append(dict(source=source.value,elapsed_ms=round((time.monotonic()-start)*1000,2)))
            llm.ainvoke = observe
            row = dict(index=index,language='Arabic' if index%3==2 else 'English')
            start=time.monotonic()
            try:
                response=await client.post('/api/v1/assessments/generation-jobs',json=AssessmentIntent(client_request_id=uuid4(),context_id=context.context_id,topic=topics[index%3],count=5,question_format='mcq').model_dump(mode='json'));response.raise_for_status();job=response.json()
                await AssessmentGenerationWorker(service).run_once()
                response=await client.get('/api/v1/assessments/generation-jobs/'+job['id']);response.raise_for_status();completed=response.json()
                row.update(elapsed_ms=round((time.monotonic()-start)*1000,2),state=completed['state'],calls=calls)
                if completed['state']=='completed':
                    row['questions']=len(completed['result'].get('assessment',completed['result'])['questions'])
                    assert completed['hydration']['version']==1 and 'attempt' in completed['hydration']
                    assert 'model_answer' not in json.dumps(completed) and 'correct_option_id' not in json.dumps(completed)
                    if index==0:(output/'ui-real-provider-handoff.json').write_text(json.dumps(completed,ensure_ascii=False),encoding='utf-8')
                    if args.private_corpus:
                        artifact=service.repository.revision_source(owner,completed['result'].get('assessment',completed['result'])['id'])
                        (output/f'provider-{mode}-sample-{index}.json').write_text(json.dumps(artifact,ensure_ascii=False,default=str),encoding='utf-8')
                else: row['failure']=completed.get('error')
            except Exception as error:
                row.update(elapsed_ms=round((time.monotonic()-start)*1000,2),state='error',error_type=type(error).__name__,calls=calls)
            result['samples'].append(row)
            (output/f'provider-{mode}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            print(json.dumps(row,ensure_ascii=False),flush=True)
        finally:
            if 'client' in locals():await client.aclose()
            db.close()
    passed=[r['elapsed_ms'] for r in result['samples'] if r['state']=='completed']
    if passed:
        passed.sort()
        result.update(median_ms=statistics.median(passed),p95_ms=passed[max(0,__import__('math').ceil(.95*len(passed))-1)],maximum_ms=max(passed))
    (output/f'provider-{mode}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    asyncio.run(main())
    raise SystemExit(0 if all(row['state']=='completed' and len(row['calls'])==1 and row['questions']==5 for row in result['samples']) else 2)
