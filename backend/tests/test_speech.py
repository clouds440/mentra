import io
import threading
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.speech import router
from app.auth.errors import AuthenticationError
from app.core.config import Settings
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AppError
from app.speech.engine import decode_audio, FasterWhisperEngine
from app.speech.service import SpeechService
from app.files.upload_limit import FileUploadLimit


def echo_worker(connection, config):
    while True:
        message = connection.recv()
        if message is None: break
        data, language = message
        if data == b'slow':
            time.sleep(3)
        connection.send(('ok', dict(text='مجھے equation سمجھائیں', language=language or 'ur',
                                   language_probability=0.8, duration_seconds=5, processing_seconds=0.1)))


def wav(seconds=0.3):
    target = io.BytesIO()
    with wave.open(target, 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
        output.writeframes(b'\0\0' * int(seconds * 16000))
    return target.getvalue()


class SpeechTests(unittest.TestCase):
    def test_real_decoder_bounds_and_invalid_content(self):
        self.assertAlmostEqual(len(decode_audio(wav(), 30)) / 16000, 0.3)
        self.assertEqual(len(decode_audio(wav(30.1), 30)), 30 * 16000)
        for data, code in [(b'invalid', 'SPEECH_AUDIO_INVALID'), (wav(0.05), 'SPEECH_AUDIO_EMPTY'),
                           (wav(31), 'SPEECH_DURATION')]:
            with self.assertRaises(AppError) as error:
                decode_audio(data, 30)
            self.assertEqual(error.exception.code, code)

    def test_real_browser_container_decoding(self):
        import av
        import numpy as np
        for format, codec, rate in [('webm', 'libopus', 48000), ('ogg', 'libopus', 48000), ('mp4', 'aac', 16000)]:
            target = io.BytesIO()
            with av.open(target, 'w', format=format) as output:
                stream = output.add_stream(codec, rate=rate); stream.layout = 'mono'
                frame = av.AudioFrame.from_ndarray(np.zeros((1, int(rate * 0.3)), dtype=np.int16), format='s16', layout='mono')
                frame.sample_rate = rate
                for packet in stream.encode(frame): output.mux(packet)
                for packet in stream.encode(None): output.mux(packet)
            decoded = decode_audio(target.getvalue(), 30)
            self.assertGreater(len(decoded), 1600)
            self.assertLess(len(decoded), 16000)

    def test_engine_preserves_scripts_and_uses_transcription(self):
        for text, language in [('Explain Newton’s second law.', 'en'), ('مجھے equation سمجھائیں۔', 'ur'),
                               ('اشرح هذه المعادلة', 'ar')]:
            model = SimpleNamespace(transcribe=lambda *a, **kw: ([SimpleNamespace(text=text)],
                                     SimpleNamespace(language=language, language_probability=0.9)))
            engine = FasterWhisperEngine(dict(max_seconds=30, beam_size=3))
            engine.model = model
            with patch('app.speech.engine.speech_regions', return_value=[(0,4800)]), patch.object(model, 'transcribe', wraps=model.transcribe) as call:
                result = engine.transcribe(wav(), language)
            self.assertEqual(result['text'], text)
            self.assertEqual(call.call_args.kwargs['task'], 'transcribe')
            self.assertEqual(call.call_args.kwargs['language'], language)

    def test_silence_does_not_load_model(self):
        engine = FasterWhisperEngine(dict(max_seconds=30))
        with self.assertRaises(AppError) as error: engine.transcribe(wav(), None)
        self.assertEqual(error.exception.code, 'SPEECH_NO_SPEECH')
        self.assertIsNone(engine.model)

    def test_paused_languages_are_preserved_in_order(self):
        results = iter([([SimpleNamespace(text='مجھے سمجھائیں۔')], SimpleNamespace(language='ur',language_probability=0.9)),
                        ([SimpleNamespace(text='Newton’s second law.')], SimpleNamespace(language='en',language_probability=0.99))])
        engine = FasterWhisperEngine(dict(max_seconds=30, beam_size=3))
        engine.model = SimpleNamespace(transcribe=lambda *a, **kw: next(results))
        with patch('app.speech.engine.speech_regions', return_value=[(0,2400),(2400,4800)]):
            result = engine.transcribe(wav(), None)
        self.assertEqual(result['text'], 'مجھے سمجھائیں۔ Newton’s second law.')

    def test_worker_reuse_busy_timeout_and_recovery(self):
        service = SpeechService(Settings(speech_timeout_seconds=10), worker_target=echo_worker)
        try:
            service.transcribe(b'first', None)
            pid = service._process.pid
            service.transcribe(b'second', 'ar')
            self.assertEqual(pid, service._process.pid)
            errors = []
            def slow():
                try: service.transcribe(b'slow', None)
                except AppError as error: errors.append(error.code)
            service.timeout = 0.3
            thread = threading.Thread(target=slow); thread.start()
            time.sleep(0.05)
            with self.assertRaises(AppError) as busy: service.transcribe(b'other', None)
            self.assertEqual(busy.exception.code, 'SPEECH_BUSY')
            thread.join(4)
            self.assertEqual(errors, ['SPEECH_TIMEOUT'])
            service.timeout = 10
            service.transcribe(b'recovery', None)
            self.assertNotEqual(pid, service._process.pid)
        finally: service.close()

    def test_auto_detection_preserves_every_detected_language(self):
        for language, text in [('hi', 'मुझे समझाइए'), ('es', 'Explícame esto'), ('ja', '説明してください'), ('fr', 'Expliquez ceci')]:
            with self.subTest(language=language):
                transcribe = Mock(return_value=([SimpleNamespace(text=text)], SimpleNamespace(language=language, language_probability=0.98)))
                engine = FasterWhisperEngine(dict(max_seconds=30, beam_size=3))
                engine.model = SimpleNamespace(transcribe=transcribe)
                with patch('app.speech.engine.speech_regions', return_value=[(0,4800)]):
                    result = engine.transcribe(wav(), None)
                self.assertEqual(result['text'], text)
                self.assertEqual(result['language'], language)
                self.assertEqual(result['language_probability'], 0.98)
                transcribe.assert_called_once()
                self.assertIsNone(transcribe.call_args.kwargs['language'])

    def test_http_auth_origin_and_json_file_reference(self):
        app=FastAPI();register_exception_handlers(app)
        app.include_router(router,prefix='/api/v1')
        class Auth:
            def authenticate(self,token):
                if token!='valid':raise AuthenticationError()
                return SimpleNamespace(learner_id='student-1')
        app.state.auth_service=Auth()
        app.state.files_service=object();app.state.speech_service=object()
        result=dict(text='Explain this equation',language='ur',language_probability=0.9,duration_seconds=0.3,processing_seconds=0.1)
        from uuid import uuid4
        body={'file_id':str(uuid4())}
        with TestClient(app) as client,patch('app.api.routes.speech.transcribe_file',return_value=result) as call:
            url='/api/v1/speech/transcriptions';headers={'Authorization':'Bearer valid'}
            self.assertEqual(client.post(url,json=body).status_code,401)
            response=client.post(url,json=body,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['language'],'ur')
            self.assertEqual(call.call_args.args[-1],body['file_id'])
            self.assertEqual(client.post(url,json={**body,'language':'ar'},headers=headers).status_code,422)
            client.cookies.set('mentra_session','valid')
            self.assertEqual(client.post(url,json=body,headers={'Origin':'https://attacker.example'}).status_code,403)

    def test_chunked_transport_size_limit(self):
        import asyncio
        sent = []
        async def app(scope, receive, send):
            while (await receive()).get('more_body'): pass
            await send({'type':'http.response.start', 'status':200, 'headers':[]})
        messages = iter([{'type':'http.request', 'body':b'x' * 40000, 'more_body':True},
                         {'type':'http.request', 'body':b'x' * 40000, 'more_body':False}])
        async def receive(): return next(messages)
        async def send(message): sent.append(message)
        asyncio.run(FileUploadLimit(app, 1024)({'type':'http', 'method':'POST', 'path':'/api/v1/files/uploads', 'headers':[]}, receive, send))
        self.assertEqual(sent[0]['status'], 413)
