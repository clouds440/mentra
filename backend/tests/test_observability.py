import asyncio
import io
import json
import logging
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import Depends
from fastapi.testclient import TestClient
from app.core.logging import workflow_logger, configure_logging
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.observability.context import current, span, Collector, envelope, validated_envelope
from app.core.observability.formatters import EventFormatter
from app.core.observability.events import ContextFilter
from app.core.observability.middleware import ObservedFastAPI


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.items = []
    def emit(self, record):
        if hasattr(record, 'workflow_event'):
            self.items.append(dict(record.workflow_event, level=record.levelname))


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.capture = Capture()
        self.target = logging.getLogger('mentra.events')
        self.old_handlers, self.old_level, self.old_propagate = self.target.handlers, self.target.level, self.target.propagate
        self.target.handlers, self.target.propagate = [self.capture], False
        self.target.setLevel(logging.DEBUG)
    def tearDown(self):
        self.target.handlers, self.target.level, self.target.propagate = self.old_handlers, self.old_level, self.old_propagate
        self.assertIsNone(current.get())
        self.assertIsNone(span.get())

    def events(self, name):
        return [x for x in self.capture.items if x['event'] == name]

    async def test_unknown_module_nested_async_and_identity(self):
        @workflow_logger.connect_module()
        class NewModule:
            def outer(self, secret): return self.inner(secret)
            def inner(self, secret): return secret
            async def later(self): return self.inner('private')
            def added_feature(self): return 2
            @staticmethod
            def utility(): return 3
            @classmethod
            def identity(cls): return cls.__name__
            @property
            def property(self): raise AssertionError('must not evaluate')
        original = NewModule
        workflow_logger.connect_module()(NewModule)
        service = NewModule()
        self.assertIs(type(service), original)
        with workflow_logger.workflow('test'):
            self.assertEqual(service.outer('canary-secret'), 'canary-secret')
            await service.later()
            service.added_feature(); service.utility(); service.identity()
        starts = self.events('step.started')
        self.assertEqual(len(starts), 7)
        self.assertEqual(starts[1]['parent_span_id'], starts[0]['span_id'])
        self.assertNotIn('canary-secret', json.dumps(self.capture.items))
        self.assertEqual(len(self.events('workflow.completed')), 1)
        self.assertEqual(self.events('step.completed')[0]['outcome'], 'unknown')

    async def test_concurrency_threads_and_cancel(self):
        @workflow_logger.connect_module()
        class Service:
            async def wait(self): await asyncio.sleep(.001)
            def sync(self): return envelope()['trace_id']
        async def run():
            with workflow_logger.workflow('concurrent') as trace:
                await Service().wait()
                self.assertEqual(await asyncio.to_thread(Service().sync), trace.trace_id)
                return trace.trace_id
        traces = await asyncio.gather(run(), run())
        self.assertNotEqual(*traces)
        @workflow_logger.operation()
        async def cancelled(): raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError): await cancelled()
        self.assertEqual(self.events('step.completed')[-1]['outcome'], 'cancelled')

    async def test_detached_links_before_start_and_after_close(self):
        ready = asyncio.Event()
        async def work():
            await ready.wait()
            with workflow_logger.step('new.module', 'finish'): pass
        with workflow_logger.workflow('parent') as parent:
            task = workflow_logger.start_task(work(), name='detached')
            self.assertEqual(len(parent.links), 1)
        snapshot = parent.snapshot()
        ready.set(); await task
        self.assertEqual(parent.snapshot()['linked_workflows'], snapshot['linked_workflows'])
        child = self.events('workflow.completed')[-1]
        self.assertEqual(child['trace_id'], parent.trace_id)
        self.assertEqual(child['origin_workflow_id'], parent.workflow_id)

    async def test_completed_child_summary_and_bounds(self):
        with patch.object(settings, 'log_summary_max_steps', 2):
            with workflow_logger.workflow('parent') as parent:
                with workflow_logger.workflow('child'):
                    with workflow_logger.step('module.a', 'a'): pass
                with workflow_logger.step('module.b', 'b'): pass
                with workflow_logger.step('module.c', 'c'): pass
        summary = parent.snapshot()
        self.assertEqual(len(summary['operations']), 1)
        self.assertEqual(summary['linked_workflows'][0]['modules'], ['module.a'])
        self.assertTrue(summary['summary_truncated'])

    async def test_task_cancelled_before_first_execution(self):
        async def never(): raise AssertionError('must not run')
        with workflow_logger.workflow('parent') as parent:
            task=workflow_logger.start_task(never(),name='cancelled_before_start')
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            await asyncio.sleep(0)
        children=[event for event in self.events('workflow.completed') if event['workflow']=='cancelled_before_start']
        self.assertEqual(len(children),1)
        self.assertEqual(children[0]['outcome'],'cancelled')

    async def test_transaction_end_after_commit_and_rollback(self):
        states = []
        @workflow_logger.connect_module(policies={'write': {'kind':'contextmanager'}})
        class Repository:
            @contextmanager
            def write(self):
                yield
                states.append('commit')
        with Repository().write():
            self.assertEqual(len(self.events('transaction.committed')), 0)
        self.assertEqual(states, ['commit'])
        with self.assertRaises(ValueError):
            with Repository().write(): raise ValueError('private-canary')
        self.assertEqual(len(self.events('transaction.rolled_back')), 1)
        self.assertNotIn('private-canary', json.dumps(self.capture.items))

    async def test_policy_failure_and_semantic_annotation(self):
        def broken(value): raise ValueError('canary')
        @workflow_logger.connect_module(policies={'call': {'result':broken}}, default_outcome='success')
        class Service:
            def call(self):
                workflow_logger.set_outcome('degraded', code='OPTIONAL_FAILURE')
                return 7
        self.assertEqual(Service().call(), 7)
        self.assertEqual(self.events('step.completed')[-1]['outcome'], 'degraded')

    async def test_envelope_and_multipart(self):
        self.assertEqual(validated_envelope({'schema_version':1,'trace_id':'bad'}), {})
        with patch.object(settings, 'log_event_max_bytes', 8192):
            with workflow_logger.workflow('large'):
                for i in range(100):
                    with workflow_logger.step('module', 'operation'+str(i)): pass
        self.assertEqual(len(self.events('workflow.completed')), 1)
        self.assertGreater(len(self.events('summary.part')), 1)
        for record in self.capture.items:
            self.assertLess(len(json.dumps(record).encode()), 8192)

    async def test_http_status_headers_forward_annotations_and_single_end(self):
        app = ObservedFastAPI()
        register_exception_handlers(app)
        def identity(): return 'original'
        @app.get('/item/{identifier}')
        async def get(identifier: int, user=Depends(identity)):
            with workflow_logger.step('module.http', 'read'): pass
            return {'value': identifier, 'user':user}
        @app.get('/broken')
        async def broken(): raise RuntimeError('canary-private')
        app.dependency_overrides[identity] = lambda:'override'
        with TestClient(app, raise_server_exceptions=False) as client:
            result=client.get('/item/2?secret=canary')
            self.assertEqual(result.json()['user'],'override')
            self.assertEqual(len(result.headers['x-request-id']),32)
            self.assertEqual(client.get('/item/invalid').status_code,422)
            self.assertEqual(client.get('/broken').status_code,500)
            self.assertEqual(client.get('/missing').status_code,404)
        self.assertEqual(len(self.events('request.completed')),4)
        self.assertEqual(len(self.events('request.error')),1)
        self.assertEqual(len(self.events('request.post_response_error')),0)
        self.assertNotIn('canary',json.dumps(self.capture.items))
        self.assertIn('/item/{identifier}',app.openapi()['paths'])

    async def test_late_completion_freezes_snapshot(self):
        import threading
        release, entered = threading.Event(), threading.Event()
        @workflow_logger.operation()
        def slow(): entered.set(); release.wait(2)
        with workflow_logger.workflow('parent') as parent:
            task=asyncio.create_task(asyncio.to_thread(slow))
            await asyncio.to_thread(entered.wait,2)
        snapshot=parent.snapshot()
        release.set();await task
        self.assertEqual(parent.snapshot()['operations'],snapshot['operations'])
        self.assertEqual(self.events('step.completed')[-1]['execution_status'],'returned')
        self.assertTrue(self.events('step.completed')[-1]['after_parent_completion'])

    async def test_raw_asgi_stream_disconnect_and_post_body_error(self):
        from app.core.observability.middleware import RequestTracing
        async def run(app, messages):
            seen=[]
            async def receive(): return messages.pop(0) if messages else {'type':'http.disconnect'}
            async def send(value): seen.append(value)
            await RequestTracing(app)({'type':'http','method':'GET','path':'/stream','headers':[],'state':{}},receive,send)
            return seen
        async def stream(scope,receive,send):
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'first','more_body':True})
            self.assertEqual(len(self.events('request.completed')),0)
            await send({'type':'http.response.body','body':b'last','more_body':False})
        seen=await run(stream,[])
        self.assertEqual([x.get('body') for x in seen[1:]],[b'first',b'last'])
        async def disconnect(scope,receive,send): await receive()
        await run(disconnect,[{'type':'http.disconnect'}])
        self.assertEqual(self.events('request.completed')[-1]['outcome'],'cancelled')
        async def after(scope,receive,send):
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'','more_body':False})
            raise RuntimeError('private')
        with self.assertRaises(RuntimeError): await run(after,[])
        self.assertEqual(len(self.events('request.completed')),3)
        self.assertEqual(len(self.events('request.post_response_error')),1)

    async def test_actual_application_startup_and_shutdown(self):
        from types import SimpleNamespace
        from contextlib import ExitStack
        from app import main
        closed=[]
        vector=SimpleNamespace(close=lambda:closed.append('vector'))
        rag=SimpleNamespace(close=lambda:closed.append('rag'))
        history=SimpleNamespace(events=SimpleNamespace(repository=SimpleNamespace()))
        with ExitStack() as patches:
            for name,value in {
                'configure_logging':None, 'init_db':None,
                'SentenceTransformerEmbeddingService':SimpleNamespace(),
                'QdrantVectorStore':vector,'create_learner_engine':SimpleNamespace(),
                'create_auth_service':SimpleNamespace(), 'create_student_profile_service':SimpleNamespace(),
                'create_rag_service':rag,'create_history_management':history,'get_session_factory':None,
            }.items():
                patches.enter_context(patch.object(main,name,return_value=value))
            patches.enter_context(patch('app.assessments.service.create_assessments',return_value=SimpleNamespace()))
            patches.enter_context(patch('app.history_management.events.proposal_service.create_event_proposals',return_value=SimpleNamespace()))
            patches.enter_context(patch('app.chat.attachments.create_document_reader',return_value=SimpleNamespace()))
            app=main.create_app()
            # Importing app.main initializes process logging, so restore the test capture.
            self.target.handlers,self.target.propagate=[self.capture],False
            self.target.setLevel(logging.DEBUG)
            async with app.router.lifespan_context(app):
                self.assertIs(app.state.rag_service,rag)
                self.assertIsNone(current.get())
        self.assertEqual(closed,['rag','vector'])
        startup=[event for event in self.events('workflow.completed') if event['workflow']=='backend.startup']
        self.assertEqual(startup[0]['outcome'],'success')
        self.assertEqual(len(self.events('process.stopped')),1)

    async def test_quiet_nested_failure_is_visible(self):
        with workflow_logger.workflow('poll',quiet=True):
            with workflow_logger.step('poll.module','normal'): pass
            with self.assertRaises(ValueError):
                with workflow_logger.step('poll.module','failure'): raise ValueError('private')
        self.assertEqual(self.events('step.started')[0]['level'],'DEBUG')
        self.assertEqual(self.events('step.completed')[-1]['level'],'WARNING')

    async def test_inherited_function_collection_and_lazy_result(self):
        class Base:
            def inherited(self): return 3
        @workflow_logger.connect_module(include_inherited=True)
        class Child(Base):
            def own(self): return self.inherited()
        self.assertEqual(Child().own(),3)
        self.assertFalse(getattr(Base.inherited,'__mentra_observed__',False))
        def feature(): return 'ok'
        features=workflow_logger.connect_module()({'feature':feature})
        self.assertEqual(features['feature'](),'ok')
        @workflow_logger.connect_module()
        class Lazy:
            def iterate(self): yield 1
        result=Lazy().iterate()
        self.assertEqual(list(result),[1])
        self.assertTrue(self.events('step.completed')[-1]['result']['lazy_result'])


