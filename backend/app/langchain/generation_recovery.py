"""Bounded repair of generated assessments before any assessment is saved."""
from collections.abc import Callable,Awaitable
from typing import TYPE_CHECKING, TypeVar
from pydantic import BaseModel, ValidationError
from langchain_core.exceptions import OutputParserException
from app.core.exceptions import AppError
from app.core.logging import workflow_logger
from app.assessments.schemas import GeneratedAssessment
from .prompts import PromptSource

if TYPE_CHECKING:
    from .llm import MentraLLM

Generated = TypeVar('Generated', bound=BaseModel)


class GenerationMismatch(ValueError):
    """A server-owned reason for repairing otherwise well-formed output."""
    def __init__(self, problem, **details):
        super().__init__(problem)
        self.details = details


async def invoke_generated(llm: 'MentraLLM', source: PromptSource, payload: dict, *,
                           output_schema: type[Generated],
                           validate: Callable[[Generated], None] | None = None,
                           maximum_attempts: int = 2, output_tokens: int | None = None,
                           review: Callable[[Generated],Awaitable[None]] | None = None) -> Generated:
    feedback = None
    retained = None
    repair_positions = None
    for attempt in range(maximum_attempts):
        result = None
        inputs = dict(payload, repair_feedback=feedback) if feedback else payload
        if retained is not None:
            inputs=dict(inputs,count=len(repair_positions),question_plan=[payload['question_plan'][i] for i in repair_positions],
                repair_positions=[i+1 for i in repair_positions],
                previous_prompts=[q['prompt'] for i,q in enumerate(retained['questions']) if i not in repair_positions])
            if payload.get('original_questions'):
                inputs['original_questions']=[payload['original_questions'][i] for i in repair_positions]
        try:
            result = await llm.ainvoke(source, inputs, output_schema=output_schema,
                **({'output_tokens': output_tokens} if output_tokens is not None else {}))
            if retained is not None:
                if len(result.questions)!=len(repair_positions):raise GenerationMismatch('wrong_repair_count')
                merged=dict(retained,questions=list(retained['questions']))
                for index,question in zip(repair_positions,result.questions):merged['questions'][index]=question.model_dump(mode='json')
                result=output_schema.model_validate(merged)
            if validate:
                validate(result)
            if review:await review(result)
            return result
        except (ValidationError, OutputParserException, GenerationMismatch) as error:
            # Do not send rejected values, exception text or private answers back
            # through diagnostic receipts. Every new call uses the shared budget.
            feedback = dict(problem=str(error) if isinstance(error, GenerationMismatch)
                            else 'invalid_structured_output')
            if isinstance(error, GenerationMismatch):
                feedback.update(error.details)
            from .structured_result import InvalidStructuredAssessment
            if isinstance(error,InvalidStructuredAssessment):feedback['violations']=error.violations
            # Retain schema-valid items from a rejected private batch. Never trim
            # options/keys; ask the model to replace only the invalid items.
            if source is PromptSource.ASSESSMENT_GENERATION:
                raw=error.candidate if isinstance(error,InvalidStructuredAssessment) else result.model_dump(mode='json') if isinstance(result,BaseModel) else None
                if isinstance(raw,dict) and isinstance(raw.get('questions'),list) and len(raw['questions'])==payload.get('count') and len(payload.get('question_plan',[]))==len(raw['questions']):
                    from app.assessments.schemas import GeneratedQuestion
                    invalid=[i-1 for i in error.details.get('question_indices',[]) if isinstance(i,int) and 1<=i<=len(raw['questions'])] if isinstance(error,GenerationMismatch) else []
                    for index,item in enumerate(raw['questions']):
                        try:
                            single=GeneratedAssessment(title='Item check',questions=[GeneratedQuestion.model_validate(item)])
                            validate_questions(single,count=1,question_format=payload.get('question_format','mixed'),
                                concepts=None,tokens={s['token'] for s in payload.get('sources',[])},
                                grounded=bool(payload.get('sources')),previous=[],plan=[payload['question_plan'][index]])
                        except (ValidationError,GenerationMismatch):
                            if index not in invalid:invalid.append(index)
                    if invalid and len(invalid)<len(raw['questions']):
                        retained=raw;repair_positions=invalid
                        feedback.update(problem='repair_invalid_items_only',positions=[i+1 for i in invalid])
                        workflow_logger.event('assessment.localized_repair',retained=len(raw['questions'])-len(invalid),replacements=len(invalid))
            workflow_logger.event('assessment.output_repair', prompt_source=source.value,
                                  attempt=attempt + 1, **feedback)
            if attempt>=1 and retained is None and feedback['problem'] in ('invalid_structured_output','wrong_question_count'):
                break  # A third call is reserved for targeted/semantic repair.
    raise AppError('ASSESSMENT_INVALID_GENERATION',
                   'This quiz needs another attempt. Please try again.', 502)


def validate_questions(result: GeneratedAssessment, *, count: int, question_format: str,
                       concepts: set[str] | None, tokens: set[str], grounded: bool, previous: list[str], plan=None, require_attribution=False) -> None:
    if len(result.questions) != count:
        raise GenerationMismatch('wrong_question_count')
    seen = {prompt.casefold().strip() for prompt in previous}
    for index, question in enumerate(result.questions):
        from app.assessments.quality import check_question
        try:check_question(question, planned_context=plan[index].get('context','') if plan else '')
        except GenerationMismatch as error:
            raise GenerationMismatch(str(error),**dict(error.details,question_index=index+1)) from None
        expected = plan[index]['question_type'] if plan else question_format
        choice = plan[index].get('answer_mode') in ('single_choice', 'multiple_choice') if plan and 'answer_mode' in plan[index] else expected in ('mcq', 'true_false')
        if bool(question.options) != choice:
            raise GenerationMismatch('wrong_question_format', question_index=index+1,
                expected_type=expected, expected_answer_mode=plan[index].get('answer_mode') if plan else 'single_choice' if choice else 'text',
                actual_option_count=len(question.options),
                correction='Provide options and a private key for a choice item; provide no options or choice keys for text. Follow this plan entry, not the overall mixed format.')
        if plan and plan[index].get('answer_mode') and question.answer_mode != plan[index]['answer_mode']:
            raise GenerationMismatch('answer_mode_must_match_the_question_plan')
        if expected == 'true_false' and (len(question.options)!=2 or {option.id for option in question.options} != {'true', 'false'}):
            raise GenerationMismatch('true_false_requires_true_and_false_options')
        if plan and 'marks' in plan[index] and question.marks != plan[index]['marks']:
            raise GenerationMismatch('marks_must_match_the_paper_plan')
        prompt = question.prompt.casefold().strip()
        if plan: prompt += '|' + plan[index].get('context', '').casefold().strip()
        if prompt in seen:
            raise GenerationMismatch('duplicate_question')
        seen.add(prompt)
        if concepts is not None and set(question.concept_ids) - concepts:
            raise GenerationMismatch('unknown_concept_id')
        if require_attribution and not question.concept_ids:
            raise GenerationMismatch('use_supplied_target_concept_ids')
        if set(question.source_tokens) - tokens:
            raise GenerationMismatch('unknown_source_token')
        if grounded and not question.source_tokens:
            raise GenerationMismatch('missing_source_citation')
