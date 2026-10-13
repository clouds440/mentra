import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from app.core.exceptions import AppError
from app.langchain.generation_recovery import invoke_generated, validate_questions, GenerationMismatch
from app.langchain.concept_identity import ConceptIdentityResolver
from app.langchain.prompts import PromptSource
from app.learner.schemas import ConceptSearchTerms
from app.learner.exceptions import ConceptAssistanceUnavailable
from app.assessments.schemas import GeneratedAssessment


class GenerationRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_output_repairs_once_without_exposing_rejected_values(self):
        try:
            ConceptSearchTerms.model_validate({'terms':[''], 'unexpected':'private text'})
        except Exception as error:
            invalid = error
        llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=[invalid, ConceptSearchTerms(terms=['Training'])]))
        result = await invoke_generated(llm, PromptSource.ASSESSMENT_TARGETS,
            {'topic':'AI basics'}, output_schema=ConceptSearchTerms)
        self.assertEqual(result.terms, ['Training'])
        self.assertEqual(llm.ainvoke.await_count, 2)
        payload = llm.ainvoke.call_args.args[1]
        self.assertEqual(payload['repair_feedback'], {'problem':'invalid_structured_output'})
        self.assertNotIn('private text', str(payload))

    async def test_persistent_bad_output_is_bounded_and_not_an_argument_error(self):
        try:
            ConceptSearchTerms.model_validate({'terms':['']})
        except Exception as error:
            invalid = error
        llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=invalid))
        with self.assertRaises(AppError) as caught:
            await invoke_generated(llm, PromptSource.ASSESSMENT_TARGETS, {}, output_schema=ConceptSearchTerms)
        self.assertEqual(caught.exception.code, 'ASSESSMENT_INVALID_GENERATION')
        self.assertEqual(llm.ainvoke.await_count, 2)

    async def test_budget_and_cancellation_are_not_retried_or_swallowed(self):
        for error in (AppError('AI_WORKFLOW_BUDGET', 'Budget reached.', 422), asyncio.CancelledError()):
            llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=error))
            with self.assertRaises(type(error)):
                await invoke_generated(llm, PromptSource.ASSESSMENT_TARGETS, {}, output_schema=ConceptSearchTerms)
            self.assertEqual(llm.ainvoke.await_count, 1)
        resolver = ConceptIdentityResolver(SimpleNamespace(ainvoke=AsyncMock(side_effect=asyncio.CancelledError())))
        with self.assertRaises(asyncio.CancelledError): await resolver.expand(['Models'], 'AI')

    async def test_advice_failure_becomes_optional_domain_error(self):
        resolver = ConceptIdentityResolver(SimpleNamespace(ainvoke=AsyncMock(side_effect=TimeoutError())))
        with self.assertRaises(ConceptAssistanceUnavailable): await resolver.expand(['Models'], 'AI')

    def test_question_constraints_still_block_invalid_grading_and_provenance(self):
        args = dict(title='AI', questions=[dict(prompt='What is training?', concept_ids=['training'],
            difficulty=.3, marks=1, options=[dict(id='a',label='Learning from data'),dict(id='b',label='Deleting data')],
            correct_option_id='a', model_answer='Learning from data', rubric='Choose A')])
        result = GeneratedAssessment(**args)
        options = dict(count=1, question_format='mcq', concepts={'training'}, tokens=set(), grounded=False, previous=[])
        validate_questions(result, **options)
        for updates, expected in [({'count':2},'wrong_question_count'), ({'question_format':'written'},'wrong_question_format'),
                ({'concepts':set()},'unknown_concept_id'), ({'grounded':True},'missing_source_citation'),
                ({'previous':['WHAT IS TRAINING?']},'duplicate_question')]:
            with self.assertRaises(GenerationMismatch) as caught: validate_questions(result, **dict(options, **updates))
            self.assertEqual(str(caught.exception), expected)
        result.questions[0].source_tokens = ['invented']
        with self.assertRaises(GenerationMismatch): validate_questions(result, **options)
