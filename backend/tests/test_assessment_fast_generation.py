"""One content call on the real workflow; custom structure and identity stay safe."""
import unittest
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select, func
from app.assessments.schemas import GenerationRequest, AssessmentIntent
from app.langchain.prompts import PromptSource
from app.langchain.assessment_selection import resolve_assessment_intent
from app.learner.schemas import GeneratedConceptsRequest
from app.learner.repositories.tables.evidence import learning_evidence
from tests import test_assessment_flexibility as fixtures


class FastGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixtures.FlexibleEngineTests.setUp(self)
        from app.langchain.concept_identity import ConceptIdentityResolver
        self.learner.generated_concepts.resolver = ConceptIdentityResolver(self.service.workflows.llm)

    async def test_standard_five_questions_use_one_content_call_and_one_independent_key_check(self):
        request = GenerationRequest(client_request_id=uuid4(), context_id=self.context.context_id,
            topic='New skill topic', count=5, question_format='mcq')
        with patch.object(self.service.workflows.llm, 'ainvoke', wraps=self.service.workflows.llm.ainvoke) as calls:
            value = await self.service.generate(self.owner, request)
        self.assertEqual(len(value.questions), 5)
        self.assertEqual([call.args[0] for call in calls.await_args_list], [PromptSource.ASSESSMENT_GENERATION,PromptSource.ASSESSMENT_CHOICE_REVIEW])
        self.assertTrue(all(q.validation['semantic_review']=='model_cross_checked' for q in value.questions))
        again = await self.service.generate(self.owner, request.model_copy(update={'client_request_id': uuid4()}))
        self.assertEqual(value.questions[0].concept_ids, again.questions[0].concept_ids)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)), 0)

    async def test_explicit_standard_intent_needs_no_selection_model(self):
        intent = AssessmentIntent(client_request_id=uuid4(), context_id=self.context.context_id,
            topic='A useful topic', count=5)
        with patch.object(self.service.workflows.llm, 'ainvoke', side_effect=AssertionError('No planning model')):
            value = await resolve_assessment_intent(self.service.workflows, self.owner, intent)
        self.assertEqual((value.count, value.question_format, value.result_style), (5, 'mixed', 'marks'))

    async def test_same_label_in_different_subjects_is_never_merged_without_advice(self):
        request = GeneratedConceptsRequest(learner_id=self.owner, context_id=self.context.context_id,
            topic='Python', labels=['Arrays'])
        first = await self.learner.prepare_assessment_concept_labels(request)
        second = await self.learner.prepare_assessment_concept_labels(request.model_copy(update={'topic': 'Java'}))
        self.assertNotEqual(first['Arrays'], second['Arrays'])
        self.assertEqual(first, await self.learner.prepare_assessment_concept_labels(request))

    async def test_custom_structured_paper_keeps_its_designer(self):
        request = GenerationRequest(client_request_id=uuid4(), context_id=self.context.context_id,
            topic='Reasoning', count=2, question_format='mock_paper')
        with patch.object(self.service.workflows.llm, 'ainvoke', wraps=self.service.workflows.llm.ainvoke) as calls:
            value = await self.service.generate(self.owner, request)
        self.assertIsNotNone(value.paper)
        self.assertIn(PromptSource.ASSESSMENT_DESIGN, [call.args[0] for call in calls.await_args_list])
