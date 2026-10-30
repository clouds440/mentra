"""Offline controlled full-regeneration versus scoped-revision comparison."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from langchain_core.messages import SystemMessage, HumanMessage
from app.assessments.schemas import GenerationRequest, GeneratedAssessmentBatch, AssessmentDesign
from app.langchain.assessment_workflows import AssessmentWorkflows
from app.langchain.prompts import get_system_prompt
from app.langchain.token_policy import count_messages


async def measure(reuse):
    original_questions=[dict(question_type='mcq',prompt=f'Original fractions question {i}',concept_ids=['accepted'],
        context='',difficulty=.4,marks=1,options=[dict(id='a',label='One'),dict(id='b',label='Two')],
        correct_option_id='a',model_answer='One',rubric='Award 1 mark only for a.') for i in range(1,21)]
    original=dict(title='Fractions',context_id='context',paper=None,preferences={},questions=original_questions)
    request=GenerationRequest(client_request_id=uuid4(),context_id='context',topic='Fractions',count=20,question_format='mcq',
        revision_draft_id=uuid4(),revision_instructions='Make question 2 clearer',instructions='Make question 2 clearer',
        revision_question_numbers=['2'] if reuse else [])
    calls=[]
    class Model:
        async def ainvoke(self,source,payload,**kwargs):
            tokens=count_messages([SystemMessage(content=get_system_prompt(source)),HumanMessage(content=json.dumps(payload,default=str))])
            tokens+=count_messages([HumanMessage(content=json.dumps(kwargs['output_schema'].model_json_schema()))])
            if source.value=='assessment_design':
                result=AssessmentDesign(title='Fractions',sections=[dict(title='Practice',question_count=20,question_type='mcq',part_marks=[1])])
            else:
                result=GeneratedAssessmentBatch(title='Fractions revised',questions=[dict(original_questions[0],
                    prompt=f'Revised fractions question {payload["question_offset"]+index+1}') for index in range(payload['count'])])
            calls.append(dict(stage=source.value,estimated_input_tokens=tokens,
                estimated_output_tokens=count_messages([HumanMessage(content=result.model_dump_json())]),questions=payload.get('count',0)))
            return result
    async def no_resolution(*args): raise AssertionError('Accepted concepts should be reused')
    learner=SimpleNamespace(get_context_summaries=lambda *a:[],get_study_targets=lambda *a:dict(recommendations=[],verification=[]),
        get_concepts=lambda ids:{key:SimpleNamespace(canonical_name='Fractions') for key in ids},
        get_relevant_context=lambda *a:SimpleNamespace(model_dump=lambda **k:{}),resolve_generated_concepts=no_resolution)
    workflow=AssessmentWorkflows(Model(),learner)
    if reuse:
        result,_=await workflow.generate(str(uuid4()),request,revision=original)
    else:
        with patch('app.assessments.revision.reusable_revision',return_value=None):
            result,_=await workflow.generate(str(uuid4()),request,revision=original)
    return dict(model_calls=len(calls),estimated_input_tokens=sum(c['estimated_input_tokens'] for c in calls),
        estimated_output_tokens=sum(c['estimated_output_tokens'] for c in calls),generated_questions=sum(c['questions'] for c in calls if c['stage']=='assessment_generation'),
        final_question_count=len(result.questions),calls=calls)


async def main():
    before,after=await measure(False),await measure(True)
    assert after['final_question_count']==before['final_question_count']==20
    assert after['generated_questions']==1 and after['model_calls']<before['model_calls']
    assert after['estimated_input_tokens']<before['estimated_input_tokens'] and after['estimated_output_tokens']<before['estimated_output_tokens']
    report=dict(method='Synthetic same-source controlled workflow comparison. Local tokenizer estimates include prompts, payloads and output schema. No paid calls or database persistence. Excludes chat routing and network/persistence latency.',before=before,after=after)
    path=Path('docs/orchestration/verification/Followup_Edit_Optimization_Evidence_2026-10-27.json')
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__': asyncio.run(main())
