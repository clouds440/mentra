import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from alembic import command
from sqlalchemy import inspect, text, update, delete
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from app.db.migrate import upgrade, migration_config
from app.learner.models import Concept, LearnerConceptState, LearningContext, LearningEvidence
from app.learner.exceptions import LearnerError
from app.learner import LearnerEngine, ConceptResolutionRequest, EvidenceSubmissionRequest, LearningContextNotFoundError
from app.learner.repositories.tables import learning_evidence, context_concept
from testing.postgres import PostgresSandbox
from testing.identities import learner_id

A, B = learner_id('student-a'), learner_id('student-b')


class LearnerPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.repository = self.db.repository

    def evidence(self, **changes):
        values = dict(id='evidence-1', learner_id=A, concept_id='c', source_type='QUIZ',
            source_id='quiz-1-question-1', result='CORRECT',
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc), score=1, max_score=1,
            evidence_confidence=0.9, metadata={'assessment_id': 'quiz-1', 'question_id': 'question-1'})
        values.update(changes)
        return LearningEvidence(**values)

    def test_migration_creates_required_tables_and_is_idempotent(self):
        upgrade(self.db.engine)
        tables = set(inspect(self.db.engine).get_table_names())
        self.assertTrue({'learner', 'mentra_account', 'external_identity', 'auth_session',
            'concept', 'concept_alias', 'concept_relation', 'learning_context', 'context_concept',
            'learning_evidence', 'evidence_decision', 'learner_concept_state', 'misconception',
            'candidate_concept', 'learner_audit', 'concept_redirect'}.issubset(tables))
        with self.db.engine.connect() as connection:
            from alembic.script import ScriptDirectory
            from app.db.migrate import migration_config
            self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(), ScriptDirectory.from_config(migration_config()).get_current_head())
            command.check(migration_config(connection))

    def test_migration_downgrade_and_fresh_upgrade(self):
        with self.db.engine.begin() as connection:
            command.downgrade(migration_config(connection), 'base')
        self.assertEqual(inspect(self.db.engine).get_table_names(), ['alembic_version'])
        upgrade(self.db.engine)
        self.assertIn('learning_evidence', inspect(self.db.engine).get_table_names())

    def test_application_database_initialization_checks_revision(self):
        from app.db import database
        with patch.object(database, 'get_engine', return_value=self.db.engine):
            database.init_db()
            with self.db.engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num='outdated'"))
            with self.assertRaisesRegex(RuntimeError, 'Alembic upgrade head'):
                database.init_db()

    def test_concept_identity_and_aliases_are_persisted(self):
        concept = Concept('c', 'Database Systems')
        self.repository.create_concept(concept)
        self.repository.add_alias('c', 'DBMS', 'dbms', 'manual', 1)
        self.assertEqual(self.repository.get_concept('c'), concept)
        self.assertEqual(self.repository.find_by_normalized_alias('dbms'), [concept])
        with self.assertRaises(IntegrityError):
            self.repository.create_concept(Concept('c2', 'database systems'))

    def test_contexts_are_scoped_to_learner_and_support_shared_concepts(self):
        self.repository.create_concept(Concept('c', 'Functional Dependency'))
        first = LearningContext('context-a', A, 'Database Systems', 'ACTIVE')
        second = LearningContext('context-b', A, 'Data Modeling', 'RELATED')
        self.repository.save_context(first)
        self.repository.save_context(second)
        self.repository.add_context_concept(first.id, 'c', learner_id=A)
        self.repository.add_context_concept(second.id, 'c', learner_id=A)
        self.assertEqual(self.repository.get_context(A, first.id), first)
        self.assertIsNone(self.repository.get_context(B, first.id))
        self.assertEqual(set(self.repository.get_concept_context_ids('c', learner_id=A)), {first.id, second.id})
        self.assertEqual(self.repository.get_concept_context_ids('c', learner_id=B), [])
        with self.assertRaises(ValueError):
            self.repository.save_context(replace(first, learner_id=B))
        with self.assertRaises(IntegrityError):
            with self.db.engine.begin() as connection:
                connection.execute(update(context_concept).where(context_concept.c.context_id == first.id).values(learner_id=B))

    def test_learner_state_is_unique_by_learner_and_concept_with_version_compare(self):
        self.repository.create_concept(Concept('c', 'Recursion'))
        initial = LearnerConceptState(learner_id=A, concept_id='c', mastery=0.7,
            estimate_confidence=0.8, retention_confidence=0.9, evidence_count=2, version=1)
        updated = replace(initial, mastery=0.75, evidence_count=3, version=2)
        self.repository.save_state(initial)
        self.repository.save_state(updated)
        self.assertEqual(self.repository.get_state(A, 'c'), updated)
        self.assertEqual(len(self.repository.list_states(A)), 1)
        self.assertIsNone(self.repository.get_state(B, 'c'))
        with self.assertRaises(LearnerError):
            self.repository.save_state(initial)
        with self.assertRaises(LearnerError):
            self.repository.save_state(replace(updated, version=4))

    def test_repository_transaction_rolls_back_all_writes_on_failure(self):
        with self.assertRaises(IntegrityError):
            with self.repository.transaction() as transaction:
                transaction.create_concept(Concept('c', 'Algebra'))
                transaction.create_concept(Concept('c2', 'algebra'))
        self.assertIsNone(self.repository.get_concept('c'))
        self.assertIsNone(self.repository.get_concept('c2'))

    def test_evidence_preserves_source_and_rejects_duplicate_source_key(self):
        self.repository.create_concept(Concept('c', 'Recursion'))
        evidence = self.evidence()
        self.repository.append_evidence(evidence)
        persisted = self.repository.find_evidence_by_source(A, 'QUIZ', evidence.source_id, 'c')
        self.assertEqual(persisted.metadata, evidence.metadata)
        self.assertEqual(persisted.occurred_at, evidence.occurred_at)
        self.assertIsNone(self.repository.get_evidence(evidence.id, B))
        with self.assertRaises(IntegrityError):
            self.repository.append_evidence(self.evidence(id='evidence-2'))
        self.repository.append_evidence(self.evidence(id='other-evidence', learner_id=B))
        for operation in (update(learning_evidence).values(result='INCORRECT'),
                          delete(learning_evidence), text('TRUNCATE learning_evidence CASCADE')):
            with self.assertRaisesRegex(IntegrityError, 'learning evidence is immutable'):
                with self.db.engine.begin() as connection:
                    connection.execute(operation)

    def test_database_rejects_orphan_and_cross_learner_evidence(self):
        self.repository.create_concept(Concept('c', 'Recursion'))
        self.repository.save_context(LearningContext('context-a', A, 'Subject', 'ACTIVE'))
        for value in (self.evidence(learner_id=learner_id('missing')), self.evidence(learner_id=B, context_id='context-a')):
            with self.assertRaises(IntegrityError):
                self.repository.append_evidence(value)
        original = self.evidence()
        self.repository.append_evidence(original)
        with self.assertRaises(IntegrityError):
            self.repository.append_evidence(self.evidence(id='correction', learner_id=B,
                source_id='new-source', supersedes_evidence_id=original.id))
        with self.assertRaises(IntegrityError):
            self.repository.save_decision(original.id, 'ACCEPTED', 'test', B)

    def test_database_requires_both_score_fields_and_valid_bounds(self):
        self.repository.create_concept(Concept('c', 'Recursion'))
        for values in ({'score': None}, {'max_score': None}, {'score': float('inf')}, {'difficulty': float('nan')}):
            with self.assertRaises(IntegrityError):
                self.repository.append_evidence(self.evidence(**values))

    def test_candidate_history_and_context_access_are_scoped_to_learner(self):
        engine = LearnerEngine(self.repository)
        first = engine.resolve_concept(ConceptResolutionRequest(label='Unknown Topic', learner_id=A))
        second = engine.resolve_concept(ConceptResolutionRequest(label='Unknown Topic', learner_id=B))
        global_candidate = engine.resolve_concept(ConceptResolutionRequest(label='Unknown Topic'))
        self.assertEqual(len({first.candidate_id, second.candidate_id, global_candidate.candidate_id}), 3)
        self.assertIsNone(self.repository.get_candidate(first.candidate_id, learner_id=B))
        self.assertIsNone(self.repository.get_candidate(first.candidate_id, learner_id=None))
        repeated = engine.resolve_concept(ConceptResolutionRequest(label='Unknown Topic', learner_id=A))
        self.assertEqual(repeated.candidate_id, first.candidate_id)
        self.assertEqual(self.repository.get_candidate(first.candidate_id, learner_id=A)['occurrence_count'], 2)
        self.repository.save_context(LearningContext('context-a', A, 'Private Subject', 'ACTIVE'))
        with self.assertRaises(LearningContextNotFoundError):
            engine.resolve_concept(ConceptResolutionRequest(label='Unknown Topic', learner_id=B, context_id='context-a'))

    def test_different_learners_can_write_while_another_learner_is_locked(self):
        self.repository.create_concept(Concept('c', 'Concurrent Skill'))
        def write_other():
            with self.repository.transaction(learner_ids=[B]) as transaction:
                transaction.save_state(LearnerConceptState(learner_id=B, concept_id='c', version=1))
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.repository.transaction(learner_ids=[A]):
                result = pool.submit(write_other)
                result.result(timeout=5)
        self.assertEqual(self.repository.get_state(B, 'c').version, 1)

    def test_concurrent_opposite_order_batches_preserve_both_learners(self):
        engine = LearnerEngine(self.repository)
        concept = engine.register_concept('Batch Skill')
        now = datetime.now(timezone.utc)
        def batch(index):
            owners = (A, B) if index == 0 else (B, A)
            return engine.submit_evidence_batch([EvidenceSubmissionRequest(
                learner_id=owner, concept_id=concept.id, source_type='QUIZ', source_id=f'batch:{index}',
                result='CORRECT', occurred_at=now, independence=1, difficulty=0.8) for owner in owners])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(batch, index) for index in range(2)]
            self.assertTrue(all(all(item.accepted for item in result.result(timeout=10)) for result in results))
        for owner in (A, B):
            self.assertEqual(self.repository.get_state(owner, concept.id).evidence_count, 2)
            self.assertEqual(self.repository.get_state(owner, concept.id).version, 2)

    def test_locked_transaction_cache_tracks_writes_and_expires_after_rollback(self):
        self.repository.create_concept(Concept('c', 'Cached Skill'))
        self.repository.save_context(LearningContext('context-a', A, 'Subject', 'ACTIVE'))
        statements = []
        def track(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(self.db.engine, 'before_cursor_execute', track)
        self.addCleanup(event.remove, self.db.engine, 'before_cursor_execute', track)
        with self.assertRaisesRegex(ValueError, 'rollback'):
            with self.repository.transaction(learner_ids=[A]) as transaction:
                first = transaction.get_context(A, 'context-a')
                before = len(statements)
                self.assertEqual(transaction.get_context(A, 'context-a'), first)
                self.assertEqual(len(statements), before)
                transaction.save_context(replace(first, status='ARCHIVED'))
                self.assertEqual(transaction.get_context(A, 'context-a').status, 'ARCHIVED')
                self.assertIsNone(transaction.get_state(A, 'c'))
                transaction.save_state(LearnerConceptState(learner_id=A, concept_id='c', version=1))
                self.assertEqual(transaction.get_state(A, 'c').version, 1)
                self.assertEqual(transaction.get_state(A.upper(), 'c').version, 1)
                self.assertEqual(transaction.get_context(A.upper(), 'context-a').status, 'ARCHIVED')
                raise ValueError('rollback')
        self.assertIsNone(self.repository.get_state(A, 'c'))
        self.assertEqual(self.repository.get_context(A, 'context-a').status, 'ACTIVE')
        self.assertEqual(transaction.get_context(A, 'context-a').status, 'ACTIVE')
