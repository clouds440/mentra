import asyncio
import unittest
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, text
from langchain_core.messages import AIMessage
from app.chat.repositories.postgres import ChatRepository, now
from app.chat.repositories.tables import turns, messages
from app.chat.schemas import SendTurn, ResumeTurn
from app.chat.service import ConversationService
from app.core.exceptions import AppError
from app.langchain.graphs.tool_coordinator import coordinate
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class ResponseResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.repo = ChatRepository(cls.db.sessions)
        cls.owner, cls.other = learner_id('alice'), learner_id('bob')

    @classmethod
    def tearDownClass(cls): cls.db.close()

    def request(self):
        return SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Explain joins')

    def test_completed_graph_steps_survive_stop_restart_and_resume(self):
        async def scenario():
            service = ConversationService(self.repo)
            request = self.request()
            calls = {'first':0, 'tool':0, 'final':0}
            waiting = asyncio.Event()
            async def generate(history, selection, scope):
                async def model(state):
                    if state['iteration'] == 0:
                        calls['first'] += 1
                        return dict(response=AIMessage(content='', tool_calls=[dict(name='lookup', args={}, id='one')]), done=False)
                    calls['final'] += 1
                    if calls['final'] == 1:
                        waiting.set()
                        await asyncio.sleep(30)
                    return dict(response=AIMessage(content='A join combines matching rows.'), done=True)
                async def tool(state):
                    calls['tool'] += 1
                    return dict(iteration=state['iteration']+1)
                value = await coordinate(model, tool, checkpoint=scope['_response_checkpoint'])
                return dict(content=value.content)
            await service.send(self.owner, request, generate, with_scope=True, wait=False)
            await asyncio.wait_for(waiting.wait(), 5)
            cid, tid = str(request.conversation_id), str(request.client_turn_id)
            paused = await service.stop(self.owner, cid, tid, 1)
            self.assertTrue(paused['turn']['can_resume'])
            await service.close()
            restarted = ConversationService(self.repo)
            await restarted.resume(self.owner, cid, tid, ResumeTurn(attempt=1, expected_revision=paused['conversation']['revision']), generate)
            for _ in range(60):
                page = self.repo.status(self.owner, cid)
                if page['turn']['state'] != 'RUNNING': break
                await asyncio.sleep(.05)
            await restarted.close()
            self.assertEqual(page['turn']['state'], 'SUCCEEDED', page['turn'])
            self.assertEqual(calls, dict(first=1, tool=1, final=2))
            self.assertEqual(len(page['items']), 2)
            self.assertEqual(page['items'][-1]['content'], 'A join combines matching rows.')
            self.assertEqual(page['turn']['id'], tid)
            self.assertEqual(page['turn']['attempt'], 2)
            with self.db.sessions() as session:
                count = session.scalar(text("SELECT count(*) FROM checkpoints WHERE thread_id LIKE :prefix"), {'prefix':f'response-v1:{self.owner}:{tid}%'})
                self.assertEqual(count, 0)
        asyncio.run(scenario())

    def test_expiry_owner_and_latest_response_fences(self):
        request = self.request()
        job = self.repo.begin_turn(self.owner, request)
        cid, tid = job['conversation_id'], job['turn_id']
        self.repo.stop_turn(self.owner, cid, tid, 1)
        page = self.repo.status(self.owner, cid)
        with self.assertRaises(AppError): self.repo.resume_turn(self.other, cid, tid, 1, page['conversation']['revision'])
        with self.assertRaises(AppError): self.repo.resume_turn(self.owner, cid, tid, 2, page['conversation']['revision'])
        with self.db.sessions.begin() as session:
            session.execute(update(turns).where(turns.c.id == tid).values(resume_until=now()-timedelta(seconds=1)))
        self.assertFalse(self.repo.status(self.owner, cid)['turn']['can_resume'])
        with self.assertRaises(AppError): self.repo.resume_turn(self.owner, cid, tid, 1, page['conversation']['revision'])
        next_request = request.model_copy(update={'client_turn_id':uuid4(), 'content':'A different question', 'expected_revision':page['conversation']['revision']})
        self.assertTrue(self.repo.begin_turn(self.owner, next_request)['run'])
        with self.db.sessions() as session:
            self.assertEqual(len(session.scalars(select(messages.c.id).where(messages.c.conversation_id == cid)).all()), 3)

    def test_retry_resumes_failed_node_instead_of_replaying_completed_tools(self):
        async def scenario():
            service = ConversationService(self.repo)
            request = self.request()
            calls = dict(first=0, tool=0, final=0)
            async def generate(history, selection, scope):
                async def model(state):
                    if not state['iteration']:
                        calls['first'] += 1
                        return dict(response=AIMessage(content=''), done=False)
                    calls['final'] += 1
                    if calls['final'] == 1: raise TimeoutError('synthetic provider failure')
                    return dict(response=AIMessage(content='Recovered answer'), done=True)
                async def tool(state):
                    calls['tool'] += 1
                    return dict(iteration=1)
                result = await coordinate(model, tool, checkpoint=scope['_response_checkpoint'])
                return dict(content=result.content)
            page = await service.send(self.owner, request, generate, with_scope=True)
            self.assertEqual(page['turn']['state'], 'FAILED')
            retry = request.model_copy(update={'retry':True, 'expected_revision':page['conversation']['revision']})
            page = await service.send(self.owner, retry, generate, with_scope=True)
            self.assertEqual(page['turn']['state'], 'SUCCEEDED', page)
            self.assertEqual(calls, dict(first=1, tool=1, final=2))
            self.assertEqual(len(page['items']), 2)
            await service.close()
        asyncio.run(scenario())

    def test_resume_receipt_is_idempotent_and_rejects_changed_request(self):
        request = self.request()
        job = self.repo.begin_turn(self.owner, request)
        cid, tid = job['conversation_id'], job['turn_id']
        self.repo.stop_turn(self.owner, cid, tid, 1)
        revision = self.repo.status(self.owner, cid)['conversation']['revision']
        operation = str(uuid4())
        self.assertTrue(self.repo.resume_turn(self.owner, cid, tid, 1, revision, operation=operation, fingerprint='same')['run'])
        self.assertFalse(self.repo.resume_turn(self.owner, cid, tid, 1, revision, operation=operation, fingerprint='same')['run'])
        with self.assertRaises(AppError): self.repo.resume_turn(self.owner, cid, tid, 1, revision, operation=operation, fingerprint='changed')
        with self.assertRaises(AppError): self.repo.stop_turn(self.owner, cid, tid, 1)

    def test_typed_change_continues_same_response_and_transport_retry_replays_receipt(self):
        from types import SimpleNamespace
        from unittest.mock import patch, AsyncMock
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.conversations import router
        from app.student_profile.dependencies import require_onboarded_identity
        from app.chat.response import ChatResponse
        request = self.request()
        job = self.repo.begin_turn(self.owner, request)
        cid, tid = job['conversation_id'], job['turn_id']
        self.repo.stop_turn(self.owner, cid, tid, 1)
        page = self.repo.status(self.owner, cid)
        body = SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=page['conversation']['revision'],
            content='Make the explanation shorter', resume_from=tid)
        app = FastAPI()
        app.include_router(router)
        app.state.conversation_service = ConversationService(self.repo)
        app.state.chat_service = SimpleNamespace(_llm=None)
        app.dependency_overrides[require_onboarded_identity] = lambda: SimpleNamespace(learner_id=self.owner)
        captured = []
        async def generate(history, *args):
            captured.append(history)
            return ChatResponse(content='Shorter join explanation')
        with patch('app.api.routes.conversations.generate_reply', side_effect=generate), \
                patch('app.langchain.response_continuation.is_continuation', AsyncMock(return_value='change')):
            with TestClient(app) as client:
                response = client.post('/conversations/turns?stream=true', json=body.model_dump(mode='json'))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['turn']['id'], tid)
                import time
                for _ in range(60):
                    status = client.get(f'/conversations/{cid}/status').json()
                    if status['turn']['state'] != 'RUNNING': break
                    time.sleep(.02)
                self.assertEqual(status['turn']['state'], 'SUCCEEDED', status)
                replay = client.post('/conversations/turns?stream=true', json=body.model_copy(update={'retry':True}).model_dump(mode='json'))
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json()['turn']['id'], tid)
                newer = SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=status['conversation']['revision'], content='A different question')
                sent = client.post('/conversations/turns?stream=true', json=newer.model_dump(mode='json'))
                self.assertEqual(sent.status_code, 200, sent.text)
                for _ in range(60):
                    latest = client.get(f'/conversations/{cid}/status').json()
                    if latest['turn']['state'] != 'RUNNING': break
                    time.sleep(.02)
                replay = client.post('/conversations/turns?stream=true', json=body.model_copy(update={'retry':True}).model_dump(mode='json'))
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json()['turn']['id'], str(newer.client_turn_id))
                self.assertEqual(replay.json()['continued_turn_id'], tid)
        self.assertEqual(len(captured), 2)
        self.assertIn(body.content, captured[0][-1][1])
        self.assertEqual(len(self.repo.history(self.owner, cid)['items']), 4)

    def test_resume_does_not_restore_invalidated_private_memory_context(self):
        from app.langchain.response_runtime import ResponseRuntime
        scope = {'_memory_summary_fence': {'revision':2}}
        conversation = []
        runtime = ResponseRuntime(conversation, scope, None, None, None)
        with self.assertRaises(AppError) as caught:
            runtime.restore({'scope': {'_memory_summary_fence': {'revision':1}}, 'conversation':[]})
        self.assertEqual(caught.exception.code, 'CHAT_RESUME_CONTEXT_CHANGED')
        self.assertEqual(scope['_memory_summary_fence']['revision'], 2)

    def test_disconnect_during_resume_admission_still_starts_generation(self):
        async def scenario():
            from threading import Event
            from unittest.mock import patch
            service = ConversationService(self.repo)
            request = self.request()
            job = self.repo.begin_turn(self.owner, request)
            self.repo.stop_turn(self.owner, job['conversation_id'], job['turn_id'], 1)
            page = self.repo.status(self.owner, job['conversation_id'])
            entered, release, started = Event(), Event(), asyncio.Event()
            original = self.repo.resume_turn
            def blocked(*args):
                entered.set()
                if not release.wait(5): raise TimeoutError()
                return original(*args)
            async def generate(history, selection):
                started.set()
                return dict(content='Resumed after disconnect')
            with patch.object(self.repo, 'resume_turn', side_effect=blocked):
                caller = asyncio.create_task(service.resume(self.owner, job['conversation_id'], job['turn_id'],
                    ResumeTurn(attempt=1, expected_revision=page['conversation']['revision']), generate, with_scope=False))
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                caller.cancel()
                with self.assertRaises(asyncio.CancelledError): await caller
                release.set()
                await asyncio.wait_for(started.wait(), 5)
                for _ in range(60):
                    if self.repo.status(self.owner, job['conversation_id'])['turn']['state'] == 'SUCCEEDED': break
                    await asyncio.sleep(.05)
                self.assertEqual(self.repo.status(self.owner, job['conversation_id'])['turn']['state'], 'SUCCEEDED')
            await service.close()
        asyncio.run(scenario())
