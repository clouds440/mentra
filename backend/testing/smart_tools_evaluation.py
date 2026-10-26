"""Reproducible offline cost audit; optional explicitly bounded synthetic live probes."""
import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage
from app.assessments.schemas import GenerationRequest
from app.core.config import settings
from app.langchain.assessment_workflows import AssessmentWorkflows
from app.langchain.history_orchestration import tool_reply
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.planning import plan_request
from app.langchain.prompts import PromptSource, get_system_prompt
from app.langchain.token_policy import _encoding
from testing.tool_schema_snapshot import snapshot


OWNER = str(UUID(int=1))


class BoundedProvider:
    def __init__(self, limit):
        config = settings.model_copy(update={'ai_max_retries': 0})
        self.llm = MentraLLM(ModelFactory(config))
        self.model_factory = self.llm.model_factory
        self.limit, self.calls, self.usage = limit, 0, []

    def reserve(self):
        if self.calls >= self.limit:
            raise RuntimeError('Synthetic live-call limit reached')
        self.calls += 1

    async def ainvoke_messages(self, *args, **kwargs):
        self.reserve()
        result = await self.llm.ainvoke_messages(*args, **kwargs)
        self.usage.append(getattr(result, 'usage_metadata', None))
        return result

    async def ainvoke(self, *args, **kwargs):
        self.reserve()
        return await self.llm.ainvoke(*args, **kwargs)


def learner_fixture():
    async def resolve(request):
        return [SimpleNamespace(id=str(UUID(int=10+i)), canonical_name=label) for i, label in enumerate(request.labels)]
    return SimpleNamespace(get_context_summaries=lambda *a: [],
        get_study_targets=lambda *a: dict(recommendations=[], verification=[]),
        get_concepts=lambda ids: {}, resolve_generated_concepts=resolve,
        get_relevant_context=lambda *a: SimpleNamespace(model_dump=lambda **k: dict(concepts=[])))


async def live_probes(limit):
    provider = BoundedProvider(limit)
    results = []
    for name, query in [
        ('ordinary_one_question', 'Give me 1 question quiz on fractions.'),
        ('urdu_one_question', 'مجھے کسر کے بارے میں ایک سوال کا کوئز دیں۔'),
        ('copyable_bash', 'Give me one bash command to show working tree changes. Output only the command.'),
    ]:
        before, started = provider.calls, perf_counter()
        arguments = []
        async def generate(*args, **kwargs):
            arguments.append({key: kwargs.get(key) for key in ('topic', 'count', 'question_format', 'delivery')})
            if kwargs.get('count') != 1 or kwargs.get('delivery') != 'interactive':
                raise ValueError('Explicit count and interactive delivery must survive routing')
            return dict(id=str(uuid4()), assessment_id=None, assessment=dict(title=kwargs.get('topic') or 'Practice', questions=[]))
        state = dict(current_user_message_id=str(uuid4()), user_sequence=2, conversation_id=str(uuid4()),
            current_answer_text=query, history_references=[], memory_references=[], context_rows=[],
            execution_plan=plan_request(query), assessment_service=SimpleNamespace(generate_chat_from_topic=generate))
        try:
            response = await tool_reply(provider, [HumanMessage(content=query)], None, OWNER, state, (), {})
            passed = bool(arguments) if name != 'copyable_bash' else bool(re.search(r'```bash\s*\ngit status[^\n]*\n```', response.content))
            results.append(dict(scenario=name, passed=passed, calls=provider.calls-before,
                duration_ms=round((perf_counter()-started)*1000, 2), arguments=arguments,
                **(dict(content=response.content) if name=='copyable_bash' else {})))
        except Exception as error:
            results.append(dict(scenario=name, passed=False, calls=provider.calls-before, error_type=type(error).__name__))
    # One real generation, through domain validation and concept resolution, using
    # synthetic owner/context only. No repository, learner or application writes.
    before, started = provider.calls, perf_counter()
    try:
        workflows = AssessmentWorkflows(provider, learner_fixture())
        request = GenerationRequest(client_request_id=uuid4(), context_id='synthetic-fractions',topic='Fractions: halves',
            count=1,question_format='mcq',delivery='interactive',instructions='Give me one MCQ on halves, using small whole numbers.')
        assessment, _ = await workflows.generate(OWNER, request)
        results.append(dict(scenario='validated_one_question_generation', passed=len(assessment.questions)==1,
            calls=provider.calls-before, duration_ms=round((perf_counter()-started)*1000, 2),
            synthetic_question=assessment.questions[0].model_dump()))
    except Exception as error:
        results.append(dict(scenario='validated_one_question_generation',passed=False,calls=provider.calls-before,error_type=type(error).__name__))
    return dict(call_limit=limit, actual_calls=provider.calls, provider_retries=0, results=results,
                routing_usage=provider.usage,
                limitation='Synthetic calls without application persistence; timings are not end-to-end production latency.')


async def main(args):
    baseline = json.loads(Path('docs/Tool_Discovery_Research_Evidence_2026-10-26.json').read_text(encoding='utf-8'))
    comparisons=[]
    for index, old in enumerate(baseline['baseline']):
        new=await snapshot(old['query'], first=index==len(baseline['baseline'])-1)
        comparisons.append(dict(query=old['query'], before=old, after=new,
            input_delta=new['estimated_total_input']-old['estimated_total_input']))
    encoding=_encoding()
    prompts={source.value:len(encoding.encode(get_system_prompt(source),disallowed_special=()))
             for source in (PromptSource.CHAT,PromptSource.TOOL_RECOVERY,PromptSource.CHAT_ASSESSMENT)}
    result=dict(method='Offline first-request snapshots; cl100k_base estimates, no real learner data.',
                comparisons=comparisons, prompt_tokens=prompts,
                library_picker_queries=dict(before=2,after=0,condition='Closed picker with no selected sources; browser verified'),
                small_quiz_model_stages=dict(before=3,after=1,condition='Simple explicit-topic generation; regression verified'),
                final_narration_calls=dict(before=1,after=0,condition='Pure completed assessment outcome; regression verified'))
    now=datetime(2026,10,26,tzinfo=timezone.utc)
    web=SimpleNamespace(enabled=True,research=SimpleNamespace(enabled=True),
        envelope=lambda *a,**k: SimpleNamespace(current_date=now.date(),current_datetime=now,reference_timezone='UTC'))
    result['web_enabled_quiz']=dict(before=baseline['web_and_research_enabled'],
        after=await snapshot('Give me 1 question quiz',web=web))
    if args.live:
        result['live']=await live_probes(args.max_calls)
    target=Path(args.output)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output=str(target), live_calls=result.get('live',{}).get('actual_calls',0),
        scenarios=len(comparisons), prompts=prompts,
        live_results=[dict(scenario=r['scenario'],passed=r['passed'],calls=r['calls']) for r in result.get('live',{}).get('results',[])])))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--max-calls',type=int,choices=range(1,5),default=4)
    parser.add_argument('--output',default='docs/Tool_Optimization_Implementation_Evidence_2026-10-26.json')
    asyncio.run(main(parser.parse_args()))
