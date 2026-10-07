import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.learner import (
    ActivateLearningContextRequest, ActiveContextsRequest, ConceptResolutionRequest,
    ConceptStateRequest, ConfirmEvidenceRequest, ContextTransitionRequest,
    EvidenceSubmissionRequest, InvalidEvidenceError, LearnerContextRequest,
    LearnerEngine, LearningContextNotFoundError, ResolveLearningContextRequest,
    StudyRecommendationsRequest, VerificationCandidatesRequest,
)
from app.learner.repositories import PostgresLearnerRepository
from testing.postgres import PostgresSandbox
from sqlalchemy.exc import IntegrityError
from app.learner.scoring import HeuristicMasteryPolicy


class LearnerEngineTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.repository = self.db.repository
        self.now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        self.engine = LearnerEngine(self.repository, clock=lambda: self.now)
        self.concept = self.engine.register_concept('Transitive Dependency', aliases=['TD'])
        self.context = self.engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', name='Database Systems', activate=True))
        self.engine.link_context_concept('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.context.context_id, self.concept.id)

    def observation(self, source_id='question-1', **kwargs):
        data = dict(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', concept_id=self.concept.id,
                    context_id=self.context.context_id, source_type='QUIZ', source_id=source_id, item_id=source_id or None,
                    result='CORRECT', difficulty=0.8, independence=1, occurred_at=self.now)
        data.update(kwargs)
        return EvidenceSubmissionRequest(**data)

    def state(self, concept_id=None):
        return self.engine.get_concept_state(ConceptStateRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7',
                                            concept_id=concept_id or self.concept.id))

    def test_plural_alias_unknown_candidate_and_review(self):
        for label in ['transitive dependencies', ' TD ', 'TRANSITIVE DEPENDENCY']:
            self.assertEqual(self.engine.resolve_concept(ConceptResolutionRequest(label=label)).concept_id, self.concept.id)
        request = ConceptResolutionRequest(label='New Topic', context_id=self.context.context_id, learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7')
        first = self.engine.resolve_concept(request)
        second = self.engine.resolve_concept(request)
        self.assertEqual(first.candidate_id, second.candidate_id)
        self.assertEqual(self.repository.get_candidate(first.candidate_id, learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7')['occurrence_count'], 2)
        new = self.engine.review_candidate(first.candidate_id)
        self.assertEqual(self.engine.resolve_concept(request).concept_id, new.id)

    def test_ambiguous_alias_never_selects_arbitrarily(self):
        other = self.engine.register_concept('Another Concept', aliases=['TD'])
        resolution = self.engine.resolve_concept(ConceptResolutionRequest(label='TD'))
        self.assertEqual(resolution.status, 'ambiguous')
        self.assertIsNone(resolution.concept_id)
        self.assertIn(other.id, resolution.alternatives)

    def test_retries_and_source_conflicts(self):
        request = self.observation()
        first = self.engine.submit_evidence(request)
        second = self.engine.submit_evidence(request)
        self.assertEqual(first.evidence_id, second.evidence_id)
        self.assertEqual(second.status, 'duplicate')
        self.assertEqual(self.state().evidence_count, 1)
        with self.assertRaises(InvalidEvidenceError):
            self.engine.submit_evidence(request.model_copy(update={'result': 'INCORRECT'}))

    def test_ocr_pending_confirmation_replay_and_uncertain_grade(self):
        response = self.engine.submit_evidence(self.observation(source_type='HANDWRITTEN_ASSESSMENT', extraction_confidence=0.2))
        self.assertEqual(response.status, 'pending')
        self.assertIsNone(self.state())
        self.engine.confirm_evidence(ConfirmEvidenceRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', evidence_id=response.evidence_id,
                                     confirmation_source='confirmed-transcription:1'))
        self.assertEqual(self.state().evidence_count, 1)
        original = self.repository.get_evidence(response.evidence_id, 'b9cdd0f0-9119-5d06-a170-103315c7f4e7')
        self.assertEqual(original.extraction_confidence, 0.2)
        self.engine.recompute_learner_state('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id)
        self.assertEqual(self.state().evidence_count, 1)
        uncertain = self.engine.submit_evidence(self.observation(source_id='uncertain', evidence_confidence=0.1))
        with self.assertRaises(InvalidEvidenceError):
            self.engine.confirm_evidence(ConfirmEvidenceRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', evidence_id=uncertain.evidence_id,
                                        confirmation_source='e2ba227d-7165-5d43-91db-f7185326e0c4'))

    def test_unknown_future_and_provenance(self):
        self.engine.submit_evidence(self.observation(result='UNKNOWN'))
        self.assertIsNone(self.state())
        for request in [self.observation(source_id=''), self.observation(occurred_at=self.now + timedelta(days=1))]:
            with self.assertRaises(InvalidEvidenceError):
                self.engine.submit_evidence(request)

    def test_retention_decays_without_mastery_changes(self):
        self.engine.submit_evidence(self.observation())
        first = self.state()
        self.now += timedelta(days=150)
        last = self.state()
        self.assertEqual(first.mastery, last.mastery)
        self.assertLess(last.retention_confidence, first.retention_confidence)
        self.assertEqual(first.version, last.version)

    def test_hints_are_weaker_and_consistent_evidence_increases_confidence(self):
        self.engine.submit_evidence(self.observation(learner_id='5ac6dfbb-895c-55f4-a3f5-02d7625d924d', context_id=None,
                                    independence=0.2, hint_count=3, source_type='CHAT'))
        self.engine.submit_evidence(self.observation())
        first = self.state()
        bob = self.engine.get_concept_state(ConceptStateRequest(learner_id='5ac6dfbb-895c-55f4-a3f5-02d7625d924d', concept_id=self.concept.id))
        self.assertIsNone(bob.mastery)
        self.assertEqual(bob.knowledge_status, 'insufficient_evidence')
        for i in range(12):
            self.now += timedelta(seconds=1)
            self.engine.submit_evidence(self.observation(source_id=f'q{i}'))
        self.assertGreater(self.state().estimate_confidence, first.estimate_confidence)

    def test_contradiction_and_independent_verification(self):
        for i in range(16):
            self.now += timedelta(seconds=1)
            self.engine.submit_evidence(self.observation(source_id=f'q{i}'))
        before = self.state()
        self.now += timedelta(seconds=1)
        response = self.engine.submit_evidence(self.observation(source_id='failure', result='INCORRECT'))
        self.assertTrue(response.verification_required)
        self.assertGreater(self.state().mastery, before.mastery - 0.1)
        candidates = self.engine.get_verification_candidates(VerificationCandidatesRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7'))
        self.assertEqual(candidates[0].reason, 'contradictory_evidence')
        self.now += timedelta(seconds=1)
        self.engine.submit_evidence(self.observation(source_id='verification'))
        self.assertTrue(self.state().verification_required)
        self.engine.submit_evidence(self.observation(source_id='verification-2'))
        self.assertFalse(self.state().verification_required)

    def test_switch_dormancy_and_intentional_cross_context(self):
        self.engine.submit_evidence(self.observation())
        python = self.engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', name='Python', activate=True))
        dictionary = self.engine.register_concept('Python Dictionary')
        self.engine.link_context_concept('b9cdd0f0-9119-5d06-a170-103315c7f4e7', python.context_id, dictionary.id)
        recommendations = self.engine.get_study_recommendations(StudyRecommendationsRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7'))
        self.assertEqual([r.concept_id for r in recommendations], [dictionary.id])
        packet = self.engine.get_relevant_context(LearnerContextRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7',
                           query='Compare Python dictionary and transitive dependency'))
        self.assertIn(self.context.context_id, packet.context_ids)
        self.assertIn(self.concept.id, [c.concept_id for c in packet.concepts])
        self.assertIsNotNone(self.state())
        generic = self.engine.get_relevant_context(LearnerContextRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', query='What should I study?'))
        self.assertNotIn(self.context.context_id, generic.context_ids)
        self.engine.activate_learning_context(ActivateLearningContextRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', context_id=self.context.context_id))
        self.assertEqual(self.engine.get_active_contexts(ActiveContextsRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7')).contexts[0].name, 'Database Systems')

    def test_context_isolation_and_inactivity(self):
        with self.assertRaises(LearningContextNotFoundError):
            self.engine.submit_evidence(self.observation(learner_id='5ac6dfbb-895c-55f4-a3f5-02d7625d924d'))
        self.assertFalse(self.repository.list_evidence('5ac6dfbb-895c-55f4-a3f5-02d7625d924d', self.concept.id))
        self.now += timedelta(days=61)
        self.assertFalse(self.engine.get_active_contexts(ActiveContextsRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7')).contexts)
        self.assertEqual(self.repository.get_context('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.context.context_id).status, 'DORMANT')

    def test_atomic_rollback_and_concurrent_ingestion(self):
        with patch.object(PostgresLearnerRepository, 'save_state', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                self.engine.submit_evidence(self.observation())
        self.assertFalse(self.repository.list_evidence('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i: self.engine.submit_evidence(self.observation(source_id=f'q{i}')), range(20)))
        self.assertEqual(self.state().evidence_count, 20)
        self.assertEqual(self.state().version, 20)
        self.assertEqual(len({r.evidence_id for r in results}), 20)

    def test_recompute_equivalence_and_policy_swap(self):
        for i in range(4):
            self.now += timedelta(seconds=1)
            self.engine.submit_evidence(self.observation(source_id=f'q{i}', result='CORRECT' if i % 2 else 'INCORRECT'))
        before = self.state()
        self.engine.recompute_learner_state('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id)
        after = self.state()
        self.assertEqual(before.model_dump(exclude={'version'}), after.model_dump(exclude={'version'}))
        engine = LearnerEngine(self.repository, clock=lambda: self.now,
                               mastery_policy=replace(HeuristicMasteryPolicy(), version='experimental-v2'))
        engine.recompute_learner_state('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id)
        self.assertEqual(engine.get_concept_state(ConceptStateRequest(
            learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', concept_id=self.concept.id)).mastery_policy_version, 'experimental-v2')
        self.assertEqual(self.state().mastery_policy_version, 'mastery-v2')

    def test_merge_redirect_preserves_provenance_and_deduplicates(self):
        other = self.engine.register_concept('DB Dependency')
        self.engine.submit_evidence(self.observation())
        self.engine.submit_evidence(self.observation(concept_id=other.id))
        self.engine.merge_concepts(other.id, self.concept.id)
        self.assertEqual(self.engine.get_concept(other.id).id, self.concept.id)
        self.assertEqual(self.state().evidence_count, 1)
        self.assertEqual(self.repository.list_evidence('b9cdd0f0-9119-5d06-a170-103315c7f4e7', other.id)[0].concept_id, other.id)
        self.assertEqual(self.engine.submit_evidence(self.observation(concept_id=other.id)).status, 'duplicate')
        self.assertEqual(self.engine.resolve_concept(ConceptResolutionRequest(label='DB Dependency')).concept_id, self.concept.id)
        children = self.engine.split_concept(self.concept.id, ['Partial Dependency', 'Functional Dependency'])
        self.assertTrue(all(self.state(child.id) is None for child in children))

    def test_bounded_packet_and_batched_reads_with_large_history(self):
        for i in range(110):
            concept = self.engine.register_concept(f'Topic {i:03}')
            self.engine.link_context_concept('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.context.context_id, concept.id)
        self.db.connections = 0
        packet = self.engine.get_relevant_context(LearnerContextRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', query='What should I study?', max_concepts=8))
        self.assertEqual(len(packet.concepts), 8)
        self.assertLess(self.db.connections, 35)
        self.assertLess(len(packet.model_dump_json(exclude_none=True)), 6000)

    def test_misconceptions_and_archived_default(self):
        observation = self.engine.record_misconception('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id, 'Confuses dependencies', 0.9)
        packet = self.engine.get_relevant_context(LearnerContextRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', query='transitive dependency'))
        self.assertIn('Confuses dependencies', packet.concepts[0].misconceptions)
        self.engine.resolve_misconception('b9cdd0f0-9119-5d06-a170-103315c7f4e7', observation.id)
        self.assertFalse(self.repository.list_misconceptions('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id))
        self.engine.transition_context_state(ContextTransitionRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', context_id=self.context.context_id, status='ARCHIVED'))
        self.assertFalse(self.engine.get_relevant_context(LearnerContextRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', query='Database systems')).context_ids)
        explicit = self.engine.get_relevant_context(LearnerContextRequest(learner_id='b9cdd0f0-9119-5d06-a170-103315c7f4e7', query='dependency', context_ids=[self.context.context_id]))
        self.assertTrue(explicit.concepts)

    def test_alias_registry_creation_is_idempotent_and_repeated_misconceptions_resolve(self):
        self.assertEqual(self.engine.register_concept('transitive dependencies').id, self.concept.id)
        first = self.engine.record_misconception('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id, 'Confuses dependencies', 0.8)
        second = self.engine.record_misconception('b9cdd0f0-9119-5d06-a170-103315c7f4e7', self.concept.id, 'Confuses dependencies', 0.9)
        self.assertEqual(first.id, second.id)
        self.assertTrue(self.engine.resolve_misconception('b9cdd0f0-9119-5d06-a170-103315c7f4e7', second.id))

    def test_duplicate_concurrent_source_has_one_state_update(self):
        request = self.observation()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.engine.submit_evidence(request), range(8)))
        self.assertEqual(self.state().evidence_count, 1)
        self.assertEqual(self.state().version, 1)
        self.assertEqual(sum(r.status == 'accepted' for r in responses), 1)

    def test_transitive_merge_redirects_and_relations(self):
        middle = self.engine.register_concept('DB Dependency')
        child = self.engine.register_concept('Dependent Topic')
        self.engine.add_concept_relation(middle.id, child.id, 'PREREQUISITE_OF')
        self.engine.submit_evidence(self.observation(concept_id=middle.id))
        self.engine.merge_concepts(middle.id, self.concept.id)
        final = self.engine.register_concept('Canonical Dependency')
        self.engine.merge_concepts(self.concept.id, final.id)
        self.assertEqual(self.engine.get_concept(middle.id).id, final.id)
        self.assertIn(child.id, [c.id for c in self.engine.get_related_concepts(final.id)])
        self.assertEqual(self.state(final.id).evidence_count, 1)


if __name__ == '__main__':
    unittest.main()
