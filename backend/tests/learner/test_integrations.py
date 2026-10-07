import asyncio
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from pydantic import ValidationError

from app.learner import (
    ConceptStateRequest, EvidenceSubmissionRequest, LearnerEngine, LearnerContextRequest,
    ResolveLearningContextRequest, ConceptResolutionRequest, InvalidEvidenceError,
    ConceptNotFoundError,
)
from app.learner.assessment import AssessmentObservations, GradedQuestion, LearnerAssessmentAdapter
from app.learner.calibration import CalibrationRequest
from app.learner.evaluation import Prediction, evaluate_predictions
from app.learner.repositories import PostgresLearnerRepository
from testing.postgres import PostgresSandbox
from app.rag.learner_scope import resolve_retrieval_scope


class LearnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.repo = self.db.repository
        self.now = datetime.now(timezone.utc)
        self.engine = LearnerEngine(self.repo, clock=lambda: self.now)
        self.context = self.engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', name='Databases', activate=True))
        self.concepts = [self.engine.register_concept(f'Normal Form {i}') for i in range(5)]
        for concept in self.concepts:
            self.engine.link_context_concept('e2ba227d-7165-5d43-91db-f7185326e0c4', self.context.context_id, concept.id)

    def question(self, index=0, **kwargs):
        return GradedQuestion(question_id=f'q{index}', concept_ids=[self.concepts[index].id],
                              score=3, max_score=4, difficulty=0.6, independence=1, **kwargs)

    def observations(self, **kwargs):
        return AssessmentObservations(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', assessment_id='assessment',
                  context_id=self.context.context_id, occurred_at=self.now,
                  questions=[self.question()], **kwargs)

    def test_assessment_results_atomic_and_idempotent(self):
        adapter = LearnerAssessmentAdapter(self.engine)
        request = self.observations()
        first = adapter.submit(request)
        self.assertTrue(first[0].accepted)
        self.assertEqual(adapter.submit(request)[0].status, 'duplicate')
        evidence = self.repo.get_evidence(first[0].evidence_id, 'e2ba227d-7165-5d43-91db-f7185326e0c4')
        self.assertEqual(evidence.metadata['question_id'], 'q0')
        self.assertEqual(evidence.result, 'PARTIAL')
        invalid = request.model_copy(update={'assessment_id': 'invalid', 'questions': [
            self.question(1), self.question(2).model_copy(update={'concept_ids': ['missing']})]})
        with self.assertRaises(ConceptNotFoundError):
            adapter.submit(invalid)
        self.assertFalse(self.repo.list_evidence('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concepts[1].id))

    def test_ocr_and_calibration_consumer_contracts(self):
        adapter = LearnerAssessmentAdapter(self.engine)
        response = adapter.submit(self.observations(source_type='HANDWRITTEN_ASSESSMENT'))
        self.assertEqual(response[0].status, 'pending')
        targets = adapter.calibration(CalibrationRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', context_id=self.context.context_id,
                                     self_reported_level=1))
        self.assertEqual(len(targets), 4)
        self.assertLess(targets[0].difficulty, targets[-1].difficulty)
        self.assertFalse(self.repo.list_states('e2ba227d-7165-5d43-91db-f7185326e0c4'))
        request = self.observations(source_type='CALIBRATION').model_copy(update={'assessment_id': 'calibration'})
        self.assertTrue(adapter.submit(request)[0].accepted)

    def test_langchain_tools_bound_identity_and_provenance(self):
        from app.langchain.learner_tools import create_learner_tools, ObservationProvenance

        tools = {t.name: t for t in create_learner_tools(self.engine, 'e2ba227d-7165-5d43-91db-f7185326e0c4')}
        self.assertNotIn('record_learning_evidence', tools)
        packet = tools['get_relevant_learner_context'].invoke({'query': 'normal form', 'max_concepts': 2})
        self.assertEqual(len(packet['concepts']), 2)
        self.assertEqual(len(tools['get_active_learning_contexts'].invoke({})['contexts']), 1)
        with self.assertRaises(ValidationError):
            tools['get_relevant_learner_context'].invoke({'query': 'normal form', 'learner_id': '6ce0b50e-09c7-5bc6-8ee3-f35d969ac429'})
        provenance = ObservationProvenance(source_type='CHAT', source_id='chat:turn:1', occurred_at=self.now,
                    context_id=self.context.context_id, evidence_confidence=0.9)
        mutation = {t.name: t for t in create_learner_tools(self.engine, 'e2ba227d-7165-5d43-91db-f7185326e0c4', provenance=provenance)}['record_learning_evidence']
        result = mutation.invoke({'concept_id': self.concepts[0].id, 'result': 'CORRECT'})
        self.assertTrue(result['accepted'])
        with self.assertRaises(ValidationError):
            mutation.invoke({'concept_id': self.concepts[0].id, 'result': 'CORRECT', 'mastery': 1})

    def test_rag_scope_dormancy_filter_and_identity(self):
        request = LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='normal form')
        scope = resolve_retrieval_scope(self.engine, request)
        self.assertEqual(scope.context_ids, [self.context.context_id])
        conditions = scope.qdrant_filter().must
        self.assertEqual(conditions[0].match.value, 'e2ba227d-7165-5d43-91db-f7185326e0c4')
        self.assertEqual(conditions[1].match.any, [self.context.context_id])
        self.engine.resolve_learning_context(ResolveLearningContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', name='Python', activate=True))
        generic = resolve_retrieval_scope(self.engine, LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='What should I study?'))
        self.assertNotIn(self.context.context_id, generic.context_ids)
        explicit = resolve_retrieval_scope(self.engine, request)
        self.assertIn(self.context.context_id, explicit.context_ids)

    def test_chat_accepts_compact_packet_without_provider_changes(self):
        from langchain_core.messages import AIMessage
        from app.langchain.chat_service import ChatService

        class Model:
            async def ainvoke(inner, messages):
                inner.messages = messages
                return AIMessage(content='answer')

        model = Model()
        class Factory:
            def get_model(self):
                return model

        packet = self.engine.get_relevant_context(LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='normal form', max_concepts=2))
        answer = asyncio.run(ChatService(Factory()).reply([('user', 'Help me')], learner_context=packet))
        self.assertEqual(answer, 'answer')
        self.assertIn(self.concepts[0].id, model.messages[0].content)
        self.assertNotIn(self.concepts[-1].id, model.messages[0].content)

    def test_constant_time_ingestion_uses_replay_only_for_old_observations(self):
        request = EvidenceSubmissionRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concepts[0].id,
                  source_type='QUIZ', source_id='1', result='CORRECT', occurred_at=self.now)
        self.engine.submit_evidence(request)
        with patch.object(PostgresLearnerRepository, 'accepted_evidence', side_effect=AssertionError('unneeded replay')):
            self.engine.submit_evidence(request.model_copy(update={'source_id': '2'}))
        self.engine.submit_evidence(request.model_copy(update={'source_id': '3', 'occurred_at': self.now - timedelta(days=1)}))
        state = self.engine.get_concept_state(ConceptStateRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concepts[0].id))
        self.assertEqual(state.evidence_count, 3)

    def test_corrections_preserve_history_without_double_counting(self):
        request = EvidenceSubmissionRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concepts[0].id,
                  source_type='QUIZ', source_id='1', result='INCORRECT', occurred_at=self.now,
                  item_id='correction-item', difficulty=0.8, independence=1)
        first = self.engine.submit_evidence(request)
        corrected = request.model_copy(update={'source_id': '1:corrected', 'result': 'CORRECT',
                                               'supersedes_evidence_id': first.evidence_id})
        self.engine.submit_evidence(corrected)
        self.assertEqual(self.repo.get_evidence(first.evidence_id, 'e2ba227d-7165-5d43-91db-f7185326e0c4').result, 'INCORRECT')
        self.assertEqual(self.repo.get_decision(first.evidence_id, 'e2ba227d-7165-5d43-91db-f7185326e0c4')['status'], 'SUPERSEDED')
        state = self.engine.get_concept_state(ConceptStateRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concepts[0].id))
        self.assertEqual(state.evidence_count, 1)
        self.assertGreater(state.mastery, 0.5)
        with self.assertRaises(InvalidEvidenceError):
            self.engine.submit_evidence(corrected.model_copy(update={'source_id': 'illegal'}))
        correction_id = self.repo.find_evidence_by_source('e2ba227d-7165-5d43-91db-f7185326e0c4', 'QUIZ', '1:corrected', self.concepts[0].id).id
        self.engine.submit_evidence(corrected.model_copy(update={'source_id': '1:revoked', 'result': 'UNKNOWN',
                                    'supersedes_evidence_id': correction_id}))
        state = self.engine.get_concept_state(ConceptStateRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concepts[0].id))
        self.assertEqual(state.evidence_count, 0)
        self.assertIsNone(state.mastery)
        self.assertEqual(state.mastery_policy_version, 'mastery-v2')

    def test_untrusted_semantic_identity_never_accepted(self):
        class Resolver:
            def search(self, *args):
                return []
            def choose(self, *args):
                return 'invented-id', 1.0

        engine = LearnerEngine(self.repo, semantic_resolver=Resolver(), clock=lambda: self.now)
        result = engine.resolve_concept(ConceptResolutionRequest(label='Normal Forms'))
        self.assertEqual(result.status, 'candidate')
        self.assertIsNone(result.concept_id)

    def test_evaluation_metrics_and_invalid_numbers(self):
        metrics = evaluate_predictions([Prediction(0.8, 1), Prediction(0.2, 0)])
        self.assertAlmostEqual(metrics['mae'], 0.2)
        self.assertAlmostEqual(metrics['rmse'], 0.2)
        for value in [float('nan'), float('inf'), -1]:
            with self.assertRaises(ValueError):
                Prediction(value, 1)
            with self.assertRaises(ValidationError):
                EvidenceSubmissionRequest(learner_id='dad56e0e-9630-51f0-a8cb-5dfc3f0b41f4', concept_id='c', source_type='QUIZ', result='CORRECT', difficulty=value)

    def test_application_startup_installs_persistent_learner_facade(self):
        from fastapi.testclient import TestClient
        from app.core.config import Settings
        from app.db import database
        from app.main import create_app

        with (patch.object(database, 'get_engine', return_value=self.db.engine),
              patch('app.main.SentenceTransformerEmbeddingService'), patch('app.main.QdrantVectorStore')):
            application = create_app()
            with TestClient(application):
                learner = application.state.learner_service
                self.assertEqual(learner.get_concept(self.concepts[0].id).id, self.concepts[0].id)
                packet = learner.get_relevant_context(LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='normal form'))
                self.assertEqual(packet.context_ids, [self.context.context_id])

    def test_real_qdrant_filter_excludes_other_students_contexts_and_archived_documents(self):
        from qdrant_client import QdrantClient, models

        client = QdrantClient(':memory:')
        self.addCleanup(client.close)
        client.create_collection('scope', vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
        payload = {'learner_id': 'e2ba227d-7165-5d43-91db-f7185326e0c4', 'learning_context_id': self.context.context_id, 'status': 'ACTIVE'}
        client.upsert('scope', points=[
            models.PointStruct(id=i + 1, vector=[1, 0, 0], payload=item)
            for i, item in enumerate([payload, payload | {'learner_id': '6ce0b50e-09c7-5bc6-8ee3-f35d969ac429'},
                                     payload | {'learning_context_id': '6ce0b50e-09c7-5bc6-8ee3-f35d969ac429'}, payload | {'status': 'ARCHIVED'}])
        ])
        scope = resolve_retrieval_scope(self.engine, LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='normal form'))
        matches = client.query_points('scope', query=[1, 0, 0], query_filter=scope.qdrant_filter()).points
        self.assertEqual([p.id for p in matches], [1])
        empty = scope.model_copy(update={'context_ids': []})
        self.assertFalse(client.query_points('scope', query=[1, 0, 0], query_filter=empty.qdrant_filter()).points)


if __name__ == '__main__':
    unittest.main()
