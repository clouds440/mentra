import os
import unittest
from uuid import uuid4
from types import SimpleNamespace
from app.core.exceptions import AppError
from app.speech.transient import transcribe_direct
from testing.postgres import PostgresSandbox
from testing.files import create_test_files
from testing.identities import learner_id


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Dedicated PostgreSQL required')
class DirectSpeechTests(unittest.TestCase):
    def setUp(self):
        self.db=PostgresSandbox();self.addCleanup(self.db.close)
        self.files=create_test_files(self.db.sessions)
        self.calls=0
        def transcribe(data,language):
            self.calls+=1
            return dict(text='ایک equation',language='ur',language_probability=.9,duration_seconds=.3,processing_seconds=.01)
        self.processor=SimpleNamespace(maximum=100,timeout=1,transcribe=transcribe)
        self.owner,self.other=learner_id('alice'),learner_id('bob')

    def test_replay_and_ownership_without_storage_roundtrips(self):
        operation=str(uuid4())
        result=transcribe_direct(self.files,self.processor,self.owner,operation,b'audio')
        self.assertEqual(transcribe_direct(self.files,self.processor,self.owner,operation,b'audio'),result)
        self.assertEqual(self.calls,1)
        self.assertEqual((self.files.provider.uploads,self.files.provider.downloads),(0,0))
        for owner,data in ((self.other,b'audio'),(self.owner,b'different')):
            with self.assertRaises(AppError) as error:
                transcribe_direct(self.files,self.processor,owner,operation,data)
            self.assertEqual(error.exception.code,'SPEECH_OPERATION_CONFLICT')

    def test_failed_inference_can_retry_without_uploading(self):
        operation=str(uuid4())
        original=self.processor.transcribe
        self.processor.transcribe=lambda *args: (_ for _ in ()).throw(AppError('SPEECH_TIMEOUT','timeout',504))
        with self.assertRaises(AppError): transcribe_direct(self.files,self.processor,self.owner,operation,b'audio')
        self.processor.transcribe=original
        self.assertEqual(transcribe_direct(self.files,self.processor,self.owner,operation,b'audio')['language'],'ur')
        self.assertFalse(self.files.provider.objects)

    def test_size_rejection_precedes_inference(self):
        for data in (b'',b'x'*101):
            with self.assertRaises(AppError): transcribe_direct(self.files,self.processor,self.owner,str(uuid4()),data)
        self.assertEqual(self.calls,0)

    def test_http_multipart_limits_and_result_contract(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.speech import router
        from app.auth.dependencies import require_identity
        from app.core.exception_handlers import register_exception_handlers
        from app.files.upload_limit import FileUploadLimit
        app=FastAPI();register_exception_handlers(app)
        app.include_router(router,prefix='/api/v1')
        app.add_middleware(FileUploadLimit,maximum=100,speech_maximum=100)
        app.state.files_service=self.files;app.state.speech_service=self.processor
        app.dependency_overrides[require_identity]=lambda:SimpleNamespace(learner_id=self.owner)
        with TestClient(app) as client:
            operation=str(uuid4())
            for _ in range(2):
                response=client.post('/api/v1/speech/transcriptions/direct',files={'file':('recording',b'audio')},data={'operation_id':operation})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['text'],'ایک equation')
                self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(self.calls,1)
            self.assertEqual(client.post('/api/v1/speech/transcriptions/direct',files={'file':('recording',b'x'*70000)},data={'operation_id':str(uuid4())}).status_code,413)
