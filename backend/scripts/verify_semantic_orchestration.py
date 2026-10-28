"""Configured-model evaluation using real schemas/coordinator and synthetic receipts.

No external tools execute; the only network requests are bounded model invocations.
Run with PYTHONPATH=backend python backend/scripts/verify_semantic_orchestration.py.
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from app.core.config import settings
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.history_orchestration import tool_reply
from app.langchain.workflow_tools import QuickPractice, GeneratePractice, SearchStudy, AnswerPractice
from app.langchain.workflow_tools import create_workflow_tools as actual_workflow_tools
from app.langchain.web_tools import ChatSearchInput
from app.langchain.event_tools import EventLookup
from app.history_management.events.proposals import EventManage
from app.history_management.schemas import HistoryLookup, MemoryToolInput, ConversationSummarySearch
from app.langchain.learner_tools import ContextToolInput, RankingToolInput
from app.langchain.attachment_tools import ReadChatAttachment
from testing.semantic_cases import CASES, CRITICAL

SCHEMAS = {
    'assessment_generate':(QuickPractice,'Create a requested saved quiz/test with native assessment questions; not preference/onboarding questions.'),
    'assessment_generate_advanced':(GeneratePractice,'Create a requested written paper with exact marks, timing and sections.'),
    'assessment_answer':(AnswerPractice,'Prepare or submit verbatim student answers to an existing owned assessment.'),
    'search_study_material':(SearchStudy,'Retrieve cited passages from the learner Library; use for source-only requests.'),
    'web_search':(ChatSearchInput,'Search public external/current facts, with dated sources. Never send private data.'),
    'web_research':(ChatSearchInput,'Research a complex public question with sources.'),
    'get_relevant_learner_context':(ContextToolInput,'Read actual topic progress and weaknesses, not general teaching knowledge.'),
    'get_study_recommendations':(RankingToolInput,'Read learner-data-based practice recommendations.'),
    'event_lookup':(EventLookup,'Read the owned agenda.'),
    'event_manage':(EventManage,'Create/review an actual personal event, supported by an exact user quote. Automatic events is enabled.'),
    'history_lookup':(HistoryLookup,'Retrieve original past conversations by question/query or visible message identity.'),
    'conversation_summary_search':(ConversationSummarySearch,'Find earlier conversations.'),
    'user_memory':(MemoryToolInput,'Recall saved preferences or propose an explicitly requested supported fact.'),
    'read_chat_attachment':(ReadChatAttachment,'Read an earlier visible upload by its attachment ID.'),
}


def tools_for(service, owner, scope, budget):
    tools = []
    actual = {tool.name:tool for tool in actual_workflow_tools(owner,dict(scope,assessment_service=object(),rag_service=object()),budget)}
    for name,(schema,description) in SCHEMAS.items():
        if name in actual: schema,description=actual[name].args_schema,actual[name].description
        async def invoke(_name=name, **arguments):
            scope.setdefault('_probe_calls',[]).append(dict(name=_name,arguments=arguments))
            if _name.startswith('assessment_generate'):
                identifier = str(uuid4())
                scope.setdefault('assessment_cards',[]).append(dict(id=identifier,generation_job_id=identifier,title='Synthetic practice'))
                return dict(outcome='queued',generation_job_id=identifier,title='Synthetic practice')
            if _name == 'event_manage': return dict(outcome='saved',event=dict(id=str(uuid4()),title='Chemistry exam'))
            if _name == 'search_study_material':
                from app.rag.schemas import SourceReference
                source=SourceReference(token='S1',document_id=str(uuid4()),version_id=str(uuid4()),generation_id=str(uuid4()),
                    chunk_id=str(uuid4()),title='Synthetic physics notes',heading_path=[],spans=[],excerpt='Inertia is resistance to a change in velocity.')
                scope['study_sources']=[source]
                return dict(outcome='ok',sources=[source.model_dump(mode='json')])
            if _name.startswith('web_'):
                from app.web_search import SearchResult
                now=datetime.now(timezone.utc)
                return SearchResult(outcome='no_results',current_date=now.date(),current_datetime=now,
                    reference_timezone='UTC',delivered_at=now,searched_at=now).model_dump(mode='json')
            if _name == 'user_memory': return dict(outcome='saved' if arguments.get('action')!='recall' else 'ok',memories=[])
            return dict(outcome='ok',items=[],content='Synthetic fixture: no matching records.' )
        tools.append(StructuredTool.from_function(name=name, description=description,args_schema=schema,coroutine=invoke))
    return tools


async def run_case(case, config, llm=None):
    name,query,previous,required = case
    scope = dict(current_user_message_id=str(uuid4()),conversation_id=str(uuid4()),user_sequence=3,
        context_rows=[],history_references=[],memory_references=[],event_preferences=dict(automatic_events=True,timezone='Asia/Karachi'))
    previous_id=str(uuid4())
    prior_user_id=str(uuid4())
    prior_user='Help me with this exercise.'
    scope['context_rows'] = ([dict(id=prior_user_id,role='user',content=prior_user,metadata={}),dict(id=previous_id,role='assistant',content=previous,metadata={})] if previous else [])+[
        dict(id=scope['current_user_message_id'],role='user',content=query,created_at=datetime(2026,10,28,9,tzinfo=timezone.utc),metadata={'timezone':'Asia/Karachi'})]
    if name=='read_upload': scope['context_rows'].insert(0,dict(id=str(uuid4()),role='user',content='An earlier upload',metadata={'attachments':[dict(id='00000000-0000-0000-0000-000000000099',filename='notes.txt',media_type='text/plain')]}))
    messages = ([HumanMessage(content=prior_user,id=prior_user_id),AIMessage(content=previous,id=previous_id)] if previous else [])+[HumanMessage(content=query,id=scope['current_user_message_id'])]
    usage, rounds = [], []
    llm = llm or MentraLLM(ModelFactory(config))
    class Model:
        async def ainvoke_messages(self,*args,**kwargs):
            started=perf_counter()
            value=await llm.ainvoke_messages(*args,**kwargs)
            usage.append(getattr(value,'usage_metadata',None))
            rounds.append(dict(seconds=round(perf_counter()-started,3),calls=[call['name'] for call in getattr(value,'tool_calls',[])],
                arguments=[call['args'] for call in getattr(value,'tool_calls',[])]))
            return value
    started=perf_counter()
    try:
        reply=await tool_reply(Model(),messages,object(),str(uuid4()),scope,(),{})
        calls=[item['name'] for item in scope.get('_probe_calls',[])]
        calls += [item['operation'] for item in scope.get('_task_receipts',{}).values() if item['operation']=='present_questionnaire']
        forbidden = []
        if not required: forbidden=[call for call in calls if name not in ('ambiguous_edit','no_mastery') or call!='present_questionnaire']
        elif name in ('onboarding','urdu_onboarding','informal'): forbidden=[call for call in calls if call!='present_questionnaire']
        passed=(all(tool in calls for tool in required) if name=='compound' else any(tool in calls for tool in required) if required else not forbidden) and not forbidden
        if name=='fresh': passed=passed and any(item['arguments'].get('refresh') for item in scope.get('_probe_calls',[]) if item['name']=='web_search')
        if name in ('onboarding','urdu_onboarding'): passed=passed and len((scope.get('interactions') or [{}])[0].get('questions',[]))==5
        return dict(name=name,passed=passed,seconds=round(perf_counter()-started,3),rounds=rounds,usage=usage,
            calls=calls,outcome=scope.get('response_outcome'),answer=reply.content)
    except Exception as error:
        return dict(name=name,passed=False,seconds=round(perf_counter()-started,3),rounds=rounds,receipts=scope.get('_task_receipts'),
            invoked=scope.get('_probe_calls'),error=type(error).__name__+': '+str(error)[:240])


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--case')
    parser.add_argument('--output',default='.cache/semantic-model-evaluation.json')
    args=parser.parse_args()
    cases=CASES[:6] if args.smoke else CASES+[case for case in CASES if case[0] in CRITICAL]*2
    if args.case: cases=[case for case in CASES if case[0]==args.case]
    config=settings.model_copy(update={'ai_max_retries':0})
    provider=MentraLLM(ModelFactory(config))
    semaphore=asyncio.Semaphore(2)
    async def evaluate(case):
        async with semaphore:
            result=await run_case(case,config,provider)
            print(json.dumps({key:result[key] for key in ('name','passed','seconds')},ensure_ascii=False),flush=True)
            if not result['passed']: print(json.dumps(result,ensure_ascii=False,default=lambda value:value.model_dump(mode='json')),flush=True)
            return result
    with patch('app.langchain.history_orchestration.create_history_tools',side_effect=tools_for),patch('app.langchain.workflow_tools.create_workflow_tools',return_value=[]):
        results=await asyncio.gather(*(evaluate(case) for case in cases))
    Path(args.output).write_text(json.dumps(dict(policy='semantic-v3',model=settings.ai_model,results=results),ensure_ascii=False,indent=2,
        default=lambda value:value.model_dump(mode='json')),encoding='utf-8')
    print(f'{sum(item["passed"] for item in results)}/{len(results)} episodes passed',flush=True)
    if any(not item['passed'] for item in results): raise SystemExit(1)


if __name__=='__main__': asyncio.run(main())
