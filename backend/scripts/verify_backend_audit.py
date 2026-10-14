"""Historical pre-fix audit probes, not post-fix regression acceptance tests.

Run with PYTHONPATH=backend and an explicit disposable TEST_DATABASE_URL.
Successful probes established defects or safeguards at audit revision 9883ce7.
Several intentionally expect defects that are now fixed and will fail against
the hardened backend. Use backend/tests and verify_runtime_hardening instead.
No application data or real model/search service is used.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, update
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError
from app.langchain.tool_execution import failure, remember_failure

OBSERVATIONS = {}


class LocalProbes(unittest.IsolatedAsyncioTestCase):
    def test_f01_failure_receipt_shape(self):
        receipt = failure(AppError('AUDIT_UNAVAILABLE', 'Unavailable', 503), write=True)
        with self.assertRaises(AttributeError):
            remember_failure({}, 'event_manage', receipt)
        OBSERVATIONS['F01'] = 'ToolFailure passed to remember_failure raises AttributeError'

    async def test_f02_profile_transaction_blocks_event_loop(self):
        from app.student_profile.calibration.service import CalibrationService

        class ProbeComplete(Exception):
            pass

        class Repository:
            @contextmanager
            def transaction(self, owner):
                time.sleep(.15)
                raise ProbeComplete()
                yield

        started = time.monotonic()
        heartbeat = asyncio.create_task(asyncio.sleep(.01))
        with self.assertRaises(ProbeComplete):
            await CalibrationService(Repository(), None).retry_evaluation('owner')
        await heartbeat
        elapsed = time.monotonic() - started
        self.assertGreater(elapsed, .14)
        OBSERVATIONS['F02'] = {'heartbeat_elapsed_ms': round(elapsed * 1000, 2),
                               'injected_transaction_delay_ms': 150}

    async def test_f07_long_valid_mcq_feedback(self):
        from app.assessments.schemas import GeneratedQuestion
        from app.langchain.assessment_workflows import AssessmentWorkflows
        question = GeneratedQuestion(prompt='Choose', concept_ids=['concept'], difficulty=.5,
            marks=1, options=[dict(id='A', label='Yes'), dict(id='B', label='No')],
            correct_option_id='A', model_answer='x' * 2000, rubric='Choose A')
        job = dict(assessment=dict(questions=[dict(question.model_dump(), id='question')]),
                   attempt=dict(answers={'question': 'A'}, extraction=None))
        with self.assertRaises(ValidationError) as caught:
            await AssessmentWorkflows(None, None).grade(job)
        self.assertEqual(caught.exception.errors()[0]['loc'], ('feedback',))
        OBSERVATIONS['F07'] = 'Valid GeneratedQuestion fails deterministic feedback validation'

    async def test_f16_watcher_failure_does_not_cancel_generation(self):
        from app.chat.service import ConversationService
        from app.chat.repositories.activity import ActivityRepository
        generation = asyncio.create_task(asyncio.sleep(2))
        try:
            with patch.object(ActivityRepository, 'ensure_active', side_effect=RuntimeError('audit read outage')):
                watcher = asyncio.create_task(ConversationService(SimpleNamespace(sessions=None))._watch_active(
                    'owner', {}, generation))
                with self.assertRaises(RuntimeError):
                    await watcher
            self.assertFalse(generation.done())
            OBSERVATIONS['F16'] = 'Watcher exits on unexpected read failure; generation remains running'
        finally:
            generation.cancel()
            await asyncio.gather(generation, return_exceptions=True)

    async def test_f26_timeout_leaves_native_thread_running(self):
        started_work = threading.Event()
        release = threading.Event()
        completed = threading.Event()

        def slow():
            started_work.set()
            release.wait(5)
            completed.set()

        invocation = asyncio.create_task(run_in_threadpool(slow))
        try:
            deadline = time.monotonic() + 5
            while not started_work.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(.01)
            self.assertTrue(started_work.is_set())
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(invocation, .02)
            elapsed = time.monotonic() - started
            unfinished = not completed.is_set()
            self.assertTrue(unfinished)
        finally:
            release.set()
            await asyncio.gather(invocation, return_exceptions=True)
        deadline = time.monotonic() + 5
        while not completed.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(.01)
        self.assertTrue(completed.is_set())
        OBSERVATIONS['F26'] = {'wait_elapsed_ms': round(elapsed * 1000, 2),
                               'thread_running_after_timeout': unfinished}

    def test_f13_unbounded_answer_schema(self):
        from app.assessments.schemas import SubmitAnswers
        body = SubmitAnswers(expected_revision=1, client_request_id=uuid4(),
                             answers={str(i): 'x' * 9000 for i in range(100)})
        self.assertEqual(len(body.answers), 100)
        OBSERVATIONS['F13'] = 'SubmitAnswers accepts 100 entries with 9000-character values before repository validation'

    def test_f34_arbitrary_error_content_logged(self):
        from app.core.observability.sanitization import error_metadata
        marker = 'AUDIT_LEARNER_CONTENT_MARKER'
        metadata = error_metadata(RuntimeError(marker))
        self.assertIn(marker, json.dumps(metadata))
        OBSERVATIONS['F34'] = 'Arbitrary non-secret-pattern personal content survives exception-string logging'

    def test_f20_library_receipt_is_returned_without_current_document_check(self):
        from app.chat.attachments import AttachmentService
        from unittest.mock import Mock
        receipt = dict(document_id='already-deleted', job_id='old-job')
        repository = SimpleNamespace(read=lambda *args: {'library_result': receipt})
        rag = Mock()
        result = AttachmentService(repository, reader=Mock()).add_to_library('owner', 'file', 'chat', ['new-context'], rag)
        self.assertEqual(result, receipt)
        self.assertEqual(rag.mock_calls, [])
        OBSERVATIONS['F20'] = 'Stored Library receipt returned without any RAG outcome/context validation'

    def test_f28_conversation_json_lacks_no_store(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.conversations import router
        from app.auth.dependencies import require_identity
        app = FastAPI()
        app.state.conversation_service = SimpleNamespace(repository=SimpleNamespace(recent=lambda *args: {'items': []}))
        app.dependency_overrides[require_identity] = lambda: SimpleNamespace(learner_id='owner')
        app.include_router(router, prefix='/api/v1')
        with TestClient(app) as client:
            response = client.get('/api/v1/conversations')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('no-store', response.headers.get('cache-control', ''))
        OBSERVATIONS['F28'] = 'Successful owned conversation JSON has no explicit no-store header'


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Explicit dedicated database required')
class DatabaseProbes(unittest.TestCase):
    def setUp(self):
        from testing.postgres import PostgresSandbox
        from testing.identities import learner_id
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.owner, self.other = learner_id('alice'), learner_id('bob')

    def assessment_parts(self):
        from app.assessments.repositories.postgres import AssessmentRepository
        from app.assessments.schemas import GenerationRequest, GeneratedAssessment, GeneratedQuestion
        from app.learner.engine import LearnerEngine
        from app.learner.schemas import ResolveLearningContextRequest
        learner = LearnerEngine(self.db.repository)
        context = learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Audit topic'))
        concept = learner.register_concept('Audit concept')
        request = GenerationRequest(client_request_id=uuid4(), context_id=context.context_id, topic='Audit topic', count=1)
        generated = GeneratedAssessment(title='Audit assessment', questions=[GeneratedQuestion(
            prompt='Give an answer', concept_ids=[concept.id], difficulty=.5, marks=1,
            model_answer='A synthetic answer', rubric='Assess the answer')])
        return AssessmentRepository(self.db.sessions), request, generated

    def test_f09_queue_head_race_wastes_one_claim(self):
        from app.assessments.schemas import StartAttempt, SubmitAnswers
        from app.db.owner_transactions import OwnerTransactions
        repository, request, generated = self.assessment_parts()
        assessment = repository.save(self.owner, request, generated, [])
        for _ in range(2):
            attempt = repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
            repository.submit(self.owner, str(attempt.id), SubmitAnswers(expected_revision=attempt.revision,
                client_request_id=uuid4(), answers={str(assessment.questions[0].id): 'Synthetic answer'}))
        barrier = threading.Barrier(2)
        real = OwnerTransactions(self.db.sessions)

        class GatedTransactions:
            @contextmanager
            def write(self, owner):
                barrier.wait(timeout=10)
                with real.write(owner) as transaction:
                    yield transaction

        repository.transactions = GatedTransactions()
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: repository.claim(), range(2)))
        self.assertEqual(sum(value is not None for value in claims), 1)
        OBSERVATIONS['F09'] = 'Two concurrent queue-head selections produce one useful claim despite two ready jobs'

    def test_f11_submission_replay_cannot_retry_terminal_failure(self):
        from app.assessments.schemas import StartAttempt, SubmitAnswers
        repository, request, generated = self.assessment_parts()
        assessment = repository.save(self.owner, request, generated, [])
        attempt = repository.start(self.owner, str(assessment.id), StartAttempt(client_request_id=uuid4()))
        body = SubmitAnswers(expected_revision=attempt.revision, client_request_id=uuid4(),
                             answers={str(assessment.questions[0].id): 'Synthetic answer'})
        repository.submit(self.owner, str(attempt.id), body)
        job = repository.claim()
        repository.fail(job, retry=False)
        replay = repository.submit(self.owner, str(attempt.id), body)
        self.assertEqual(replay.state, 'failed')
        self.assertIsNone(repository.claim())
        OBSERVATIONS['F11'] = 'Same submission receipt returns failed attempt and does not requeue grading'

    def test_f12_capacity_bounds_make_full_history_reachable(self):
        from app.assessments.schemas import StartAttempt
        repository, request, generated = self.assessment_parts()
        first = None
        for _ in range(200):
            assessment = repository.save(self.owner, request.model_copy(update={'client_request_id': uuid4()}), generated, [])
            first = first or assessment
        with self.assertRaises(AppError) as caught:
            repository.save(self.owner, request.model_copy(update={'client_request_id': uuid4()}), generated, [])
        self.assertEqual(caught.exception.code, 'ASSESSMENT_CAPACITY')
        page, total = 0, 0
        while page is not None:
            result = repository.list(self.owner, page)
            total += len(result['items'])
            page = result['next_offset']
        self.assertEqual(total, 200)
        for _ in range(20):
            repository.start(self.owner, str(first.id), StartAttempt(client_request_id=uuid4()))
        with self.assertRaises(AppError) as caught:
            repository.start(self.owner, str(first.id), StartAttempt(client_request_id=uuid4()))
        self.assertEqual(caught.exception.code, 'ATTEMPT_CAPACITY')
        self.assertEqual(len(repository.attempts(self.owner, str(first.id))), 20)
        OBSERVATIONS['F12_WITHDRAWN'] = {'all_assessments_browsable': total, 'all_attempts_listed': 20,
                                        'extra_creations_rejected': True}

    def test_f04_reminder_capacity_starvation(self):
        from app.history_management.events.factory import create_events_service
        from app.history_management.events.schemas import EventCreate
        from app.history_management.repositories.events.tables import reminders
        from app.notifications.repositories.postgres import NotificationRepository
        from app.notifications.repositories.tables import inbox
        from app.notifications.service import NotificationsService
        now = datetime.now(timezone.utc)
        notification_repository = NotificationRepository(self.db.sessions, clock=lambda: now)
        notifications = NotificationsService(notification_repository)
        events = create_events_service(self.db.sessions, clock=lambda: now)
        events.repository.notifications = notifications
        blocked = []
        for index in range(50):
            result = events.create(self.owner, EventCreate(title=f'Blocked {index}', timezone='UTC',
                starts_at=now + timedelta(hours=2), client_request_id=uuid4()))
            blocked.append(str(result['event_id']))
        good = events.create(self.other, EventCreate(title='Deliverable', timezone='UTC',
            starts_at=now + timedelta(hours=2), client_request_id=uuid4()))
        with self.db.sessions.begin() as session:
            session.execute(inbox.insert(), [dict(id=str(uuid4()), learner_id=self.owner,
                kind='event_reminder', target_kind='event', title='Existing', body='Existing', created_at=now,
                revision=1) for _ in range(1000)])
            session.execute(update(reminders).where(reminders.c.event_id.in_(blocked)).values(
                due_at=now - timedelta(minutes=2)))
            session.execute(update(reminders).where(reminders.c.event_id == str(good['event_id'])).values(
                due_at=now - timedelta(minutes=1)))
        self.assertEqual(events.repository.deliver_reminders(), 0)
        self.assertEqual(events.repository.deliver_reminders(), 0)
        self.assertEqual(notifications.inbox(self.other)['items'], [])
        OBSERVATIONS['F04'] = 'Two 50-row batches both blocked; another owner receives no due reminder'

    def test_f08_merge_breaks_material_scope(self):
        from tests.rag.test_workflows import WorkflowTests
        from app.rag.schemas import SearchRequest
        case = WorkflowTests()
        case.setUp()
        try:
            accepted = case.ready()
            original = case.learner.register_concept('Python decorators')
            target = case.learner.register_concept('Decorator functions')
            doc = case.repo.get_document(case.owner, accepted['document_id'])
            case.repo.tag_document(case.owner, doc['id'], doc['revision'], [original.id])
            before = case.service.search(case.owner, SearchRequest(query='decorators', mode='CONCEPT_FOCUSED',
                context_ids=[case.context.context_id], concept_ids=[original.id]))
            self.assertTrue(before.chunks)
            case.learner.merge_concepts(original.id, target.id)
            after = case.service.search(case.owner, SearchRequest(query='decorators', mode='CONCEPT_FOCUSED',
                context_ids=[case.context.context_id], concept_ids=[original.id]))
            self.assertEqual(after.status, 'no_eligible_sources')
            OBSERVATIONS['F08'] = {'before_chunks': len(before.chunks), 'after_status': after.status}
        finally:
            case.doCleanups()

    def test_f10_exhausted_evidence_stays_running(self):
        from tests.test_chat_evidence_jobs import EvidenceJobTests
        from app.langchain.repositories.evidence import ChatEvidenceRepository
        from app.langchain.repositories.evidence_tables import jobs
        case = EvidenceJobTests()
        case.setUp()
        try:
            with case.db.sessions.begin() as session:
                session.execute(update(jobs).values(state='running', attempts=3, claim_id=str(uuid4()),
                    claim_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
            self.assertIsNone(ChatEvidenceRepository(case.db.sessions).claim())
            with case.db.sessions() as session:
                self.assertEqual(session.scalar(select(jobs.c.state)), 'running')
            OBSERVATIONS['F10'] = 'Expired third-attempt job remains running and cannot be reclaimed'
        finally:
            case.doCleanups()

    def test_f14_profile_reads_execute_insert_and_lock(self):
        from sqlalchemy import event
        from app.student_profile.repositories.postgres import PostgresStudentProfileRepository
        from app.student_profile.service import StudentProfileService
        service = StudentProfileService(PostgresStudentProfileRepository(self.db.sessions), None)
        service.get(self.owner)
        statements = []

        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())

        event.listen(self.db.engine, 'before_cursor_execute', record)
        try:
            service.get(self.owner)
        finally:
            event.remove(self.db.engine, 'before_cursor_execute', record)
        self.assertTrue(any('pg_advisory_xact_lock' in statement for statement in statements))
        self.assertTrue(any('insert into student_profile' in statement for statement in statements))
        OBSERVATIONS['F14'] = {'existing_profile_read_statement_count': len(statements),
                               'insert_and_advisory_lock': True}

    def test_f18_metadata_detail_selects_original_bytes(self):
        from sqlalchemy import event
        from app.chat.repositories.attachments import AttachmentRepository
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        repository = AttachmentRepository(self.db.sessions)
        file = repository.create(self.owner, 'audit.txt', b'a' * 1024 * 1024)
        conversation = uuid4()
        ChatRepository(self.db.sessions).begin_turn(self.owner, SendTurn(conversation_id=conversation,
            client_turn_id=uuid4(), expected_revision=0, content='Read the file', attachment_ids=[file['id']]))
        statements = []

        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.db.engine, 'before_cursor_execute', record)
        try:
            detail = repository.detail(self.owner, file['id'], str(conversation))
        finally:
            event.remove(self.db.engine, 'before_cursor_execute', record)
        self.assertEqual(detail['size_bytes'], 1024 * 1024)
        self.assertTrue(any('chat_attachment.data' in statement for statement in statements))
        OBSERVATIONS['F18'] = 'Metadata-only detail SELECT includes a 1 MiB original BLOB column'

    def test_f22_dense_failure_never_attempts_lexical_branch(self):
        from tests.rag.test_workflows import WorkflowTests
        from app.rag.vector_store import VectorStoreError
        case = WorkflowTests()
        case.setUp()
        try:
            case.ready()
            with patch.object(case.vector, 'query_chunks', side_effect=VectorStoreError('Audit vector outage')), \
                    patch.object(case.repo, 'lexical', wraps=case.repo.lexical) as lexical:
                with self.assertRaises(AppError) as caught:
                    case.search()
            self.assertEqual(caught.exception.code, 'RAG_UNAVAILABLE')
            self.assertEqual(lexical.call_count, 0)
            OBSERVATIONS['F22'] = 'Ready PostgreSQL chunks exist, but dense failure aborts before lexical retrieval'
        finally:
            case.doCleanups()

    def test_f15_profile_edit_conflicts_with_owner_projection(self):
        from app.db.owner_transactions import OwnerTransactions
        from app.student_profile.repositories.postgres import PostgresStudentProfileRepository
        from app.student_profile.repositories.store import PostgresProfileStore
        from app.student_profile.repositories.learning_projection import project_learning_profile
        from app.student_profile.repositories.tables import student_profile
        from app.student_profile.service import StudentProfileService
        from app.student_profile.schemas import ProfileUpdate, Estimates, Estimate
        from tests.student_profile.test_profile import details
        service = StudentProfileService(PostgresStudentProfileRepository(self.db.sessions), None)
        initial = service.get(self.owner)
        service.update_details(self.owner, ProfileUpdate(expected_version=initial.version, details=details()))
        estimates = Estimates(domain_familiarity=Estimate(value=.4, confidence=.3, evidence_count=1))
        with self.db.sessions.begin() as session:
            session.execute(update(student_profile).where(student_profile.c.learner_id == self.owner).values(
                estimates=estimates.model_dump(mode='json')))
        read, resume = threading.Event(), threading.Event()
        original = PostgresProfileStore.profile

        def gated(store):
            profile = original(store)
            if threading.current_thread().name.startswith('audit-projection'):
                read.set()
                if not resume.wait(10):
                    raise RuntimeError('Audit synchronization timeout')
            return profile

        def project():
            with OwnerTransactions(self.db.sessions).write(self.owner) as transaction:
                project_learning_profile(transaction, self.owner)

        with patch.object(PostgresProfileStore, 'profile', gated), ThreadPoolExecutor(
                max_workers=1, thread_name_prefix='audit-projection') as executor:
            future = executor.submit(project)
            try:
                self.assertTrue(read.wait(10))
                current = service.get(self.owner)
                service.update_details(self.owner, ProfileUpdate(expected_version=current.version,
                    details=details(preferred_name='Audit edited name')))
            finally:
                resume.set()
            with self.assertRaises(AppError) as caught:
                future.result(timeout=10)
        self.assertEqual(service.get(self.owner).details.preferred_name, 'Audit edited name')
        OBSERVATIONS['F15'] = {'projection_conflict_code': caught.exception.code,
                               'user_edit_preserved_by_version_fence': True}

    def test_f29_text_identifier_returns_owned_not_found(self):
        from app.rag.repositories.postgres import RAGRepository
        from app.rag.repositories.tables import documents
        from sqlalchemy import Text
        self.assertIsInstance(documents.c.id.type, Text)
        with self.assertRaises(AppError) as caught:
            RAGRepository(self.db.sessions).get_document(self.owner, 'not-a-uuid')
        self.assertEqual(caught.exception.status_code, 404)
        OBSERVATIONS['F29_WITHDRAWN'] = 'RAG IDs are PostgreSQL Text; unknown text ID returns owned 404, not DataError'

    def test_f38_replay_timestamp_representation_drift(self):
        from dataclasses import asdict
        from sqlalchemy import text
        from tests.learner.test_realistic_learning import RealisticLearningTests
        case = RealisticLearningTests()
        case.setUp()
        try:
            with case.db.engine.begin() as connection:
                connection.execute(text("SET timezone TO 'Asia/Karachi'"))
            for index in range(90):
                case.now += timedelta(seconds=1)
                case.submit(result='INCORRECT' if index % 7 == 0 else 'CORRECT', item_id=f'reused:{index % 25}')
            owner = 'e2ba227d-7165-5d43-91db-f7185326e0c4'
            before = asdict(case.repo.get_state(owner, case.concept.id))
            after = asdict(case.engine.recompute_learner_state(owner, case.concept.id))
            before.pop('version')
            after.pop('version')
            differences = {}
            for key in before:
                if before[key] == after[key]:
                    continue
                if key == 'policy_data':
                    for field in set(before[key]) | set(after[key]):
                        if before[key].get(field) != after[key].get(field):
                            differences[f'policy_data.{field}'] = [before[key].get(field), after[key].get(field)]
                else:
                    differences[key] = [str(before[key]), str(after[key])]
            self.assertTrue(differences)
            self.assertEqual(before['mastery'], after['mastery'])
            self.assertTrue(all(datetime.fromisoformat(values[0]) == datetime.fromisoformat(values[1])
                                for values in differences.values()))
            OBSERVATIONS['F38'] = {'differences': differences, 'numeric_mastery_unchanged': True,
                                    'different_strings_represent_same_instants': True}
        finally:
            case.doCleanups()

    def test_f36_historical_core_rows_survive_downgrade_and_upgrade(self):
        from alembic import command
        from app.db.migrate import migration_config, upgrade
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.repositories.tables import conversations, messages
        from app.chat.schemas import SendTurn
        from app.history_management.repositories.postgres import MemoryRepository
        from app.history_management.repositories.tables import memories
        MemoryRepository(self.db.sessions).write(self.owner, 'Synthetic audit preference', 'preference', str(uuid4()))
        chat = ChatRepository(self.db.sessions)
        job = chat.begin_turn(self.owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(),
            expected_revision=0, content='Synthetic historical question'))
        chat.finish(self.owner, job, response=dict(content='Synthetic historical answer'))
        # These projections explicitly select fields that existed at revision 0006.
        projections = {'memory': [memories.c.id, memories.c.content, memories.c.status, memories.c.revision],
            'chat': [conversations.c.id, conversations.c.title, conversations.c.message_count, conversations.c.revision],
            'messages': [messages.c.id, messages.c.sequence, messages.c.role, messages.c.content]}

        def snapshot():
            with self.db.sessions() as session:
                return {key: sorted(tuple(row) for row in session.execute(select(*columns)))
                        for key, columns in projections.items()}

        baseline = snapshot()
        with self.db.engine.connect() as connection:
            command.downgrade(migration_config(connection), '20261008_0006')
            connection.commit()
        try:
            self.assertEqual(snapshot(), baseline)
        finally:
            upgrade(self.db.engine)
        self.assertEqual(snapshot(), baseline)
        OBSERVATIONS['F36'] = 'Explicit pre-Events memory/chat/message projections survive downgrade and re-upgrade; original test still needs repair'


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    output = Path(os.environ.get('AUDIT_PROBE_RESULTS', '.cache/backend-audit/probes.json'))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(tests=result.testsRun, failures=len(result.failures),
        errors=len(result.errors), skipped=len(result.skipped), observations=OBSERVATIONS), indent=2), encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