class FormatTests(unittest.TestCase):
    def test_json_and_exception_privacy(self):
        try: raise ValueError('secret-private')
        except ValueError:
            import sys
            record=logging.LogRecord('httpx',logging.ERROR,'',1,'private %s',('private',),sys.exc_info())
        result=EventFormatter('json').format(record)
        self.assertNotIn('secret-private',result)
        self.assertNotIn('private',result)
        self.assertTrue(json.loads(result)['timestamp'].endswith('Z'))

    def test_server_error_dedup_preserves_unknown_error(self):
        from app.core.observability.errors import mark_reported,ServerErrorFilter
        error=RuntimeError('private')
        record=logging.LogRecord('uvicorn.error',logging.ERROR,'',1,'private',(),(RuntimeError,error,None))
        self.assertTrue(ServerErrorFilter().filter(record))
        mark_reported(error)
        self.assertFalse(ServerErrorFilter().filter(record))


import os
@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires isolated PostgreSQL')
class DurableLoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from testing.postgres import PostgresSandbox
        self.db=PostgresSandbox()
        self.addCleanup(self.db.close)

    async def test_chat_origin_and_private_status(self):
        from app.chat.service import ConversationService
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.repositories.tables import turns
        from app.chat.schemas import SendTurn
        from testing.identities import learner_id
        from uuid import uuid4
        from sqlalchemy import select
        service=ConversationService(ChatRepository(self.db.sessions))
        body=SendTurn(conversation_id=uuid4(),client_turn_id=uuid4(),expected_revision=0,content='Hello')
        async def generate(history,selection): return dict(role='assistant',content='Hello')
        with workflow_logger.workflow('origin') as origin:
            result=await service.send(learner_id('alice'),body,generate)
        self.assertEqual(result['turn']['state'],'SUCCEEDED')
        self.assertNotIn('log_context',json.dumps(result,default=str))
        with self.db.sessions() as session:
            saved=session.scalar(select(turns.c.log_context).where(turns.c.id==str(body.client_turn_id)))
        self.assertEqual(saved['trace_id'],origin.trace_id)
        self.assertEqual(saved['origin_workflow_id'],origin.workflow_id)
        self.assertEqual(origin.snapshot()['linked_workflows'][0]['state'],'completed')
        await service.close()

    async def test_additive_migration_preserves_legacy_records(self):
        from alembic import command
        from sqlalchemy import select,func
        from app.db.migrate import migration_config,upgrade
        from app.chat.repositories.tables import conversations,turns
        from testing.identities import learner_id
        from uuid import uuid4
        from datetime import datetime,timezone
        with self.db.engine.begin() as connection:
            command.downgrade(migration_config(connection),'20261009_0013')
        owner,cid,tid=learner_id('alice'),str(uuid4()),str(uuid4())
        stamp=datetime.now(timezone.utc)
        with self.db.engine.begin() as connection:
            connection.execute(conversations.insert().values(id=cid,learner_id=owner,title='legacy',selection={},revision=1,message_count=1,created_at=stamp,updated_at=stamp))
            connection.execute(turns.insert().values(id=tid,learner_id=owner,conversation_id=cid,request_hash='legacy',user_sequence=1,state='FAILED',attempt=1,selection={},created_at=stamp))
        upgrade(self.db.engine)
        with self.db.engine.connect() as connection:
            row=connection.execute(select(turns).where(turns.c.id==tid)).mappings().one()
        self.assertEqual(row['request_hash'],'legacy')
        self.assertIsNone(row['log_context'])


if __name__ == '__main__': unittest.main()
