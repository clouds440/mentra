"""Opt-in real authenticated HTTP/worker/model check against a local public-audio manifest."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.speech import router
from app.core.config import Settings
from app.core.exception_handlers import register_exception_handlers
from app.speech.service import SpeechService
from app.speech.upload_limit import SpeechUploadLimit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--model-path', required=True)
    args = parser.parse_args()
    config = Settings(speech_model_path=args.model_path)
    service = SpeechService(config)
    app = FastAPI(); app.include_router(router, prefix='/api/v1'); register_exception_handlers(app)
    app.add_middleware(SpeechUploadLimit, maximum=config.speech_max_upload_bytes)
    class Auth:
        def authenticate(self, token):
            assert token == 'isolated-test'
            return SimpleNamespace(learner_id='isolated')
    app.state.auth_service = Auth(); app.state.speech_service = service
    try:
        with TestClient(app) as client:
            for sample in json.loads(args.manifest.read_text(encoding='utf-8')):
                data = (args.manifest.parent / sample['path']).read_bytes()
                result = client.post('/api/v1/speech/transcriptions', headers={'Authorization':'Bearer isolated-test'},
                                     files={'audio':('recording.wav', data, 'audio/wav')})
                assert result.status_code == 200, result.text
                assert result.headers['cache-control'] == 'no-store'
                body = result.json()
                assert body['text'].strip()
                if sample.get('language'):
                    assert body['language'] == sample['language'], (sample['path'], body['language'])
                print(json.dumps(dict(sample=sample['path'], language=body['language'],
                                      processing_seconds=body['processing_seconds']), ensure_ascii=True), flush=True)
    finally:
        service.close()


if __name__ == '__main__': main()
