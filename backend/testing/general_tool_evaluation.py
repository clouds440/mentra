"""Offline comparison; run from the repository root.

First archive the reference revision without changing the checkout:
  git archive --format=zip --output=.cache/smart-tools-reference.zip HEAD backend/app backend/testing
  Expand-Archive .cache/smart-tools-reference.zip .cache/smart-tools-reference -Force
Then run this file with the project Python and --check for regression gates.
No paid provider calls are made.
Keep the reference archive tied to the reported HEAD revision.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

QUERIES = [
    'Explain photosynthesis', 'Explain an event loop', 'Define assessment',
    'Rewrite this text: My previous schedule changed today.',
    'Translate this sentence: Remember my old notes.',
    'Debug this code:\nprint("latest news")',
    'Explain my notes', 'Search my Library for Newton laws',
    'What are my saved preferences?', 'Remember that I prefer worked examples.',
    'Find my earlier message about fractions', 'Where did we discuss fractions?',
    'Show my current learning progress', 'What should I study next?',
    'What is my agenda tomorrow?', 'Show my schedule', 'Remind me tomorrow',
    'Research current battery chemistry', 'Check the latest news',
    'Give me 1 question quiz', 'Give me one MCQ on fractions',
]

async def task_costs():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from uuid import UUID
    from langchain_core.messages import AIMessage,HumanMessage,SystemMessage
    from app.langchain.history_orchestration import tool_reply
    from app.langchain.planning import plan_request
    from app.langchain.prompts import get_system_prompt
    from app.langchain.token_policy import count_messages,schema_tokens
    from app.rag.schemas import RetrievalResult
    from app.web_search import WebSearchService
    class Usage:
        def reserve(self,*a,**k):return 'reserved'
        def mark(self,*a,**k):pass
    class Provider:
        async def search(self,*a,**k):return {'results':{'web':[]}}
    rows=[]
    cases=[('Find my earlier message about fractions','history_lookup',dict(query='fractions')),
           ('What are my saved preferences?','user_memory',dict(action='recall',query='preferences')),
           ('What is my agenda tomorrow?','event_lookup',{}),
           ('Explain my notes','search_study_material',dict(query='study notes')),
           ('Check the latest news','web_search',dict(query='latest news'))]
    for query,needed,arguments in cases:
        captured=[]
        class Model:
            async def ainvoke_messages(self,source,messages,**kwargs):
                instructions='\n\n'.join(get_system_prompt(s) for s in (source,*kwargs['additional_sources']))
                captured.append(count_messages([SystemMessage(content=instructions+kwargs['system_context']),*messages])+schema_tokens(kwargs.get('tools')))
                names={getattr(t,'name',getattr(t,'__name__','')) for t in kwargs.get('tools') or []}
                if any(m.type=='tool' and m.name==needed for m in messages):
                    return AIMessage(content='No matching synthetic results were returned.')
                if needed not in names:
                    return AIMessage(content='',tool_calls=[dict(name='enable_workflow_tools',args=dict(tool_names=[needed]),id='discover')])
                return AIMessage(content='',tool_calls=[dict(name=needed,args=arguments,id='lookup')])
        state=dict(current_user_message_id=str(UUID(int=1)),user_sequence=2,current_answer_text=query,
            conversation_id=str(UUID(int=2)),context_rows=[],history_references=[],memory_references=[],
            execution_plan=plan_request(query),learner_service=Mock(),
            rag_service=SimpleNamespace(search=lambda *a:RetrievalResult(status='no_eligible_sources')),
            assessment_service=Mock(),event_proposal_service=Mock())
        service=SimpleNamespace(events=SimpleNamespace(list=lambda *a:dict(items=[],has_more=False)),
            lookup=AsyncMock(return_value=dict(windows=[])),memory=AsyncMock(return_value=dict(memories=[])),
            search_summaries=AsyncMock(return_value=dict(summaries=[])))
        if needed=='web_search':
            state['web_search_service']=WebSearchService(Provider(),Usage(),enabled=True,cache_seconds=0,
                clock=lambda:datetime(2026,10,26,tzinfo=timezone.utc))
        await tool_reply(Model(),[HumanMessage(content=query)],service,str(UUID(int=3)),state,(),{})
        rows.append(dict(query=query,tool=needed,model_rounds=len(captured),
            estimated_total_input=sum(captured),physical_calls=state['_tool_budget'].calls))
    return rows

async def measure():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import Mock
    from uuid import UUID
    from langchain_core.messages import HumanMessage, SystemMessage
    from app.langchain.history_orchestration import tool_reply
    from app.langchain.planning import plan_request
    from app.langchain.prompts import PromptSource,get_system_prompt
    from app.langchain.token_policy import count_messages,schema_tokens
    now=datetime(2026,10,26,tzinfo=timezone.utc)
    web=SimpleNamespace(enabled=True,research=SimpleNamespace(enabled=True),
        envelope=lambda *a,**k:SimpleNamespace(current_date=now.date(),current_datetime=now,reference_timezone='UTC'))
    class Captured(Exception):pass
    async def snapshot(query,enabled):
        plan=plan_request(query)
        captured=[]
        class Model:
            async def ainvoke_messages(self,source,messages,**kwargs):
                captured.append(kwargs);raise Captured()
        state=dict(current_user_message_id=str(UUID(int=1)),user_sequence=2,current_answer_text=query,
            conversation_id=str(UUID(int=2)),context_rows=[],history_references=[],memory_references=[],
            execution_plan=plan,history_token_budget=4096,learner_service=Mock(),rag_service=Mock(),assessment_service=Mock(),event_proposal_service=Mock())
        if enabled:state['web_search_service']=web
        try:await tool_reply(Model(),[HumanMessage(content=query)],SimpleNamespace(events=Mock()),str(UUID(int=3)),state,(),{})
        except Captured:pass
        value=captured[0]
        instructions='\n\n'.join(get_system_prompt(s) for s in (PromptSource.CHAT,*value['additional_sources']))
        return dict(query=query,web_enabled=enabled,tools=[getattr(t,'name',getattr(t,'__name__','')) for t in value['tools']],
            schema_tokens=schema_tokens(value['tools']),estimated_total_input=count_messages([SystemMessage(content=instructions+value['system_context']),HumanMessage(content=query)])+schema_tokens(value['tools']))
    rows=[]
    for enabled in (False,True):
        for query in QUERIES:
            value=await snapshot(query,enabled)
            plan=plan_request(query)
            value['modules']=[step.module for step in plan.steps]
            rows.append(value)
    return rows

if '--child' in sys.argv:
    print(json.dumps(dict(first_requests=asyncio.run(measure()),task_costs=asyncio.run(task_costs()))))
else:
    root=Path.cwd()
    def run(path):
        env=dict(os.environ, PYTHONPATH=str(path), TIKTOKEN_CACHE_DIR=str(root/'backend/.cache/tokenizers'))
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child'],env=env,capture_output=True,text=True,check=True)
        return json.loads(result.stdout)
    before=run(root/'.cache/smart-tools-reference/backend')
    after=run(root/'backend')
    assert len(before['first_requests']) == len(after['first_requests']) == len(QUERIES)*2, 'Incomplete request comparison'
    assert [(x['query'],x['web_enabled']) for x in before['first_requests']] == [(x['query'],x['web_enabled']) for x in after['first_requests']], 'Mismatched request cohorts'
    assert [(x['query'],x['tool']) for x in before['task_costs']] == [(x['query'],x['tool']) for x in after['task_costs']], 'Mismatched complete workflows'
    reference_revision=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    result=dict(method='Synthetic first-request snapshots and scripted read workflows against archived git HEAD and current source. No paid provider calls or real domain persistence.',
        reference_revision=reference_revision,
        results=[dict(query=a['query'],web_enabled=a['web_enabled'],before=b,after=a,input_delta=a['estimated_total_input']-b['estimated_total_input']) for b,a in zip(before['first_requests'],after['first_requests'])],
        task_costs=[dict(query=a['query'],before=b,after=a) for b,a in zip(before['task_costs'],after['task_costs'])])
    result['checks'] = dict(complete_cohorts=True, scripted_workflow_non_regression=all(
        row['after'][metric] <= row['before'][metric]
        for row in result['task_costs'] for metric in ('estimated_total_input','model_rounds','physical_calls')))
    path=root/'docs/General_Tool_Optimization_Evidence_2026-10-26.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if '--check' in sys.argv and not all(result['checks'].values()):
        raise SystemExit('Scripted workflow cost regression; inspect the evidence and validate any quality tradeoff.')
    print(json.dumps(dict(output=str(path),rows=len(result['results']),task_costs=result['task_costs'])))
