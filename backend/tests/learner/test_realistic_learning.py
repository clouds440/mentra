"""Synthetic end-to-end regressions through the real persistent facade."""

import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from app.learner import (
    LearnerEngine, EvidenceSubmissionRequest, ConceptStateRequest, LearningGoalRequest,
    PerformancePredictionRequest, ResolveLearningContextRequest, LearnerContextRequest,
    StudyRecommendationsRequest, ContextTransitionRequest, ConceptResolutionRequest,
    InvalidEvidenceError, ConfirmEvidenceRequest,
)
from app.learner.assessment import AssessmentObservations, GradedQuestion, ConceptGrade, LearnerAssessmentAdapter
from app.learner.repositories import PostgresLearnerRepository
from testing.postgres import PostgresSandbox
from sqlalchemy.exc import IntegrityError
from app.learner.scoring import HeuristicMasteryPolicy
from app.learner.evaluation import evaluate_observations


class RealisticLearningTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.repo = self.db.repository
        self.now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        self.engine = LearnerEngine(self.repo, clock=lambda: self.now)
        self.concept = self.engine.register_concept('Transitive Dependency')
        self.context = self.engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', name='Databases', activate=True))
        self.engine.link_context_concept('e2ba227d-7165-5d43-91db-f7185326e0c4', self.context.context_id, self.concept.id)
        self.serial = 0

    def observation(self, **changes):
        self.serial += 1
        values = dict(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concept.id, context_id=self.context.context_id,
                      source_type='QUIZ', source_id=f'answer:{self.serial}', item_id=f'item:{self.serial}',
                      session_id=f'session:{self.serial}', difficulty=0.8, independence=1,
                      result='CORRECT', occurred_at=self.now)
        values.update(changes)
        return EvidenceSubmissionRequest(**values)

    def submit(self, **changes):
        return self.engine.submit_evidence(self.observation(**changes))

    def state(self, concept_id=None):
        return self.engine.get_concept_state(ConceptStateRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=concept_id or self.concept.id))

    def predict(self, difficulty=0.8):
        return self.engine.predict_performance(PerformancePredictionRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concept.id, difficulty=difficulty))

    def assessment(self, revision=1, **changes):
        values = dict(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', assessment_id='exam', revision=revision,
                      context_id=self.context.context_id, occurred_at=self.now,
                      questions=[GradedQuestion(question_id='q', concept_ids=[self.concept.id],
                                  score=0, max_score=1, difficulty=0.8, independence=1)])
        values.update(changes)
        return AssessmentObservations(**values)

    def test_current_skill_changes_both_directions_without_erasing_history(self):
        for _ in range(100):
            self.submit()
        before = self.state()
        self.assertEqual(before.knowledge_status, 'demonstrated')
        self.submit(result='INCORRECT')
        self.assertGreater(self.state().mastery, before.mastery - 0.1)
        self.assertTrue(self.state().verification_required)
        for _ in range(19):
            self.submit(result='INCORRECT')
        self.assertLess(self.state().mastery, 0.25)
        self.assertLess(self.predict().expected_score, 0.25)
        self.assertEqual(len(self.repo.list_evidence('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id)), 120)
        for _ in range(25):
            self.submit()
        self.assertGreater(self.state().mastery, 0.75)
        self.assertGreater(self.predict().expected_score, 0.85)
        self.assertFalse(self.state().verification_required)

    def test_easy_and_guided_successes_do_not_imply_advanced_knowledge(self):
        for _ in range(100):
            self.submit(source_type='CHAT', difficulty=0.1, independence=0, hint_count=5)
        self.assertIsNone(self.state().mastery)
        self.assertFalse(self.predict().supported)
        for _ in range(20):
            self.submit(difficulty=0.1)
        self.assertLess(self.state().mastery, 0.5)
        self.assertTrue(self.predict(0.1).supported)
        self.assertGreater(self.predict(0.1).expected_score, 0.9)
        self.assertFalse(self.predict(0.8).supported)
        self.assertEqual(self.predict(0.8).lower_bound, 0)
        self.assertLess(self.state().recommended_difficulty, 0.4)
        recommendation = self.engine.get_study_recommendations(StudyRecommendationsRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4'))[0]
        self.assertEqual(recommendation.reason, 'difficulty_unverified')
        self.assertEqual(recommendation.recommended_difficulty, 0.5)

    def test_unknown_assistance_and_difficulty_stay_unknown_until_demonstrated(self):
        self.submit(independence=None)
        self.assertIsNone(self.state().hint_dependency)
        self.submit(difficulty=None)
        self.submit(attempt_number=2)
        self.assertIsNone(self.state().mastery)
        self.assertEqual(self.state().independent_item_count, 0)
        for _ in range(6):
            self.submit()
        self.assertGreater(self.state().mastery, 0.7)
        self.assertTrue(self.predict().supported)

    def test_reused_item_and_chat_do_not_establish_broad_certainty(self):
        for _ in range(80):
            self.submit(item_id='memorized-question')
        self.assertEqual(self.state().independent_item_count, 1)
        self.assertLess(self.state().estimate_confidence, 0.2)
        self.assertFalse(self.predict().supported)
        for _ in range(80):
            self.submit(learner_id='38660dce-847a-50dc-a681-ab9844d49d51', context_id=None, source_type='CHAT')
        chat = self.engine.get_concept_state(ConceptStateRequest(learner_id='38660dce-847a-50dc-a681-ab9844d49d51', concept_id=self.concept.id))
        self.assertLessEqual(chat.estimate_confidence, 0.55)
        self.assertNotEqual(chat.knowledge_status, 'demonstrated')

    def test_challenge_matched_verification_requires_two_new_items(self):
        for _ in range(20):
            self.submit()
        self.submit(result='INCORRECT')
        anchor = self.state().last_demonstrated_at
        self.now += timedelta(days=10)
        self.submit(difficulty=0.1)
        self.assertTrue(self.state().verification_required)
        self.assertEqual(self.state().last_demonstrated_at, anchor)
        self.submit(item_id='probe')
        self.assertTrue(self.state().verification_required)
        self.submit(item_id='probe')
        self.assertTrue(self.state().verification_required)
        self.submit(result='INCORRECT')
        self.submit()
        self.assertTrue(self.state().verification_required)
        self.submit()
        self.assertFalse(self.state().verification_required)

    def test_spaced_recall_differs_from_one_mass_exam_and_failures_do_not_refresh(self):
        start = self.now - timedelta(days=19)
        for i in range(20):
            self.submit(learner_id='f26196a7-d649-52d4-9488-5916a6d89345', context_id=None, occurred_at=start + timedelta(days=i))
            self.submit()
        self.now += timedelta(days=30)
        spaced = self.engine.get_concept_state(ConceptStateRequest(learner_id='f26196a7-d649-52d4-9488-5916a6d89345', concept_id=self.concept.id))
        self.assertGreater(spaced.retention_confidence, self.state().retention_confidence)
        anchor = self.state().last_demonstrated_at
        retention = self.state().retention_confidence
        mastery = self.state().mastery
        self.submit(result='INCORRECT')
        self.assertEqual(self.state().last_demonstrated_at, anchor)
        self.assertLess(self.state().retention_confidence, retention)
        self.assertNotEqual(self.state().mastery, mastery)

    def test_recent_easy_activity_does_not_refresh_old_hard_prediction(self):
        for _ in range(8):
            self.submit()
        initial = self.predict()
        self.now += timedelta(days=180)
        self.submit(difficulty=0.1)
        current = self.predict()
        self.assertLess(current.expected_score, initial.expected_score)
        self.assertLess(abs(current.expected_score - 0.5), 0.02)
        self.assertGreater(current.upper_bound - current.lower_bound, 0.95)

    def test_easy_review_preserves_demonstrated_hard_skills_but_hard_failures_revise_them(self):
        for _ in range(20):
            self.submit()
        mastery = self.state().mastery
        prediction = self.predict()
        for _ in range(80):
            self.submit(difficulty=0.1)
        self.assertAlmostEqual(self.state().mastery, mastery)
        self.assertAlmostEqual(self.predict().expected_score, prediction.expected_score)
        self.assertTrue(self.predict(0.1).supported)
        for _ in range(20):
            self.submit(result='INCORRECT')
        self.assertLess(self.predict().expected_score, 0.25)
        self.assertLess(self.state().mastery, 0.5)

    def test_grade_revisions_replace_auto_and_retries_preserve_one_effective_observation(self):
        adapter = LearnerAssessmentAdapter(self.engine)
        first = adapter.submit(self.assessment())[0]
        correct = self.assessment(2, questions=[GradedQuestion(question_id='q', concept_ids=[self.concept.id],
                    score=1, max_score=1, difficulty=0.8, independence=1)])
        second = adapter.submit(correct)[0]
        self.assertEqual(adapter.submit(correct)[0].status, 'duplicate')
        self.assertEqual(self.repo.get_evidence(second.evidence_id, 'e2ba227d-7165-5d43-91db-f7185326e0c4').supersedes_evidence_id, first.evidence_id)
        self.assertEqual(self.state().evidence_count, 1)
        self.assertEqual(self.repo.get_evidence(first.evidence_id, 'e2ba227d-7165-5d43-91db-f7185326e0c4').result, 'INCORRECT')
        with self.assertRaises(InvalidEvidenceError):
            self.submit(item_id=self.repo.get_evidence(second.evidence_id, 'e2ba227d-7165-5d43-91db-f7185326e0c4').item_id,
                        session_id='exam', item_revision=1)

    def test_pending_revision_cannot_overwrite_new_grade_and_confirmation_is_retry_safe(self):
        adapter = LearnerAssessmentAdapter(self.engine)
        adapter.submit(self.assessment(source_type='HANDWRITTEN_ASSESSMENT', questions=[
            GradedQuestion(question_id='q', concept_ids=[self.concept.id], score=0, max_score=1,
                           difficulty=0.8, independence=1, extraction_confidence=1)]))
        pending = adapter.submit(self.assessment(2, source_type='HANDWRITTEN_ASSESSMENT'))[0]
        confirmed = ConfirmEvidenceRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', evidence_id=pending.evidence_id, confirmation_source='review:1')
        self.engine.confirm_evidence(confirmed)
        self.assertEqual(self.engine.confirm_evidence(confirmed).status, 'duplicate')
        pending3 = adapter.submit(self.assessment(3, source_type='HANDWRITTEN_ASSESSMENT'))[0]
        adapter.submit(self.assessment(4, source_type='HANDWRITTEN_ASSESSMENT', questions=[
            GradedQuestion(question_id='q', concept_ids=[self.concept.id], score=1, max_score=1,
                           difficulty=0.8, independence=1, extraction_confidence=1)]))
        with self.assertRaises(InvalidEvidenceError):
            self.engine.confirm_evidence(confirmed.model_copy(update={'evidence_id': pending3.evidence_id}))
        self.assertEqual(self.state().evidence_count, 1)
        self.assertGreater(self.state().mastery, 0.5)

    def test_same_item_session_cannot_double_count_under_another_source(self):
        request = self.observation()
        self.engine.submit_evidence(request)
        with self.assertRaises(InvalidEvidenceError):
            self.engine.submit_evidence(request.model_copy(update={'source_id': 'different-grader'}))
        self.assertEqual(self.state().evidence_count, 1)
        self.engine.submit_evidence(request.model_copy(update={'source_id': 'retry-attempt', 'attempt_number': 2}))
        self.assertEqual(self.state().evidence_count, 2)
        self.assertEqual(self.state().independent_item_count, 1)

    def test_multi_concept_rubric_attributes_strength_and_weakness_separately(self):
        other = self.engine.register_concept('Functional Dependency')
        adapter = LearnerAssessmentAdapter(self.engine)
        with self.assertRaises(ValidationError):
            GradedQuestion(question_id='ambiguous', concept_ids=[self.concept.id, other.id],
                           score=1, max_score=2, difficulty=0.8, independence=1)
        questions = [GradedQuestion(question_id=f'q{i}', concept_ids=[self.concept.id, other.id],
                     score=1, max_score=2, difficulty=0.8, independence=1,
                     concept_grades={self.concept.id: ConceptGrade(score=1, max_score=1),
                                     other.id: ConceptGrade(score=0, max_score=1)}) for i in range(8)]
        adapter.submit(self.assessment(questions=questions))
        self.assertGreater(self.state().mastery, 0.75)
        self.assertLess(self.state(other.id).mastery, 0.1)
        self.assertEqual(self.state().evidence_count, 8)
        self.assertEqual(self.state(other.id).evidence_count, 8)

    def test_per_concept_challenge_prevents_inflated_basic_component_mastery(self):
        other = self.engine.register_concept('Basic Dependency')
        questions = [GradedQuestion(question_id=f'q{i}', concept_ids=[self.concept.id, other.id],
                    score=2, max_score=2, difficulty=0.8, independence=1,
                    concept_grades={self.concept.id: ConceptGrade(score=1, max_score=1, difficulty=0.8),
                                    other.id: ConceptGrade(score=1, max_score=1, difficulty=0.1)}) for i in range(12)]
        LearnerAssessmentAdapter(self.engine).submit(self.assessment(questions=questions))
        self.assertGreater(self.state().mastery, 0.8)
        self.assertLess(self.state(other.id).mastery, 0.5)
        self.assertEqual(self.state(other.id).difficulty_tested, 0.1)

    def test_stale_explicit_revision_and_cross_item_correction_are_rejected(self):
        first = self.submit()
        original = self.repo.get_evidence(first.evidence_id, 'e2ba227d-7165-5d43-91db-f7185326e0c4')
        updated = self.observation(item_id=original.item_id, session_id=original.session_id,
                                   item_revision=3, result='INCORRECT')
        newer = self.engine.submit_evidence(updated)
        with self.assertRaises(InvalidEvidenceError):
            self.engine.submit_evidence(updated.model_copy(update={'source_id': 'late:2', 'item_revision': 2,
                                       'supersedes_evidence_id': newer.evidence_id}))
        with self.assertRaises(InvalidEvidenceError):
            self.submit(supersedes_evidence_id=newer.evidence_id)
        self.assertEqual(self.state().evidence_count, 1)

    def test_normal_large_multi_concept_exam_remains_atomic(self):
        other = self.engine.register_concept('Functional Dependency')
        questions = [GradedQuestion(question_id=f'q{i}', concept_ids=[self.concept.id, other.id],
                    score=2, max_score=2, difficulty=0.5, independence=1,
                    concept_grades={c: ConceptGrade(score=1, max_score=1) for c in [self.concept.id, other.id]})
                    for i in range(75)]
        self.assertEqual(len(LearnerAssessmentAdapter(self.engine).submit(self.assessment(questions=questions))), 150)
        self.assertEqual(self.state().evidence_count, 75)

    def test_goal_importance_changes_priority_and_excludes_explicit_zero(self):
        other = self.engine.register_concept('Normalization')
        self.engine.link_context_concept('e2ba227d-7165-5d43-91db-f7185326e0c4', self.context.context_id, other.id)
        for concept, importance in [(self.concept, 1), (other, 0.1)]:
            self.engine.set_learning_goal(LearningGoalRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', context_id=self.context.context_id,
                                          concept_id=concept.id, importance=importance, target_difficulty=0.8))
        ranked = self.engine.get_study_recommendations(StudyRecommendationsRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4'))
        self.assertEqual(ranked[0].concept_id, self.concept.id)
        self.assertGreater(ranked[0].priority, ranked[1].priority)
        self.engine.set_learning_goal(LearningGoalRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', context_id=self.context.context_id,
                                      concept_id=self.concept.id, importance=0))
        self.assertEqual([r.concept_id for r in self.engine.get_study_recommendations(
            StudyRecommendationsRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4'))], [other.id])

    def test_query_relevance_beats_alphabetical_limit_and_recovers_plural_dormant_topic(self):
        concepts = [self.engine.register_concept(f'Normal Form {i}') for i in range(25)]
        for concept in concepts:
            self.engine.link_context_concept('e2ba227d-7165-5d43-91db-f7185326e0c4', self.context.context_id, concept.id)
        packet = self.engine.get_relevant_context(LearnerContextRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='Explain Normal Form 24', max_concepts=1))
        self.assertEqual(packet.concepts[0].concept_id, concepts[24].id)
        self.engine.transition_context_state(ContextTransitionRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', context_id=self.context.context_id, status='DORMANT'))
        self.engine.resolve_learning_context(ResolveLearningContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', name='Python', activate=True))
        packet = self.engine.get_relevant_context(LearnerContextRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='Explain transitive dependencies', max_concepts=1))
        self.assertEqual(packet.context_ids, [self.context.context_id])
        self.assertEqual(packet.concepts[0].concept_id, self.concept.id)
        self.assertEqual(packet.concepts[0].relevance, 1)

    def test_unowned_archived_and_weak_graph_links_are_excluded(self):
        for index, status in enumerate(['unowned', 'ARCHIVED', 'weak']):
            concept = self.engine.register_concept(f'Related {index}')
            context = self.engine.resolve_learning_context(ResolveLearningContextRequest(
                learner_id='6ce0b50e-09c7-5bc6-8ee3-f35d969ac429' if status == 'unowned' else 'e2ba227d-7165-5d43-91db-f7185326e0c4', name=status))
            self.engine.link_context_concept('6ce0b50e-09c7-5bc6-8ee3-f35d969ac429' if status == 'unowned' else 'e2ba227d-7165-5d43-91db-f7185326e0c4', context.context_id, concept.id)
            if status == 'ARCHIVED':
                self.engine.transition_context_state(ContextTransitionRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', context_id=context.context_id, status=status))
            self.engine.add_concept_relation(self.concept.id, concept.id, 'RELATED_TO', 0.4 if status == 'weak' else 1)
        packet = self.engine.get_relevant_context(LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='transitive dependency'))
        self.assertEqual([c.concept_id for c in packet.concepts], [self.concept.id])

    def test_foreign_prerequisites_and_historical_activity_do_not_inflate_relevance(self):
        foreign = self.engine.register_concept('Foreign Advanced Topic')
        context = self.engine.resolve_learning_context(ResolveLearningContextRequest(learner_id='6ce0b50e-09c7-5bc6-8ee3-f35d969ac429', name='Other'))
        self.engine.link_context_concept('6ce0b50e-09c7-5bc6-8ee3-f35d969ac429', context.context_id, foreign.id)
        self.engine.add_concept_relation(self.concept.id, foreign.id, 'PREREQUISITE_OF')
        self.assertEqual(self.repo.prerequisite_counts([self.concept.id], [self.context.context_id], 'e2ba227d-7165-5d43-91db-f7185326e0c4'), {})
        activity = self.repo.get_context('e2ba227d-7165-5d43-91db-f7185326e0c4', self.context.context_id).last_activity_at
        self.submit(occurred_at=self.now - timedelta(days=100))
        self.assertEqual(self.repo.get_context('e2ba227d-7165-5d43-91db-f7185326e0c4', self.context.context_id).last_activity_at, activity)

    def test_weak_alias_reviewed_rejection_and_plural_identity(self):
        self.repo.add_alias(self.concept.id, 'Uncertain Topic', 'uncertain topic', 'model', 0.4)
        request = ConceptResolutionRequest(label='Uncertain Topic')
        resolution = self.engine.resolve_concept(request)
        self.assertNotEqual(resolution.status, 'resolved')
        self.engine.review_candidate(resolution.candidate_id, discard=True)
        self.assertEqual(self.engine.resolve_concept(request).status, 'rejected')
        for singular, plural in [('Class', 'Classes'), ('Process', 'Processes'), ('Analysis', 'Analyses')]:
            concept = self.engine.register_concept(singular)
            self.assertEqual(self.engine.resolve_concept(ConceptResolutionRequest(label=plural)).concept_id, concept.id)

    def test_restart_and_replay_are_equivalent_with_repetition_and_bounded_history(self):
        for i in range(90):
            self.now += timedelta(seconds=1)
            self.submit(result='INCORRECT' if i % 7 == 0 else 'CORRECT', item_id=f'reused:{i % 25}')
        original = asdict(self.repo.get_state('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id))
        restart = LearnerEngine(self.repo, clock=lambda: self.now)
        self.assertEqual(restart.get_concept_state(ConceptStateRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concept.id)), self.state())
        replay = asdict(restart.recompute_learner_state('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id))
        original.pop('version')
        replay.pop('version')
        self.assertEqual(replay, original)
        self.assertLessEqual(replay['policy_data']['weight'], 12)
        self.assertLessEqual(len(replay['policy_data']['recent_items']), 64)

    def test_policy_configuration_change_refreshes_on_read(self):
        for _ in range(16):
            self.submit()
        engine = LearnerEngine(self.repo, clock=lambda: self.now,
                               mastery_policy=replace(HeuristicMasteryPolicy(), max_effective_weight=6))
        version = self.state().version
        changed = engine.get_concept_state(ConceptStateRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', concept_id=self.concept.id))
        self.assertGreater(changed.version, version)
        self.assertLessEqual(self.repo.get_state('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id).policy_data['weight'], 6)

    def test_replay_preserves_recency_after_more_than_cache_capacity_distinct_items(self):
        for _ in range(90):
            self.now += timedelta(seconds=1)
            self.submit()
        self.submit(item_id='item:89')
        before = self.repo.get_state('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id)
        after = self.engine.recompute_learner_state('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id)
        self.assertEqual(before.policy_data, after.policy_data)
        self.assertEqual(before.mastery, after.mastery)

    def test_concurrent_duplicate_graders_cannot_inflate_item_count(self):
        request = self.observation()
        def submit(index):
            try:
                return self.engine.submit_evidence(request.model_copy(update={'source_id': f'grader:{index}'}))
            except InvalidEvidenceError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(8)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.state().evidence_count, 1)

    def test_prequential_evaluation_never_uses_future_labels_or_production_state(self):
        requests = [self.observation() for _ in range(8)]
        report = evaluate_observations(requests)
        self.assertEqual(report['count'], 8)
        self.assertEqual(report['supported_count'], 5)
        first = evaluate_observations(requests[:1])
        self.assertEqual(first['mae'], 0.5)
        self.assertEqual(first['supported_count'], 0)
        self.assertIsNone(self.state())
        reversed_time = [requests[0], requests[1].model_copy(update={'occurred_at': self.now - timedelta(days=1)})]
        with self.assertRaises(ValueError):
            evaluate_observations(reversed_time)
        with self.assertRaises(ValueError):
            evaluate_observations([requests[0].model_copy(update={'item_revision': 2})])
        self.assertEqual(evaluate_observations(requests + [requests[-1]])['skipped_count'], 1)

    def test_independent_synthetic_trajectories_beat_neutral_baseline_with_explicit_coverage(self):
        from scripts.verify_learner import synthetic_trajectories
        report = evaluate_observations(synthetic_trajectories())
        self.assertEqual(report['count'], 1050)
        self.assertEqual(report['skipped_count'], 150)
        self.assertLess(report['brier_score'], report['baseline_metrics']['rmse']**2)
        self.assertGreater(report['coverage'], 0.7)
        self.assertLess(report['coverage'], 1)

    def test_merge_preserves_explicit_context_goals(self):
        other = self.engine.register_concept('Dependency Alias')
        self.engine.set_learning_goal(LearningGoalRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', context_id=self.context.context_id,
                                      concept_id=other.id, importance=0.9, target_difficulty=0.8))
        self.engine.merge_concepts(other.id, self.concept.id)
        packet = self.engine.get_relevant_context(LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='transitive dependency'))
        self.assertEqual(packet.concepts[0].importance, 0.9)
        self.assertEqual(packet.concepts[0].target_difficulty, 0.8)
        self.assertFalse(packet.concepts[0].target_performance.supported)

    def test_calibration_small_subject_still_provides_requested_probe_count(self):
        from app.learner.calibration import CalibrationRequest
        targets = LearnerAssessmentAdapter(self.engine).calibration(CalibrationRequest(
            learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', context_id=self.context.context_id, question_count=4))
        self.assertEqual(len(targets), 4)
        self.assertEqual(len({t.concept_id for t in targets}), 1)
        self.assertLess(targets[0].difficulty, targets[-1].difficulty)

    def test_uncertain_misconception_does_not_reassert_a_resolved_claim(self):
        first = self.engine.record_misconception('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id, 'Confuses dependencies', 0.9)
        self.engine.resolve_misconception('e2ba227d-7165-5d43-91db-f7185326e0c4', first.id)
        self.engine.record_misconception('e2ba227d-7165-5d43-91db-f7185326e0c4', self.concept.id, 'Confuses dependencies', 0.2)
        packet = self.engine.get_relevant_context(LearnerContextRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4', query='transitive dependency'))
        self.assertEqual(packet.concepts[0].misconceptions, [])

    def test_timestamped_context_transition_is_serializable(self):
        context = self.engine.transition_context_state(ContextTransitionRequest(learner_id='e2ba227d-7165-5d43-91db-f7185326e0c4',
                  context_id=self.context.context_id, status='DORMANT', occurred_at=self.now))
        self.assertEqual(context.status, 'DORMANT')


if __name__ == '__main__':
    unittest.main()
