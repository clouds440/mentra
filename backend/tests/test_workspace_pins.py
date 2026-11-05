import os
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.workspace_pins import router
from app.chat.repositories.history_reader import ChatReadFacade
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.core.exceptions import AppError
from app.student_profile.dependencies import require_onboarded_identity
from testing.identities import learner_id
from testing.postgres import PostgresSandbox


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requires disposable PostgreSQL')
class WorkspacePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = PostgresSandbox()
        cls.addClassCleanup(cls.database.close)
        cls.repository = ChatRepository(cls.database.sessions)

    def test_pin_deduplicates_and_cannot_be_listed_or_deleted_by_another_owner(self):
        app = FastAPI()
        app.include_router(router)
        app.state.conversation_service = SimpleNamespace(repository=self.repository)
        owner = SimpleNamespace(learner_id=learner_id('alice'))
        app.dependency_overrides[require_onboarded_identity] = lambda: owner
        source = {'kind': 'web', 'title': 'Article', 'url': 'https://example.org/article#section'}
        with TestClient(app) as client:
            path = '/workspace/pins'
            first = client.post(path, json=source)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.headers['cache-control'], 'no-store')
            pin = first.json()
            self.assertEqual(client.post(path, json={**source, 'title': 'Same page'}).json(), pin)
            owner.learner_id = learner_id('bob')
            self.assertEqual(client.get(path).json(), [])
            self.assertEqual(client.delete(path + '/' + pin['id']).status_code, 204)
            owner.learner_id = learner_id('alice')
            self.assertEqual(client.get(path).json(), [pin])
            self.assertEqual(client.delete(path + '/' + pin['id']).status_code, 204)
            self.assertEqual(client.get(path).json(), [])

    def test_annotation_is_saved_on_the_user_turn_and_part_of_its_idempotency(self):
        owner = learner_id('alice')
        source = {'kind': 'chat', 'title': 'Mentra response'}
        page = {'mode': 'page', 'source': {'kind': 'web', 'title': 'Article', 'url': 'https://example.org/article'}}
        turn = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='',
            source_annotations=[{'source': source, 'text': 'Exact words.'}, page])
        self.repository.begin_turn(owner, turn)
        changed = SendTurn(**{**turn.model_dump(), 'source_annotations': [{'source': source, 'text': 'Changed.'}]})
        with self.assertRaises(AppError):
            self.repository.begin_turn(owner, changed)
        conversation = str(turn.conversation_id)
        [message] = self.repository.history(owner, conversation)['items']
        self.assertEqual(message['content'], '')
        self.assertEqual(message['source_annotations'], [{'source': source, 'text': 'Exact words.'}, page])
        exchange = ChatReadFacade(self.repository).saved_exchange(owner, conversation, message['id'])
        self.assertEqual(exchange.messages[0].source_annotations[0].text, 'Exact words.')
        self.assertEqual(exchange.messages[0].source_annotations[1].model_dump(mode='json'), page)
