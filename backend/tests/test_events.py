import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError, DBAPIError
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.core.exceptions import AppError
from app.db.metadata import metadata
from app.db.migrate import migration_config, upgrade
from app.history_management.events.schemas import (EventCreate, EventDraft, EventEdit,
    EventRecord, EventPage, EventSync, EventOutcome, PreferencesEdit, TemporalPreview)
from app.history_management.events.temporal import local_choices, bounds, reminder_due, bucket, preview
from app.history_management.events.factory import create_events_service
from app.history_management.repositories.events.tables import events, reminders, receipts, evidence, revisions, sync_state
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from testing.postgres import PostgresSandbox
from testing.identities import learner_id

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 6, tzinfo=UTC)


def create_body(**changes):
    return EventCreate(**(dict(title='Algebra quiz', kind='quiz', timezone='Asia/Karachi',
        local_date=date(2026, 10, 12), client_request_id=uuid4()) | changes))


class EventTemporalTests(unittest.TestCase):
    def test_fold_chronology_uses_instants_not_wall_clock(self):
        from zoneinfo import ZoneInfo
        zone = ZoneInfo('America/New_York')
        draft = create_body(local_date=None,
            starts_at=datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0),
            ends_at=datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1))
        start, end = bounds(draft)
        self.assertEqual(end-start, timedelta(minutes=30))

    def test_host_timezone_keys_are_rejected(self):
        for zone in ('localtime', 'posixrules'):
            with self.assertRaises(ValidationError):
                create_body(timezone=zone)

    def test_past_date_can_be_recorded_when_unused_default_reminder_is_in_dst_gap(self):
        from app.history_management.repositories.events.postgres import DEFAULTS
        draft = create_body(local_date=date(2026, 3, 9), timezone='America/New_York')
        self.assertEqual(reminder_due(draft, dict(DEFAULTS, date_hour=2, date_minute=30), NOW)[1], 'skipped')

    def test_fold_preview_only_reports_invalid_end_when_no_pair_is_valid(self):
        from app.history_management.repositories.events.postgres import DEFAULTS
        result = preview(TemporalPreview(timezone='America/New_York',
            local_start=datetime(2026, 11, 1, 1, 30), local_end=datetime(2026, 11, 1, 1, 15)), DEFAULTS, NOW)
        self.assertEqual(len(result['choices']), 1)
        self.assertEqual(result['field_errors'], [])
        result = preview(TemporalPreview(timezone='Pacific/Apia', local_date=date(2011, 12, 30)), DEFAULTS, NOW)
        self.assertEqual(result['field_errors'][0]['field'], 'local_date')

    def test_date_mode_naive_zone_and_unknown_field_validation(self):
        for fields in [dict(local_date=None), dict(starts_at=NOW), dict(timezone='Mars/Olympus'),
                       dict(local_date=None, starts_at=datetime(2026, 10, 12)), dict(owner=str(uuid4())),
                       dict(reminder=dict(mode='disabled', at=NOW)), dict(description='x'*1001)]:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                create_body(**fields)

    def test_dst_gap_and_fold_choices(self):
        self.assertEqual(local_choices(datetime(2026, 3, 8, 2, 30), 'America/New_York'), [])
        choices = local_choices(datetime(2026, 11, 1, 1, 30), 'America/New_York')
        self.assertEqual(len(choices), 2)
        self.assertEqual(choices[1]-choices[0], timedelta(hours=1))
        self.assertTrue(preview(TemporalPreview(timezone='America/New_York', local_start=datetime(2026, 11, 1, 1, 30)))['requires_choice'])

    def test_date_only_local_cutoff_and_default_reminder(self):
        from app.history_management.repositories.events.postgres import DEFAULTS
        draft = create_body()
        start, cutoff = bounds(draft)
        self.assertEqual(start, datetime(2026, 10, 11, 19, tzinfo=UTC))
        self.assertEqual(cutoff, datetime(2026, 10, 12, 19, tzinfo=UTC))
        due, state = reminder_due(draft, DEFAULTS, NOW)
        self.assertEqual(due, datetime(2026, 10, 11, 4, tzinfo=UTC))
        self.assertEqual(state, 'pending')

    def test_default_timed_offset_and_late_create(self):
        from app.history_management.repositories.events.postgres import DEFAULTS
        draft = create_body(local_date=None, starts_at=NOW+timedelta(hours=2))
        self.assertEqual(reminder_due(draft, DEFAULTS, NOW), (NOW, 'pending'))
        self.assertEqual(reminder_due(draft, DEFAULTS, NOW+timedelta(hours=3))[1], 'skipped')
        self.assertEqual(reminder_due(draft, dict(DEFAULTS, reminders_enabled=False), NOW)[1], 'skipped')
        future = create_body(local_date=None, starts_at=NOW+timedelta(days=3))
        self.assertEqual(reminder_due(future, dict(DEFAULTS, reminders_enabled=False), NOW)[1], 'pending')

    def test_occurrences_never_become_overdue_deadlines(self):
        start, cutoff = bounds(create_body())
        row = dict(status='scheduled', kind='quiz', local_date=date(2026, 10, 12), sort_at=start, cutoff_at=cutoff)
        self.assertEqual(bucket(row, cutoff), 'past')
        self.assertEqual(bucket(dict(row, kind='assignment'), cutoff), 'overdue')
        self.assertEqual(bucket(row, start), 'in_progress')
        self.assertEqual(bucket(dict(row, status='completed'), NOW), 'completed')

    def test_civil_day_dst_length_midnight_gap_and_skipped_day(self):
        start, end = bounds(create_body(local_date=date(2026, 3, 8), timezone='America/New_York'))
        self.assertEqual(end-start, timedelta(hours=23))
        # Sao Paulo's historical midnight gap still has a valid civil day.
        start, end = bounds(create_body(local_date=date(2018, 11, 4), timezone='America/Sao_Paulo'))
        self.assertEqual(end-start, timedelta(hours=23))
        with self.assertRaises(AppError):
            bounds(create_body(local_date=date(2011, 12, 30), timezone='Pacific/Apia'))

    def test_civil_boundary_preserves_historical_second_precision(self):
        start, _ = bounds(create_body(local_date=date(1972, 1, 7), timezone='Africa/Monrovia'))
        self.assertEqual(start, datetime(1972, 1, 7, 0, 44, 30, tzinfo=UTC))

    def test_reminder_after_cutoff_and_dst_default_are_rejected(self):
        from app.history_management.repositories.events.postgres import DEFAULTS
        with self.assertRaises(AppError):
            reminder_due(create_body(reminder=dict(mode='at', at=NOW+timedelta(days=10))), DEFAULTS, NOW)
        with self.assertRaises(AppError):
            reminder_due(create_body(local_date=date(2026, 3, 9), timezone='America/New_York'),
                         dict(DEFAULTS, date_hour=2, date_minute=30), NOW-timedelta(days=300))


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires explicit dedicated TEST_DATABASE_URL')
class EventPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.owner, cls.other = learner_id('alice'), learner_id('bob')

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.now = NOW
        self.service = create_events_service(self.db.sessions, clock=lambda: self.now)
        # Tests have separate event data and preferences despite one rehearsal schema.
        with self.service.repository.transactions.write(self.owner) as uow:
            from app.history_management.repositories.events.tables import TABLES
            # Lifetime ledgers may be removed only by their parent event purge.
            uow._session.execute(events.delete().where(events.c.learner_id == self.owner))
            for table in reversed(TABLES):
                uow._session.execute(table.delete().where(table.c.learner_id == self.owner))

    def create(self, **changes):
        result = self.service.create(self.owner, create_body(**changes))
        EventOutcome.model_validate(result)
        return result['event']

    def edit(self, event, **changes):
        return self.service.edit(self.owner, event['id'], EventEdit(expected_revision=event['revision'], client_request_id=uuid4(), **changes))['event']

    def test_owned_crud_receipt_replay_conflict_and_purge(self):
        body = create_body()
        first = self.service.create(self.owner, body)
        self.assertEqual(self.service.create(self.owner, body)['event']['id'], first['event']['id'])
        with self.assertRaises(AppError):
            self.service.create(self.owner, body.model_copy(update={'title': 'Different'}))
        event = first['event']
        for action in [lambda: self.service.detail(self.other, event['id']),
                       lambda: self.service.remove(self.other, event['id'], 1, str(uuid4())),
                       lambda: self.service.operation(self.other, str(body.client_request_id))]:
            with self.assertRaises(AppError) as error:
                action()
            self.assertEqual(error.exception.status_code, 404)
        edited = self.edit(event, status='completed')
        self.assertEqual(edited['reminder_state'], 'cancelled')
        self.assertIsNotNone(edited['completed_at'])
        with self.assertRaises(AppError):
            self.edit(event, status='cancelled')
        key = str(uuid4())
        self.service.remove(self.owner, event['id'], 2, key)
        self.assertEqual(self.service.remove(self.owner, event['id'], 2, key)['outcome'], 'deleted')
        self.assertEqual(self.service.create(self.owner, body)['outcome'], 'deleted')
        with self.db.sessions() as session:
            for table, column in [(events, events.c.id), (reminders, reminders.c.event_id), (evidence, evidence.c.event_id), (revisions, revisions.c.event_id)]:
                self.assertEqual(session.scalar(select(func.count()).select_from(table).where(column == event['id'])), 0)

    def test_metadata_edits_preserve_original_pending_reminder_schedule(self):
        event = self.create()
        self.service.set_preferences(self.owner, PreferencesEdit(expected_revision=0, date_hour=12))
        details = EventDraft(title='Changed title', kind='quiz', timezone=event['timezone'], local_date=event['local_date'])
        edited = self.edit(event, details=details)
        self.assertEqual(edited['reminder_due_at'], event['reminder_due_at'])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(reminders.c.schedule_version).where(reminders.c.event_id == event['id'])), 1)
        # A real date edit explicitly recalculates using the current defaults.
        rescheduled = self.edit(edited, details=details.model_copy(update={'local_date':date(2026, 10, 13)}))
        self.assertEqual(rescheduled['reminder_due_at'], datetime(2026, 10, 12, 7, tzinfo=UTC))

    def test_reopen_does_not_replay_cancelled_or_skipped_missed_reminder(self):
        event = self.create(local_date=None, starts_at=NOW+timedelta(days=3))
        cancelled = self.edit(event, status='cancelled')
        self.now += timedelta(days=2, hours=1)
        reopened = self.edit(cancelled, status='scheduled')
        self.assertEqual(reopened['reminder_state'], 'skipped')
        completed = self.edit(reopened, status='completed')
        self.assertEqual(self.edit(completed, status='scheduled')['reminder_state'], 'skipped')

    def test_rescheduling_inactive_event_updates_its_single_ledger_for_reopen(self):
        cancelled = self.edit(self.create(), status='cancelled')
        details = EventDraft(title=cancelled['title'], kind=cancelled['kind'], timezone=cancelled['timezone'], local_date=date(2026, 10, 20))
        edited = self.edit(cancelled, details=details)
        reopened = self.edit(edited, status='scheduled')
        self.assertEqual(reopened['reminder_due_at'], datetime(2026, 10, 19, 4, tzinfo=UTC))
        self.assertEqual(reopened['reminder_state'], 'pending')

    def test_equivalent_offset_on_delivered_reminder_is_not_a_new_rule(self):
        due = NOW+timedelta(days=1)
        event = self.create(reminder=dict(mode='at', at=due.astimezone(timezone(timedelta(hours=5)))))
        with self.service.repository.transactions.write(self.owner) as uow:
            uow._session.execute(update(reminders).where(reminders.c.event_id == event['id'])
                .values(state='delivered', delivered_at=NOW, receipt_id=str(uuid4())))
        details = EventDraft(title='New title', kind='quiz', timezone=event['timezone'],
            local_date=event['local_date'], reminder=dict(mode='at', at=due))
        updated = self.edit(event, details=details)
        self.assertEqual(updated['reminder_state'], 'delivered')

    def test_context_deleted_after_admission_returns_owned_not_found_and_rolls_back(self):
        from app.learner import LearnerEngine, ResolveLearningContextRequest
        from app.learner.repositories.tables.contexts import learning_context
        engine = LearnerEngine(self.db.repository)
        context = engine.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Race '+uuid4().hex))
        class DisappearingContext:
            def get_context_summaries(_, owner, identifiers):
                summaries = engine.get_context_summaries(owner, identifiers)
                with self.db.sessions.begin() as session:
                    session.execute(learning_context.delete().where(learning_context.c.id == context.context_id))
                return summaries
        service = create_events_service(self.db.sessions, clock=lambda: self.now, learner=DisappearingContext())
        with self.assertRaises(AppError) as error:
            service.create(self.owner, create_body(context_id=context.context_id))
        self.assertEqual(error.exception.code, 'CONTEXT_NOT_FOUND')
        self.assertEqual(service.summary(self.owner)['upcoming'], 0)

    def test_owner_lock_timeout_is_retryable_and_does_not_partially_write(self):
        from app.db.owner_transactions import OwnerTransactions
        self.service.repository.transactions = OwnerTransactions(self.db.sessions, timeout_ms=100)
        body = create_body()
        with OwnerTransactions(self.db.sessions).write(self.owner):
            with ThreadPoolExecutor(1) as pool:
                with self.assertRaises(AppError) as error:
                    pool.submit(self.service.create, self.owner, body).result(timeout=3)
        self.assertEqual(error.exception.code, 'EVENTS_UNAVAILABLE')
        self.assertEqual(self.service.create(self.owner, body)['outcome'], 'saved')

    def test_bulk_disable_uses_bounded_queries_and_emits_all_revisioned_changes(self):
        from sqlalchemy import event as sqlalchemy_event
        identifiers = [self.create(local_date=None, starts_at=NOW+timedelta(days=2))['id'] for _ in range(64)]
        self.now += timedelta(hours=36)
        queries = []
        def track(*args):
            queries.append(args[2])
        sqlalchemy_event.listen(self.db.engine, 'before_cursor_execute', track)
        try:
            result = self.service.set_preferences(self.owner, PreferencesEdit(expected_revision=0, reminders_enabled=False))
        finally:
            sqlalchemy_event.remove(self.db.engine, 'before_cursor_execute', track)
        self.assertLessEqual(len(queries), 16)
        self.assertEqual(result['sync_revision'], 129)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(reminders).where(reminders.c.event_id.in_(identifiers), reminders.c.state == 'skipped')), 64)
            self.assertEqual(session.scalar(select(func.count()).select_from(revisions).where(revisions.c.event_id.in_(identifiers), revisions.c.revision == 2, revisions.c.actor == 'preferences')), 64)

    def test_context_lookup_failure_cannot_hide_committed_or_deleted_outcomes(self):
        from app.learner import LearnerEngine, ResolveLearningContextRequest
        engine = LearnerEngine(self.db.repository)
        context = engine.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Receipt '+uuid4().hex))
        service = create_events_service(self.db.sessions, clock=lambda: self.now, learner=engine)
        body = create_body(context_id=context.context_id)
        event = service.create(self.owner, body)['event']
        edit = EventEdit(expected_revision=1, client_request_id=uuid4(), details=EventDraft(
            title='Edited', kind='quiz', timezone='Asia/Karachi', local_date=body.local_date, context_id=context.context_id))
        service.edit(self.owner, event['id'], edit)
        service.learner = None
        self.assertEqual(service.create(self.owner, body)['event']['id'], event['id'])
        self.assertEqual(service.edit(self.owner, event['id'], edit)['event']['revision'], 2)
        service.remove(self.owner, event['id'], 2, str(uuid4()))
        self.assertEqual(service.create(self.owner, body)['outcome'], 'deleted')
        self.assertEqual(service.edit(self.owner, event['id'], edit)['outcome'], 'deleted')
        with self.assertRaises(AppError) as error:
            service.create(self.owner, body.model_copy(update={'title':'Changed payload'}))
        self.assertEqual(error.exception.code, 'OPERATION_CONFLICT')

    def test_summary_counts_follow_upcoming_buckets(self):
        deadline = self.create(kind='deadline', local_date=None, starts_at=NOW-timedelta(hours=1), ends_at=NOW+timedelta(hours=1))
        occurrence = self.create(local_date=date(2026, 10, 9))
        self.assertEqual(deadline['bucket'], 'upcoming')
        self.assertEqual(occurrence['bucket'], 'in_progress')
        self.assertEqual(self.service.summary(self.owner)['upcoming'], 1)

    def test_concurrent_create_and_update_one_winner(self):
        body = create_body()
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: self.service.create(self.owner, body), range(2)))
        self.assertEqual(results[0]['event']['id'], results[1]['event']['id'])
        event = results[0]['event']
        def change(status):
            try:
                return self.edit(event, status=status)['revision']
            except AppError:
                return 'conflict'
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(change, ['completed', 'cancelled']))
        self.assertCountEqual(results, [2, 'conflict'])

    def test_preferences_first_write_race_and_independent_capture(self):
        def change(enabled):
            try:
                return self.service.set_preferences(self.owner, PreferencesEdit(expected_revision=0, automatic_events=enabled))['revision']
            except AppError:
                return 'conflict'
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(change, [False, True]))
        self.assertCountEqual(results, [1, 'conflict'])
        prefs = self.service.preferences(self.owner)
        self.service.set_preferences(self.owner, PreferencesEdit(expected_revision=prefs['revision'], automatic_events=False))
        self.assertTrue(self.create()['id'])
        self.assertTrue(self.service.preferences(self.owner)['reminders_enabled'])

    def test_lifetime_delivery_is_immutable_in_service_and_database(self):
        event = self.create()
        with self.service.repository.transactions.write(self.owner) as uow:
            uow._session.execute(update(reminders).where(reminders.c.learner_id == self.owner, reminders.c.event_id == event['id'])
                                 .values(state='delivered', delivered_at=NOW, receipt_id=str(uuid4())))
        current = self.edit(event, status='completed')
        reopened = self.edit(current, status='scheduled')
        self.assertEqual(reopened['reminder_state'], 'delivered')
        self.assertEqual(reopened['reminder_delivered_at'], NOW)
        details = EventDraft(title='Rescheduled quiz', kind='quiz', timezone='Asia/Karachi', local_date=date(2026, 11, 12))
        updated = self.edit(reopened, details=details)
        self.assertEqual(updated['reminder_state'], 'delivered')
        with self.assertRaises(AppError):
            self.edit(updated, details=details.model_copy(update={'reminder': create_body(reminder=dict(mode='disabled')).reminder}))
        with self.assertRaises(DBAPIError), self.db.sessions.begin() as session:
            session.execute(update(reminders).where(reminders.c.learner_id == self.owner, reminders.c.event_id == event['id'])
                            .values(state='pending', delivered_at=None, receipt_id=None))

    def test_lifetime_ledger_cannot_be_deleted_to_rearm_but_event_purge_is_allowed(self):
        event = self.create()
        with self.service.repository.transactions.write(self.owner) as uow:
            uow._session.execute(update(reminders).where(reminders.c.event_id == event['id'])
                .values(state='delivered', delivered_at=NOW, receipt_id=str(uuid4())))
        with self.assertRaises(DBAPIError), self.db.sessions.begin() as session:
            session.execute(reminders.delete().where(reminders.c.event_id == event['id']))
        self.assertEqual(self.service.detail(self.owner, event['id'])['reminder_state'], 'delivered')
        self.assertEqual(self.service.remove(self.owner, event['id'], 1, str(uuid4()))['outcome'], 'deleted')

    def test_retention_migration_downgrade_preserves_live_rows_and_update_fence(self):
        event = self.create()
        with self.db.engine.connect() as connection:
            command.downgrade(migration_config(connection), '20261009_0007')
            connection.commit()
        self.assertEqual(self.service.detail(self.owner, event['id'])['revision'], 1)
        with self.service.repository.transactions.write(self.owner) as uow:
            uow._session.execute(update(reminders).where(reminders.c.event_id == event['id'])
                .values(state='delivered', delivered_at=NOW, receipt_id=str(uuid4())))
        with self.assertRaises(DBAPIError), self.db.sessions.begin() as session:
            session.execute(update(reminders).where(reminders.c.event_id == event['id']).values(due_at=NOW))
        upgrade(self.db.engine)
        with self.assertRaises(DBAPIError), self.db.sessions.begin() as session:
            session.execute(reminders.delete().where(reminders.c.event_id == event['id']))
        self.assertEqual(self.service.detail(self.owner, event['id'])['reminder_state'], 'delivered')

    def test_disable_window_preserves_future_and_skips_missed_even_without_worker(self):
        soon = self.create(local_date=None, starts_at=NOW+timedelta(days=2))
        later = self.create(local_date=None, starts_at=NOW+timedelta(days=5))
        self.service.set_preferences(self.owner, PreferencesEdit(expected_revision=0, reminders_enabled=False))
        self.now += timedelta(days=2)
        self.service.set_preferences(self.owner, PreferencesEdit(expected_revision=1, reminders_enabled=True))
        self.assertEqual(self.service.detail(self.owner, soon['id'])['reminder_state'], 'skipped')
        self.assertEqual(self.service.detail(self.owner, later['id'])['reminder_state'], 'pending')
        # A title-only edit must not rearm a reminder missed while disabled.
        soon = self.service.detail(self.owner, soon['id'])
        result = self.edit(soon, details=EventDraft(title='New title', kind='quiz', timezone='Asia/Karachi', starts_at=soon['starts_at']))
        self.assertEqual(result['reminder_state'], 'skipped')

    def test_bounded_pages_owner_binding_changed_membership_and_sync_tombstones(self):
        for _ in range(3):
            self.create()
        filters = dict(after=NOW, before=NOW+timedelta(days=90), status='scheduled', kind=None, query='')
        page = self.service.list(self.owner, filters, limit=2)
        EventPage.model_validate(page)
        self.assertEqual(len(self.service.list(self.owner, filters, page['next_cursor'], 2)['items']), 1)
        with self.assertRaises(AppError):
            self.service.list(self.other, filters, page['next_cursor'], 2)
        event = page['items'][0]
        self.service.remove(self.owner, event['id'], event['revision'], str(uuid4()))
        with self.assertRaises(AppError) as error:
            self.service.list(self.owner, filters, page['next_cursor'], 2)
        self.assertEqual(error.exception.code, 'PAGE_CHANGED')
        sync = self.service.sync(self.owner, 0, 2)
        EventSync.model_validate(sync)
        self.assertTrue(sync['has_more'])
        # Even an old create change hydrates a tombstone after deletion.
        all_changes = self.service.sync(self.owner, 0)['items']
        self.assertTrue(next(item for item in all_changes if item['id'] == event['id'])['deleted'])
        self.assertTrue(self.service.sync(self.owner, 100000)['reset'])
        self.assertFalse(self.service.sync(self.other, 0)['items'])

    def test_database_constraints_and_owner_foreign_keys(self):
        event = self.create()
        with self.assertRaises(IntegrityError), self.db.sessions.begin() as session:
            session.execute(update(events).where(events.c.id == event['id']).values(starts_at=NOW))
        with self.assertRaises(IntegrityError), self.db.sessions.begin() as session:
            session.execute(update(events).where(events.c.id == event['id']).values(reminder_rule={}))
        with self.assertRaises(IntegrityError), self.db.sessions.begin() as session:
            session.execute(evidence.insert().values(id=str(uuid4()), learner_id=self.other, event_id=event['id'],
                quote='Owned quote', source_date=NOW, source_timezone='Asia/Karachi', source_deleted=False, policy_version='test'))

    def test_saved_event_retains_source_and_signals_chat_deletion(self):
        chat = ChatRepository(self.db.sessions)
        job = chat.begin_turn(self.owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='My algebra quiz is on October 12'))
        event = self.create()
        with self.service.repository.transactions.write(self.owner) as uow:
            uow._session.execute(evidence.insert().values(id=str(uuid4()), learner_id=self.owner, event_id=event['id'],
                quote='My algebra quiz is on October 12', source_date=NOW, source_timezone='Asia/Karachi', source_deleted=False,
                conversation_id=job['conversation_id'], policy_version='test'))
        chat.edit(self.owner, job['conversation_id'], 2, remove=True)
        current = self.service.detail(self.owner, event['id'])
        self.assertTrue(current['evidence'][0]['source_deleted'])
        self.assertEqual(current['revision'], 2)
        self.assertEqual(current['reminder_state'], 'pending')

    def test_migration_drift_and_downgrade_preserve_memory_and_chat(self):
        from app.history_management.repositories.postgres import MemoryRepository
        memory = MemoryRepository(self.db.sessions).write(self.owner, 'I prefer short summaries', 'preference', str(uuid4()))['memory']
        chat = ChatRepository(self.db.sessions)
        job = chat.begin_turn(self.owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Existing chat survives migration'))
        chat.finish(self.owner, job, dict(content='Existing answer'))
        # Compare the pre-Events schema only: later migrations intentionally add
        # tables/columns that do not exist at revision 0006.
        later_tables = {'chat_activity', 'chat_attachment', 'chat_evidence_job'}
        later_columns = {('chat_turn', 'attachment_ids'), ('rag_document_version', 'extracted_content')}
        def snapshots():
            with self.db.sessions() as session:
                return {table.name: sorted(json.dumps(dict(row), sort_keys=True, default=str) for row in
                        session.execute(select(*(column for column in table.c if (table.name, column.name) not in later_columns))).mappings())
                        for table in metadata.sorted_tables
                        if not table.name.startswith(('hm_event', 'notification_', 'checkpoint', 'assessment')) and table.name not in later_tables}
        baseline = snapshots()
        with self.db.engine.connect() as connection:
            self.assertEqual(compare_metadata(MigrationContext.configure(connection), metadata), [])
            command.downgrade(migration_config(connection), '20261008_0006')
            connection.commit()
        try:
            self.assertEqual(MemoryRepository(self.db.sessions).detail(self.owner, memory['id'])['content'], memory['content'])
            self.assertEqual(snapshots(), baseline)
        finally:
            upgrade(self.db.engine)
        self.assertEqual(snapshots(), baseline)
        with self.db.engine.connect() as connection:
            self.assertEqual(compare_metadata(MigrationContext.configure(connection), metadata), [])

    def test_context_ownership_uses_public_learner_reads_without_mastery_changes(self):
        from app.learner import LearnerEngine, ResolveLearningContextRequest
        engine = LearnerEngine(self.db.repository)
        owned = engine.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Algebra '+uuid4().hex))
        other = engine.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.other, name='Biology '+uuid4().hex))
        service = create_events_service(self.db.sessions, clock=lambda: self.now, learner=engine)
        first = service.create(self.owner, create_body(context_id=owned.context_id))['event']
        self.assertEqual(first['context_id'], owned.context_id)
        with self.assertRaises(AppError) as error:
            service.create(self.owner, create_body(context_id=other.context_id))
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(IntegrityError), self.db.sessions.begin() as session:
            session.execute(update(events).where(events.c.id == first['id']).values(context_id=other.context_id))
        completed = service.edit(self.owner, first['id'], EventEdit(expected_revision=1, client_request_id=uuid4(), status='completed'))['event']
        self.assertEqual(completed['status'], 'completed')
        from app.learner.repositories.tables import evidence as learner_evidence
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learner_evidence.learning_evidence).where(learner_evidence.learning_evidence.c.learner_id == self.owner)), 0)

    def test_capacity_and_transaction_rollback_leave_no_partial_ledger_or_receipt(self):
        self.service.repository.capacity = 1
        first = self.create()
        with self.assertRaises(AppError) as error:
            self.create()
        self.assertEqual(error.exception.code, 'CAPACITY')
        # Failure during a composed transaction rolls back event mutation and
        # both owner/module watermarks; a future producer uses the same token.
        original = self.service.summary(self.owner)['sync_revision']
        with self.assertRaises(RuntimeError), self.service.repository.transactions.write(self.owner) as uow:
            uow._session.execute(update(events).where(events.c.id == first['id']).values(title='Rolled back'))
            self.service.repository._change(uow._session, self.owner, 'event', first['id'])
            raise RuntimeError('Abort producer workflow')
        self.assertEqual(self.service.detail(self.owner, first['id'])['title'], first['title'])
        self.assertEqual(self.service.summary(self.owner)['sync_revision'], original)


if __name__ == '__main__':
    unittest.main()
