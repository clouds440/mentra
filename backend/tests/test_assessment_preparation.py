"""Bounded preparation, read-only parity and pool-pressure regressions."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import event, update
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import sessionmaker
from app.db.database import build_engine
from app.learner import LearnerEngine
from app.learner.repositories.postgres import PostgresLearnerRepository
from app.learner.schemas import LearnerContextRequest
from app.learner.repositories.tables import learner_concept_state
from app.assessments.schemas import AssessmentIntent
from app.assessments.repositories.postgres import AssessmentRepository
from app.assessments.repositories.generation import GenerationJobs
from app.core.exceptions import AppError
from tests import test_assessments as fixtures


class AssessmentPreparationTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.AssessmentTests.setUp

    def seed(self):
        values = []
        for index in range(12):
            value = self.learner.register_concept(f'Force skill {index}')
            self.learner.link_context_concept(self.owner, self.request.context_id, value.id)
            values.append(value)
        return values

    def test_packet_preserves_supported_fields_with_one_checkout_and_no_commits(self):
        self.seed()
        expected = self.learner.get_relevant_context(LearnerContextRequest(learner_id=self.owner,
            context_ids=[self.request.context_id], query='Force', include_related=False))
        counts = dict(queries=0, checkouts=0, commits=0, writes=0)
        def query(connection, cursor, statement, *args):
            counts['queries'] += 1
            counts['writes'] += int(statement.lstrip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE'))
        def checkout(*args): counts['checkouts'] += 1
        def commit(*args): counts['commits'] += 1
        for name, action in [('before_cursor_execute', query), ('checkout', checkout), ('commit', commit)]: event.listen(self.db.engine, name, action)
        try:
            actual = self.learner.get_assessment_context(self.owner, self.request.context_id, 'Force')
        finally:
            for name, action in [('before_cursor_execute', query), ('checkout', checkout), ('commit', commit)]: event.remove(self.db.engine, name, action)
        self.assertEqual(actual.packet.model_dump(exclude={'generated_at'}), expected.model_dump(exclude={'generated_at'}))
        self.assertEqual(len(actual.packet.concepts), 8)
        self.assertLessEqual(counts['queries'], 7)
        self.assertEqual((counts['checkouts'], counts['commits'], counts['writes']), (1, 0, 0))
        print('PREPARATION_METRIC', counts)

    def test_unknown_topic_does_not_read_or_rank_unrelated_history(self):
        self.seed()
        with patch.object(self.learner, 'get_study_targets', side_effect=AssertionError('No full ranking')):
            packet = self.learner.get_assessment_context(self.owner, self.request.context_id, 'Arabic letter forms').packet
        self.assertEqual(packet.concepts, [])

    def test_exact_targets_remain_owned_and_complete_beyond_compact_packet(self):
        values = self.seed()
        actual = self.learner.get_assessment_context(self.owner, self.request.context_id, 'Any title', [value.id for value in values])
        self.assertEqual(set(actual.concepts), {value.id for value in values})
        self.assertEqual(len(actual.packet.concepts), 8)
        with self.assertRaises(AppError):
            self.learner.get_assessment_context(self.owner, self.request.context_id, 'Force', ['missing'])

    async def test_optional_pool_failure_cannot_veto_valid_practice(self):
        with patch.object(self.learner, 'get_assessment_context', side_effect=PoolTimeout('pool busy')):
            result = await self.service.generate(self.owner, self.request)
        self.assertEqual(len(result.questions), 2)

    async def test_programming_errors_are_not_silenced_as_optional_failures(self):
        with patch.object(self.learner, 'get_assessment_context', side_effect=AssertionError('unexpected bug')):
            with self.assertRaisesRegex(AssertionError, 'unexpected bug'):
                await self.service.generate(self.owner, self.request)

    async def test_stale_policy_is_unknown_without_synchronous_replay(self):
        from app.learner.schemas import EvidenceSubmissionRequest
        value = self.seed()[0]
        self.learner.submit_evidence(EvidenceSubmissionRequest(learner_id=self.owner,
            concept_id=value.id, context_id=self.request.context_id, source_type='QUIZ', source_id='first',
            item_id='first', result='CORRECT', score=1, max_score=1, independence=1, difficulty=.5,
            evidence_confidence=1, occurred_at=self.learner.clock()))
        with self.db.sessions.begin() as session:
            session.execute(update(learner_concept_state).where(learner_concept_state.c.concept_id == value.id)
                .values(mastery_policy_version='old-policy'))
        with patch.object(self.learner.evidence, 'recompute', side_effect=AssertionError('No foreground replay')):
            packet = self.learner.get_assessment_context(self.owner, self.request.context_id, 'Force', [value.id]).packet
        self.assertIsNone(packet.concepts[0].mastery)
        with self.db.sessions() as session:
            from sqlalchemy import select
            self.assertEqual(session.scalar(select(learner_concept_state.c.mastery_policy_version)
                .where(learner_concept_state.c.concept_id == value.id)), 'old-policy')

    def test_one_connection_handles_1000_competing_preparation_and_status_operations(self):
        self.seed()
        engine = build_engine(self.db.engine.url.render_as_string(hide_password=False), pool_size=1, max_overflow=0, pool_timeout=2)
        self.addCleanup(engine.dispose)
        sessions = sessionmaker(engine, expire_on_commit=False)
        learner = LearnerEngine(PostgresLearnerRepository(sessions))
        jobs = GenerationJobs(AssessmentRepository(sessions))
        job = jobs.enqueue(self.owner, AssessmentIntent.model_validate(self.request.model_dump()))
        def run(index):
            for offset in range(250):
                if (index + offset) % 2:
                    self.assertEqual(jobs.get(self.owner, job['id'])['state'], 'queued')
                else:
                    self.assertLessEqual(len(learner.get_assessment_context(self.owner,
                        self.request.context_id, 'Force').packet.concepts), 8)
            return 250
        with ThreadPoolExecutor(max_workers=4) as executor:
            self.assertEqual(sum(executor.map(run, range(4))), 1000)
