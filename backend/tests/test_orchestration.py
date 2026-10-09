import asyncio
import io
import unittest
from uuid import uuid4
from unittest.mock import Mock
from pydantic import BaseModel, ValidationError
from langchain_core.tools import StructuredTool
from sqlalchemy import select, func

from app.langchain.activity import ActivityPublisher, ActivityUpdate
from app.langchain.tool_activity import announced_tool
from app.chat.attachments import AttachmentService
from app.chat.repositories.attachments import AttachmentRepository
from app.chat.repositories.activity import ActivityRepository
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.tables import activity, attachments
from app.chat.schemas import SendTurn
from app.core.exceptions import AppError
from app.documents import DocumentContent
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class ToolActivityTests(unittest.IsolatedAsyncioTestCase):
    async def test_announces_before_execution_and_rejects_invalid_decision(self):
        trace = []
        class Input(BaseModel):
            query: str
        class Sink:
            async def publish(self, update): trace.append(update.status)
        async def search(query):
            trace.append('execute')
            return query
        wrapped = announced_tool(StructuredTool.from_function(name='history_lookup', description='Search', args_schema=Input, coroutine=search), ActivityPublisher(Sink()))
        with self.assertRaises(ValidationError):
            await wrapped.ainvoke(dict(query='old notes', tool_name='unknown', user_message='secret'))
        self.assertEqual(trace, [])
        result = await wrapped.ainvoke(dict(query='old notes', tool_name='history_lookup', user_message='Searching earlier conversations'))
        self.assertEqual(result, 'old notes')
        self.assertEqual(trace, ['planned', 'running', 'execute', 'completed'])


class DurableOrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.owner, cls.other = learner_id('alice'), learner_id('bob')
        cls.chat = ChatRepository(cls.db.sessions)
        cls.activity = ActivityRepository(cls.db.sessions)
        cls.files = AttachmentRepository(cls.db.sessions)

    @classmethod
    def tearDownClass(cls): cls.db.close()

    def turn(self, ids=()):
        body = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0,
            content='Explain the attached page', attachment_ids=list(ids))
        return body, self.chat.begin_turn(self.owner, body)

    def test_activity_is_durable_owned_attempt_fenced_and_deleted(self):
        body, job = self.turn()
        update = ActivityUpdate(step_id='reading', status='running', user_message='Reading documents')
        self.activity.append(self.owner, job, update)
        page = ActivityRepository(self.db.sessions).page(self.owner, job['conversation_id'], job['turn_id'], 1)
        self.assertEqual(page['events'][0]['user_message'], 'Reading documents')
        with self.assertRaises(AppError): self.activity.page(self.other, job['conversation_id'], job['turn_id'], 1)
        self.chat.finish(self.owner, job, error='Retry')
        newer = self.chat.begin_turn(self.owner, body.model_copy(update={'retry': True}))
        with self.assertRaises(AppError): self.activity.append(self.owner, job, update)
        self.activity.append(self.owner, newer, update)
        self.assertTrue(self.activity.page(self.owner, job['conversation_id'], job['turn_id'], 1)['reset'])
        status = self.chat.status(self.owner, job['conversation_id'])
        self.chat.edit(self.owner, job['conversation_id'], status['conversation']['revision'], remove=True)
        with self.db.sessions() as session:
            self.assertEqual(session.execute(select(func.count()).select_from(activity).where(activity.c.turn_id == job['turn_id'])).scalar_one(), 0)

    def test_attachment_extracts_once_binds_owner_and_reuses_library_pipeline(self):
        reader = Mock()
        reader.read.return_value = DocumentContent('txt', 'text/plain', [dict(text='Photosynthesis converts light energy.', page=2, method='ocr')], [], 'test-reader')
        service = AttachmentService(self.files, reader)
        file = service.upload(self.owner, io.BytesIO(b'Photosynthesis'), 'lesson.txt')
        body, job = self.turn([file['id']])
        for _ in range(2): service.extract(self.owner, file['id'], job['conversation_id'])
        self.assertEqual(reader.read.call_count, 1)
        with self.assertRaises(AppError): service.extract(self.other, file['id'], job['conversation_id'])
        rag = Mock()
        rag.accept_extracted.return_value = dict(document_id='doc', job_id='job', generation_id='gen', duplicate=False)
        result = service.add_to_library(self.owner, file['id'], job['conversation_id'], ['context'], rag)
        self.assertEqual(result['document_id'], 'doc')
        self.assertEqual(rag.accept_extracted.call_args.kwargs['extracted']['blocks'][0]['page'], 2)
        service.add_to_library(self.owner, file['id'], job['conversation_id'], ['context'], rag)
        self.assertEqual(rag.accept_extracted.call_count, 1)
        self.assertEqual(reader.read.call_count, 1)
        status = self.chat.status(self.owner, job['conversation_id'])
        self.assertEqual(status['items'][0]['attachments'][0]['id'], file['id'])
        self.chat.edit(self.owner, job['conversation_id'], status['conversation']['revision'], remove=True)
        with self.db.sessions() as session:
            self.assertIsNone(session.execute(select(attachments.c.id).where(attachments.c.id == file['id'])).first())

    def test_attachment_change_is_not_an_idempotent_turn_retry(self):
        one = self.files.create(self.owner, 'one.txt', b'one')
        two = self.files.create(self.owner, 'two.txt', b'two')
        body, job = self.turn([one['id']])
        with self.assertRaises(AppError) as error:
            self.chat.begin_turn(self.owner, body.model_copy(update={'attachment_ids': [two['id']]}))
        self.assertEqual(error.exception.code, 'CHAT_IDEMPOTENCY_CONFLICT')
