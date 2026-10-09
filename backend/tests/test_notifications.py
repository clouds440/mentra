import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, func, delete
from app.notifications.repositories.postgres import NotificationRepository
from app.notifications.repositories.tables import inbox, receipts
from app.notifications.service import NotificationsService
from app.notifications.schemas import NotificationDraft, NotificationPreferencesEdit, InboxEdit
from app.history_management.events.factory import create_events_service
from app.history_management.events.schemas import EventCreate, EventEdit
from app.core.exceptions import AppError
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated TEST_DATABASE_URL')
class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.owner, self.other = learner_id('alice'), learner_id('bob')
        self.now = datetime(2026, 10, 9, 6, tzinfo=timezone.utc)
        self.repository = NotificationRepository(self.db.sessions, clock=lambda: self.now)
        self.service = NotificationsService(self.repository, producers=('events', 'test_assessment'))
        self.events = create_events_service(self.db.sessions, clock=lambda: self.now)
        self.events.repository.notifications = self.service

    def draft(self, **fields):
        return NotificationDraft(**(dict(producer='test_assessment', delivery_key='assessment-1',
            kind='assessment_ready', title='Assessment ready', due_at=self.now) | fields))

    def publish(self, draft=None):
        with self.repository.transactions.write(self.owner) as tx:
            return self.service.publish(tx, draft or self.draft())

    def event(self):
        return self.events.create(self.owner, EventCreate(title='Quiz', kind='quiz', timezone='UTC',
            starts_at=self.now+timedelta(hours=2), client_request_id=uuid4()))['event']

    def test_concurrent_delivery_one_lifetime_after_dismiss_and_reopen(self):
        event = self.event()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.events.repository.deliver_reminders(), range(8)))
        page = self.service.inbox(self.owner)
        self.assertEqual(len(page['items']), 1)
        notification = page['items'][0]
        self.service.edit(self.owner, notification['id'], InboxEdit(expected_revision=1, action='dismiss'))
        for status in ('completed', 'scheduled'):
            event = self.events.edit(self.owner, event['id'], EventEdit(expected_revision=event['revision'],
                client_request_id=uuid4(), status=status))['event']
        self.events.repository.deliver_reminders()
        self.assertEqual(self.service.inbox(self.owner)['unread_count'], 0)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(receipts)), 1)

    def test_second_producer_idempotency_survives_inbox_cleanup(self):
        result = self.publish()
        with self.repository.transactions.write(self.owner) as tx:
            tx._session.execute(delete(inbox).where(inbox.c.id == result['notification_id']))
        self.assertEqual(self.publish()['outcome'], 'already_delivered')
        self.assertEqual(self.service.inbox(self.owner)['items'], [])
        with self.assertRaises(AppError): self.publish(self.draft(producer='unregistered'))

    def test_disabled_interval_is_never_backfilled(self):
        self.event()
        self.service.set_preferences(self.owner, NotificationPreferencesEdit(expected_revision=0, enabled=False))
        self.now += timedelta(minutes=1)
        self.service.set_preferences(self.owner, NotificationPreferencesEdit(expected_revision=1, enabled=True))
        self.events.repository.deliver_reminders()
        self.assertEqual(self.service.inbox(self.owner)['items'], [])
        self.assertEqual(self.publish()['outcome'], 'disabled')
        self.now += timedelta(seconds=1)
        self.assertEqual(self.publish()['outcome'], 'delivered')

    def test_atomic_rollback_ownership_revision_and_sync(self):
        with self.assertRaises(RuntimeError):
            with self.repository.transactions.write(self.owner) as tx:
                self.service.publish(tx, self.draft())
                raise RuntimeError('rollback')
        self.assertEqual(self.service.inbox(self.owner)['items'], [])
        result = self.publish()
        with self.assertRaises(AppError) as denied:
            self.service.edit(self.other, result['notification_id'], InboxEdit(expected_revision=1, action='read'))
        self.assertEqual(denied.exception.status_code, 404)
        self.assertEqual(self.service.sync(self.other, 0)['items'], [])
        self.service.edit(self.owner, result['notification_id'], InboxEdit(expected_revision=1, action='read'))
        with self.assertRaises(AppError):
            self.service.edit(self.owner, result['notification_id'], InboxEdit(expected_revision=1, action='dismiss'))
        self.assertEqual(self.service.inbox(self.owner)['unread_count'], 0)
        self.assertEqual(len(self.service.sync(self.owner, 0)['items']), 2)

    def test_event_removal_removes_inbox_but_preserves_receipt(self):
        event = self.event()
        self.events.repository.deliver_reminders()
        self.events.remove(self.owner, event['id'], event['revision'], str(uuid4()))
        self.assertEqual(self.service.inbox(self.owner)['items'], [])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(receipts)), 1)
