import json,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from langchain_core.messages import AIMessage
from langchain_core.exceptions import OutputParserException
from app.assessments.schemas import GeneratedAssessmentBatch
from app.langchain.structured_result import candidate,validate,InvalidStructuredAssessment
from app.langchain.generation_recovery import invoke_generated,validate_questions
from app.langchain.prompts import PromptSource
from app.langchain.llm import MentraLLM


def item(number):
    return dict(prompt=f'Which explanation fits case {number}?',marks=1,difficulty=.5,concept_ids=[],
        question_type='mcq',options=[dict(id='a',label='First explanation'),dict(id='b',label='Second explanation')],
        correct_option_id='a',model_answer='First explanation is correct.',rubric='One mark for a.')


class StructuredAssessmentRepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_llm_recovers_a_valid_schema_object_without_another_provider_call(self):
        raw=dict(title='Practice',questions=[item(1)])
        model=SimpleNamespace(ainvoke=AsyncMock(return_value=dict(raw=AIMessage(content=json.dumps(raw)),parsed=None,parsing_error=None)))
        llm=MentraLLM(SimpleNamespace())
        with patch.object(llm,'_model',return_value=model):
            result=await llm.ainvoke(PromptSource.ASSESSMENT_GENERATION,{},output_schema=GeneratedAssessmentBatch)
        self.assertEqual(len(result.questions),1)
        self.assertEqual(model.ainvoke.await_count,1)

    def test_schema_exposes_the_option_bound_and_private_repair_error_is_redacted(self):
        raw=dict(title='Practice',questions=[item(1)])
        raw['questions'][0]['options']=[dict(id=str(i),label=f'Private answer {i}') for i in range(7)]
        with self.assertRaises(InvalidStructuredAssessment) as caught:validate(raw,GeneratedAssessmentBatch,assessment=True)
        self.assertNotIn('Private answer',str(caught.exception))
        self.assertEqual(caught.exception.violations[0]['max_length'],6)
        schema=GeneratedAssessmentBatch.model_json_schema()
        self.assertEqual(schema['$defs']['GeneratedQuestion']['properties']['options']['maxItems'],6)

    def test_strict_recovery_rejects_prose_truncated_output_arrays_and_wrong_tool_calls(self):
        for message in [AIMessage(content='Here is your JSON: {}'),AIMessage(content='[]'),
            AIMessage(content='{}',response_metadata={'finish_reason':'length'}),
            AIMessage(content='{}',tool_calls=[dict(name='OtherTool',args={},id='bad')])]:
            with self.subTest(message=message.content):
                with self.assertRaises(OutputParserException):candidate(message,GeneratedAssessmentBatch)

    def test_duplicate_keys_and_incomplete_tool_output_are_not_recovered(self):
        messages=[AIMessage(content='{"title":"one","title":"two"}'),
            AIMessage(content='',tool_calls=[dict(name='GeneratedAssessmentBatch',args=dict(title='x',questions=[]),id='call')],response_metadata={'finish_reason':'length'})]
        for raw in messages:
            with self.assertRaises(OutputParserException):candidate(raw,GeneratedAssessmentBatch)
        self.assertEqual(candidate(AIMessage(content='```json\r\n{"title":"x"}\r\n```'),GeneratedAssessmentBatch),dict(title='x'))

    async def test_message_invocation_also_recovers_schema_json_in_one_call(self):
        raw=dict(title='Practice',questions=[item(1)])
        model=SimpleNamespace(ainvoke=AsyncMock(return_value=dict(raw=AIMessage(content=json.dumps(raw)),parsed=None,parsing_error=None)))
        llm=MentraLLM(SimpleNamespace())
        with patch.object(llm,'_model',return_value=model):
            result=await llm.ainvoke_messages(PromptSource.ASSESSMENT_GENERATION,[],output_schema=GeneratedAssessmentBatch)
        self.assertEqual(len(result.questions),1)
        self.assertEqual(model.ainvoke.await_count,1)

    async def test_only_the_invalid_item_is_replaced_and_every_item_is_revalidated(self):
        raw=dict(title='Original title',questions=[item(1),item(2),item(3)])
        raw['questions'][1]['options']=[dict(id=str(i),label=f'Option {i}') for i in range(7)]
        try:validate(raw,GeneratedAssessmentBatch,assessment=True)
        except InvalidStructuredAssessment as error:invalid=error
        replacement=GeneratedAssessmentBatch(title='Repair title',questions=[item('replacement')])
        llm=SimpleNamespace(ainvoke=AsyncMock(side_effect=[invalid,replacement]))
        plan=[dict(question_type='mcq',answer_mode='single_choice',marks=1) for _ in range(3)]
        def check(result):validate_questions(result,count=3,question_format='mcq',concepts=None,tokens=set(),grounded=False,previous=[],plan=plan)
        result=await invoke_generated(llm,PromptSource.ASSESSMENT_GENERATION,dict(count=3,question_format='mcq',question_plan=plan),
            output_schema=GeneratedAssessmentBatch,validate=check)
        self.assertEqual(result.title,'Original title')
        self.assertEqual(result.questions[0].model_dump(),GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[raw['questions'][0]])).questions[0].model_dump())
        self.assertEqual(result.questions[2].prompt,raw['questions'][2]['prompt'])
        payload=llm.ainvoke.call_args.args[1]
        self.assertEqual((payload['count'],payload['repair_positions']),(1,[2]))
        self.assertEqual(len(payload['previous_prompts']),2)
        self.assertEqual(llm.ainvoke.await_count,2)

    async def test_a_bad_replacement_cannot_escape_full_batch_validation(self):
        from app.core.exceptions import AppError
        raw=dict(title='Practice',questions=[item(1),item(2)])
        raw['questions'][1]['options']=[dict(id=str(i),label=f'Option {i}') for i in range(7)]
        try:validate(raw,GeneratedAssessmentBatch,assessment=True)
        except InvalidStructuredAssessment as error:invalid=error
        llm=SimpleNamespace(ainvoke=AsyncMock(side_effect=[invalid,GeneratedAssessmentBatch(title='Repair',questions=[item(1)])]))
        plan=[dict(question_type='mcq',answer_mode='single_choice',marks=1)]*2
        def check(result):validate_questions(result,count=2,question_format='mcq',concepts=None,tokens=set(),grounded=False,previous=[],plan=plan)
        with self.assertRaises(AppError):
            await invoke_generated(llm,PromptSource.ASSESSMENT_GENERATION,dict(count=2,question_format='mcq',question_plan=plan),output_schema=GeneratedAssessmentBatch,validate=check)
