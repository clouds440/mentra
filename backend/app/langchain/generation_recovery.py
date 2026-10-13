"""Bounded repair of generated assessments before any assessment is saved."""
from collections.abc import Callable
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


async def invoke_generated(llm: 'MentraLLM', source: PromptSource, payload: dict, *,
                           output_schema: type[Generated],
                           validate: Callable[[Generated], None] | None = None) -> Generated:
    feedback = None
    for attempt in range(2):
        inputs = dict(payload, repair_feedback=feedback) if feedback else payload
        try:
            result = await llm.ainvoke(source, inputs, output_schema=output_schema)
            if validate:
                validate(result)
            return result
        except (ValidationError, OutputParserException, GenerationMismatch) as error:
            # Do not send rejected values, exception text or private answers back
            # through diagnostic receipts. Every new call uses the shared budget.
            feedback = dict(problem=str(error) if isinstance(error, GenerationMismatch)
                            else 'invalid_structured_output')
            workflow_logger.event('assessment.output_repair', prompt_source=source.value,
                                  attempt=attempt + 1, problem=feedback['problem'])
    raise AppError('ASSESSMENT_INVALID_GENERATION',
                   'This quiz needs another attempt. Please try again.', 502)


def validate_questions(result: GeneratedAssessment, *, count: int, question_format: str,
                       concepts: set[str], tokens: set[str], grounded: bool, previous: list[str]) -> None:
    if len(result.questions) != count:
        raise GenerationMismatch('wrong_question_count')
    seen = {prompt.casefold().strip() for prompt in previous}
    for question in result.questions:
        if bool(question.options) != (question_format == 'mcq'):
            raise GenerationMismatch('wrong_question_format')
        prompt = question.prompt.casefold().strip()
        if prompt in seen:
            raise GenerationMismatch('duplicate_question')
        seen.add(prompt)
        if set(question.concept_ids) - concepts:
            raise GenerationMismatch('unknown_concept_id')
        if set(question.source_tokens) - tokens:
            raise GenerationMismatch('unknown_source_token')
        if grounded and not question.source_tokens:
            raise GenerationMismatch('missing_source_citation')
