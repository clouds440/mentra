import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, func
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.management import ChatManagement
from app.chat.repositories.history_reader import ChatReadFacade
from app.chat.repositories.tables import conversations, messages, management_jobs
from app.chat.schemas import SendTurn, OrganizeConversation, BulkChatAction
from app.core.exceptions import AppError
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated database')
class ChatOrganizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        # Different owners isolate test cases while retaining one migrated schema.
        self.owner, self.other = learner_id('alice'), learner_id('bob')
        with self.db.sessions.begin() as session:
            session.execute(management_jobs.delete())
            # Existing deletion pipeline cleans dependents; tests use new UUID chats.
            session.execute(conversations.update().values(archived_at=func.now(), pinned_at=None))
        self.repo = ChatRepository(self.db.sessions)
        self.manager = ChatManagement(self.repo)

    def chat(self, owner=None):
        owner = owner or self.owner
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Organization needle ' + str(uuid4()))
        job = self.repo.begin_turn(owner, request)
        self.repo.finish(owner, job, dict(content='Saved explanation'))
        return self.repo.status(owner, str(request.conversation_id))['conversation']

    def organize(self, chat, **change):
        return self.manager.organize(self.owner, chat['id'], OrganizeConversation(expected_revision=chat['revision'], **change))

    def queue(self, chats, action='archive', identifier=None, owner=None):
        body = BulkChatAction(client_request_id=identifier or uuid4(), action=action, items=[dict(conversation_id=c['id'], expected_revision=c['revision']) for c in chats])
        return self.manager.enqueue(owner or self.owner, body), body

    def test_pin_section_survives_sync_and_metadata_preserves_activity_order(self):
        chat = self.chat()
        pinned = self.organize(chat, pinned=True)
        self.assertIsNotNone(pinned['pinned_at'])
        self.assertEqual(pinned['updated_at'], chat['updated_at'])
        self.assertNotIn(chat['id'], [r['id'] for r in self.repo.recent(self.owner)['items']])
        self.assertIn(chat['id'], [r['id'] for r in self.repo.sync(self.owner)['conversations']])
        unpinned = self.organize(pinned, pinned=False)
        self.assertIsNone(unpinned['pinned_at'])
        self.assertIn(chat['id'], [r['id'] for r in self.repo.recent(self.owner)['items']])

    def test_archive_keeps_messages_unpins_and_search_requires_opt_in(self):
        chat = self.chat()
        reader = ChatReadFacade(self.repo)
        phrase = self.repo.status(self.owner, chat['id'])['items'][0]['content']
        pinned = self.organize(chat, pinned=True)
        archived = self.organize(pinned, archived=True)
        self.assertIsNone(archived['pinned_at'])
        self.assertEqual(reader.search_saved(self.owner, phrase).items, [])
        hits = reader.search_saved(self.owner, phrase, include_archived=True).items
        self.assertTrue(hits)
        self.assertTrue(all(str(hit.conversation_id) == chat['id'] and hit.archived_at for hit in hits))
        self.assertEqual(len(self.repo.status(self.owner, chat['id'])['items']), 2)
        with self.assertRaises(AppError): self.organize(archived, pinned=True)
        restored = self.organize(archived, archived=False)
        self.assertIsNone(restored['archived_at'])
        self.assertTrue(reader.search_saved(self.owner, phrase).items)

    def test_batch_admission_is_atomic_owned_and_revision_checked(self):
        first, second, foreign = self.chat(), self.chat(), self.chat(self.other)
        for invalid in ([first, dict(second, revision=999)], [first, foreign]):
            with self.assertRaises(AppError): self.queue(invalid)
            self.assertIsNone(self.repo.status(self.owner, first['id'])['conversation']['pending_action'])
        with self.assertRaises(AppError): self.manager.organize(self.other, first['id'], OrganizeConversation(expected_revision=first['revision'], pinned=True))

    def test_queue_is_durable_idempotent_private_and_does_not_delete_inline(self):
        chats = [self.chat(), self.chat()]
        job, body = self.queue(chats, 'delete')
        self.assertEqual(job['state'], 'queued')
        self.assertNotIn('learner_id', job)
        self.assertEqual(self.manager.enqueue(self.owner, body)['id'], job['id'])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(messages).where(messages.c.conversation_id.in_([c['id'] for c in chats]))), 4)
        with self.assertRaises(AppError): self.manager.status(self.other, job['id'])
        with self.assertRaises(AppError): self.manager.enqueue(self.other, body)
        with self.assertRaises(AppError): self.manager.enqueue(self.owner, body.model_copy(update={'action':'archive'}))
        with self.assertRaises(AppError): self.repo.begin_turn(self.owner, SendTurn(conversation_id=chats[0]['id'], client_turn_id=uuid4(), expected_revision=chats[0]['revision'] + 1, content='Too late'))
        self.assertTrue(self.manager.run_once())
        self.assertEqual(len(self.manager.status(self.owner, job['id'])['completed_ids']), 1)
        self.assertTrue(self.manager.run_once())
        self.assertEqual(self.manager.status(self.owner, job['id'])['state'], 'completed')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(messages).where(messages.c.conversation_id.in_([c['id'] for c in chats]))), 0)
        self.assertEqual(self.manager.enqueue(self.owner, body)['state'], 'completed')

    def test_partial_failure_rolls_back_content_and_releases_failed_selection(self):
        chats = [self.chat(), self.chat()]
        job, _ = self.queue(chats, 'delete')
        original = self.repo._edit_in_session
        failed_id = sorted(c['id'] for c in chats)[0]
        def fail_after_delete(session, owner, row, state, **kwargs):
            result = original(session, owner, row, state, **kwargs)
            if row['id'] == failed_id: raise AppError('TEST_FAILURE', 'Synthetic failure', 409)
            return result
        with patch.object(self.repo, '_edit_in_session', side_effect=fail_after_delete):
            self.manager.run_once()
            self.manager.run_once()
        result = self.manager.status(self.owner, job['id'])
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(len(result['completed_ids']), 1)
        self.assertEqual(result['failed_items'][0]['conversation_id'], failed_id)
        saved = self.repo.status(self.owner, failed_id)
        self.assertEqual(len(saved['items']), 2)
        self.assertIsNone(saved['conversation']['pending_action'])

    def test_worker_crash_rolls_back_receipt_and_recovers_after_restart(self):
        chat = self.chat()
        job, _ = self.queue([chat], 'delete')
        original = self.repo._edit_in_session
        def crash(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('Process failure')
        with patch.object(self.repo, '_edit_in_session', side_effect=crash):
            with self.assertRaises(RuntimeError): self.manager.run_once()
        self.assertEqual(self.manager.status(self.owner, job['id'])['completed_ids'], [])
        restarted = ChatManagement(ChatRepository(self.db.sessions))
        self.assertTrue(restarted.run_once())
        self.assertEqual(restarted.status(self.owner, job['id'])['state'], 'completed')

    def test_two_workers_process_each_chat_once_and_unarchive_returns_to_recents(self):
        chats = [self.chat(), self.chat(), self.chat()]
        job, _ = self.queue(chats)
        with ThreadPoolExecutor(max_workers=2) as pool:
            for _ in range(4): list(pool.map(lambda _: self.manager.run_once(), range(2)))
        result = self.manager.status(self.owner, job['id'])
        self.assertEqual(set(result['completed_ids']), {c['id'] for c in chats})
        self.assertEqual(result['failed_items'], [])
        self.assertFalse(self.manager.run_once())
        archived = [self.repo.status(self.owner, c['id'])['conversation'] for c in chats]
        job, _ = self.queue(archived, 'unarchive')
        for _ in chats: self.manager.run_once()
        self.assertEqual(self.manager.status(self.owner, job['id'])['state'], 'completed')
        self.assertTrue({c['id'] for c in chats}.issubset({r['id'] for r in self.repo.recent(self.owner)['items']}))

    def test_archive_pagination_has_no_duplicates(self):
        chats = [self.organize(self.chat(), archived=True) for _ in range(3)]
        seen, cursor = [], None
        while True:
            page = self.repo.recent(self.owner, cursor, 2, archived=True)
            seen.extend(c['id'] for c in page['items'])
            cursor = page['next_cursor']
            if not cursor: break
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue({c['id'] for c in chats}.issubset(set(seen)))

    def test_api_contract_exposes_metadata_and_durable_receipts_without_caching(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.conversations import router
        from app.student_profile.dependencies import require_onboarded_identity
        from app.auth.dependencies import require_identity
        chat = self.chat()
        app = FastAPI()
        app.state.conversation_service = SimpleNamespace(repository=self.repo)
        app.include_router(router, prefix='/api/v1')
        identity = lambda: SimpleNamespace(learner_id=self.owner)
        app.dependency_overrides[require_identity] = identity
        app.dependency_overrides[require_onboarded_identity] = identity
        with TestClient(app) as client:
            response = client.patch(f"/api/v1/conversations/{chat['id']}/organization", json={'expected_revision':chat['revision'],'pinned':True})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            pinned = response.json()
            response = client.post('/api/v1/conversations/bulk', json={'client_request_id':str(uuid4()),'action':'archive','items':[{'conversation_id':chat['id'],'expected_revision':pinned['revision']}]})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            identifier = response.json()['id']
            self.assertEqual(response.json()['state'], 'queued')
            self.manager.run_once()
            response = client.get(f'/api/v1/conversations/bulk/{identifier}')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.json()['state'], 'completed')
            response = client.get('/api/v1/conversations', params={'archived':'true'})
            self.assertIn(chat['id'], [row['id'] for row in response.json()['items']])
            response = client.post('/api/v1/conversations/bulk', json={'client_request_id':str(uuid4()),'action':'delete','items':[]})
            self.assertEqual(response.status_code, 422)

    def test_readiness_includes_background_chat_work(self):
        from datetime import datetime, timezone, timedelta
        from app.db.worker_status import queue_status
        job, _ = self.queue([self.chat()])
        result = queue_status(self.db.sessions, clock=lambda:datetime.now(timezone.utc)+timedelta(minutes=3))
        queue = next(row for row in result['queues'] if row['queue'] == 'chat_management_job')
        self.assertEqual(queue['pending'], 1)
        self.assertEqual(queue['active_leases'], 0)
        self.assertEqual(queue['status'], 'stalled')
        self.manager.run_once()
        queue = next(row for row in queue_status(self.db.sessions)['queues'] if row['queue'] == 'chat_management_job')
        self.assertEqual(queue['status'], 'idle')


class ChatOrganizationValidationTests(unittest.TestCase):
    def test_batch_bounds_uniqueness_and_explicit_changes(self):
        item = dict(conversation_id=uuid4(), expected_revision=1)
        for items in ([], [item, item], [dict(conversation_id=uuid4(), expected_revision=1) for _ in range(101)]):
            with self.assertRaises(ValidationError): BulkChatAction(client_request_id=uuid4(), action='delete', items=items)
        for change in ({}, {'pinned':True,'archived':False}, {'pinned':True,'owner':'someone'}):
            with self.assertRaises(ValidationError): OrganizeConversation(expected_revision=1, **change)
