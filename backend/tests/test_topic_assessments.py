import unittest
import asyncio
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock
from sqlalchemy import select, func

from app.core.exceptions import AppError
from app.learner.engine import LearnerEngine
from app.learner.schemas import (GeneratedConceptsRequest, ResolveLearningContextRequest,
    ConceptSearchTerms, ConceptIdentityMatches, ConceptResolutionRequest)
from app.learner.repositories.tables.evidence import learning_evidence
from app.assessments.service import create_assessments
from app.assessments.schemas import StartAttempt, SubmitAnswers
from app.assessments.worker import AssessmentWorker
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.langchain.llm import MentraLLM
from app.langchain.workflow_tools import create_workflow_tools
from app.history_management.budgets import ToolBudget
from testing.history_model import HistoryChatFactory
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class TopicAssessmentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = PostgresSandbox(); self.addCleanup(self.db.close)
        self.owner, self.other = learner_id('alice'), learner_id('bob')
        self.learner = LearnerEngine(self.db.repository)
        self.service = create_assessments(self.db.sessions, MentraLLM(HistoryChatFactory()), self.learner)

    def conversation(self):
        cid = str(uuid4())
        ChatRepository(self.db.sessions).begin_turn(self.owner, SendTurn(conversation_id=cid,
            client_turn_id=uuid4(), expected_revision=0, content='Give me a beginner interactive assessment'))
        return cid

    def request(self, label, context):
        return GeneratedConceptsRequest(learner_id=self.owner, context_id=context.context_id,
            topic=context.name, labels=[label])

    async def test_arbitrary_topic_without_prior_context_concepts_or_assessments(self):
        for topic in ['Programming foundations', 'Introductory optics', 'Beginner gardening']:
            with self.subTest(topic=topic):
                scope = dict(assessment_service=self.service, conversation_id=self.conversation(), current_user_message_id=str(uuid4()))
                tool = next(tool for tool in create_workflow_tools(self.owner, scope, ToolBudget()) if tool.name == 'assessment_generate')
                result = await tool.ainvoke(dict(topic=topic, count=5, question_format='mcq'))
                card = scope['assessment_cards'][0]
                self.assertIsNotNone(result['assessment_id'])
                self.assertEqual(len(card['assessment']['questions']), 5)
                self.assertTrue(all(question['options'] for question in card['assessment']['questions']))
                self.assertNotIn('correct_option_id', str(card))
                self.assertEqual(len({concept for question in card['assessment']['questions'] for concept in question['concept_ids']}), 1)
                replay = await tool.ainvoke(dict(topic=topic, count=5, question_format='mcq'))
                self.assertEqual(result['assessment_id'], replay['assessment_id'])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)), 0)

    async def test_generated_names_can_be_registered_without_student_confirmation_and_graded(self):
        scope = dict(assessment_service=self.service, conversation_id=self.conversation(), current_user_message_id=str(uuid4()))
        tool = next(tool for tool in create_workflow_tools(self.owner, scope, ToolBudget()) if tool.name == 'assessment_generate')
        result = await tool.ainvoke(dict(topic='Python basics', concept_names=['Python variable assignment', 'Python list indexing'], count=2, question_format='mcq'))
        assessment = self.service.repository.detail(self.owner, result['assessment_id'])
        attempt = self.service.repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
        self.service.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(), answers={str(question.id): 'a' for question in assessment.questions}))
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        result = self.service.repository.attempt(self.owner, str(attempt.id))
        self.assertEqual((result.state, result.evidence_status), ('graded', 'applied'))

    async def test_semantic_synonym_reuses_id_and_remembers_alias(self):
        canonical = self.learner.register_concept('Python variable assignment')
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Python'))
        resolver = SimpleNamespace(expand=AsyncMock(return_value=ConceptSearchTerms(terms=['Python variable assignment'])),
            match=AsyncMock(return_value=ConceptIdentityMatches(matches=[dict(label='Binding a name to a value in Python', concept_id=canonical.id, confidence=.97)])))
        self.learner.generated_concepts.resolver = resolver
        request = self.request('Binding a name to a value in Python', context)
        concepts = await self.learner.resolve_generated_concepts(request)
        self.assertEqual([concept.id for concept in concepts], [canonical.id])
        self.assertEqual(self.learner.resolve_concept(ConceptResolutionRequest(label=request.labels[0])).concept_id, canonical.id)
        await self.learner.resolve_generated_concepts(request)
        self.assertEqual(resolver.match.await_count, 1)
        self.assertEqual(len(self.db.repository.list_concepts(10)), 1)

    async def test_related_concept_is_new_and_foreign_id_from_model_is_rejected(self):
        canonical = self.learner.register_concept('Python lists')
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Python'))
        resolver = SimpleNamespace(expand=AsyncMock(return_value=ConceptSearchTerms(terms=['Python lists'])),
            match=AsyncMock(return_value=ConceptIdentityMatches(matches=[dict(label='Python tuples', concept_id=None, confidence=1)])))
        self.learner.generated_concepts.resolver = resolver
        concepts = await self.learner.resolve_generated_concepts(self.request('Python tuples', context))
        self.assertNotEqual(concepts[0].id, canonical.id)
        resolver.match.return_value = ConceptIdentityMatches(matches=[dict(label='Python dictionaries', concept_id=str(uuid4()), confidence=1)])
        with self.assertRaises(AppError) as error:
            await self.learner.resolve_generated_concepts(self.request('Python dictionaries', context))
        self.assertEqual(error.exception.code, 'CONCEPT_INVALID_MATCH')
        self.assertEqual(len(self.db.repository.list_concepts(10)), 2)

    async def test_other_learner_cannot_create_targets_in_an_owned_context_or_chat(self):
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.other, name='Physics'))
        with self.assertRaises(Exception): await self.learner.resolve_generated_concepts(self.request('Optics', context))
        cid = self.conversation()
        with self.assertRaises(AppError): await self.service.generate_chat_from_topic(self.other, cid,
            client_request_id=uuid4(), topic='Other subject')
        self.assertEqual(self.learner.get_context_summaries(self.other)[0].name, 'Physics')

    async def test_equivalent_new_labels_in_one_batch_share_one_id(self):
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Programming'))
        resolver = SimpleNamespace(expand=AsyncMock(), match=AsyncMock(return_value=ConceptIdentityMatches(matches=[
            dict(label='Variable assignment', concept_id=None, confidence=1),
            dict(label='Binding a name to a value', equivalent_label='Variable assignment', confidence=.97)])))
        self.learner.generated_concepts.resolver = resolver
        request = self.request('Variable assignment', context).model_copy(update={'labels':['Variable assignment', 'Binding a name to a value']})
        concepts = await self.learner.resolve_generated_concepts(request)
        self.assertEqual(len(concepts), 1)
        self.assertEqual(len(self.db.repository.list_concepts(10)), 1)
        resolver.expand.assert_not_awaited()
        self.assertEqual(self.learner.resolve_concept(ConceptResolutionRequest(label=request.labels[1])).concept_id, concepts[0].id)

    async def test_concurrent_creation_of_the_same_target_is_idempotent(self):
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Biology'))
        request = self.request('Cell division', context)
        left, right = await asyncio.gather(self.learner.resolve_generated_concepts(request), self.learner.resolve_generated_concepts(request))
        self.assertEqual(left[0].id, right[0].id)
        self.assertEqual(len(self.db.repository.list_concepts(10)), 1)

    async def test_discarded_candidates_are_not_silently_promoted(self):
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Biology'))
        result = self.learner.resolve_concept(ConceptResolutionRequest(learner_id=self.owner, context_id=context.context_id, label='Rejected target'))
        self.learner.review_owned_candidate(self.owner, result.candidate_id, discard=True)
        with self.assertRaises(AppError): await self.learner.resolve_generated_concepts(self.request('Rejected target', context))
        self.assertEqual(self.db.repository.list_concepts(10), [])

    async def test_topic_chat_replays_an_assessment_created_with_legacy_confirmation_flag(self):
        from app.assessments.schemas import GenerationRequest
        canonical = self.learner.register_concept('Cell division')
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Biology'))
        cid = self.conversation()
        request = GenerationRequest(client_request_id=uuid4(), context_id=context.context_id,
            topic='Cell division', concept_names=[canonical.canonical_name], count=2, question_format='mcq', confirm_new_concepts=False)
        legacy = await self.service.generate_chat(self.owner, cid, request)
        replay = await self.service.generate_chat_from_topic(self.owner, cid, client_request_id=request.client_request_id,
            context_id=request.context_id, topic=request.topic, concept_names=request.concept_names,
            count=request.count, question_format=request.question_format)
        self.assertEqual(legacy['assessment_id'], replay['assessment_id'])

    async def test_ambiguous_names_do_not_merge_unrelated_meanings_or_leave_a_confirmation_gate(self):
        left = self.learner.register_concept('Biological models', aliases=['Models'])
        right = self.learner.register_concept('Physical models', aliases=['Models'])
        context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Statistics'))
        concepts = await self.learner.resolve_generated_concepts(self.request('Models', context))
        self.assertNotIn(concepts[0].id, [left.id, right.id])
        self.assertEqual(self.learner.get_pending_concepts(self.owner), [])
