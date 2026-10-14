import json
import unittest
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.core.http_limits import JsonBodyLimit
from app.assessments.schemas import SubmitAnswers


class HttpLimitTests(unittest.TestCase):
    def test_private_policy_preserves_other_headers_and_covers_errors(self):
        from app.core.http_privacy import PrivateApiResponses
        from app.core.exception_handlers import register_exception_handlers
        from starlette.responses import Response
        app = FastAPI()
        register_exception_handlers(app)
        app.add_middleware(PrivateApiResponses)
        @app.get('/api/v1/source')
        def source():
            return Response('source', headers={'Content-Disposition': 'attachment', 'X-Request-ID': 'trace'})
        @app.get('/api/v1/health')
        def health():
            return {'ok': True}
        client = TestClient(app)
        response = client.get('/api/v1/source')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['content-disposition'], 'attachment')
        self.assertEqual(response.headers['x-request-id'], 'trace')
        self.assertEqual(client.get('/api/v1/missing').headers['cache-control'], 'no-store')
        self.assertNotIn('cache-control', client.get('/api/v1/health').headers)

    def test_answer_items_are_bounded_and_maximum_unicode_answers_fit_transport(self):
        answers = {str(uuid4()): '\U0001f600' * 8000 for _ in range(10)}
        body = dict(expected_revision=1, client_request_id=str(uuid4()), answers=answers)
        SubmitAnswers.model_validate(body)
        self.assertLess(len(json.dumps(body).encode()), 1024 * 1024)
        with self.assertRaises(ValidationError):
            SubmitAnswers.model_validate(dict(body, answers={str(i): 'x' for i in range(11)}))
        with self.assertRaises(ValidationError):
            SubmitAnswers.model_validate(dict(body, answers={'q': 'x' * 8001}))

    def test_declared_and_chunked_oversized_json_are_rejected_before_parsing(self):
        app = FastAPI()
        app.add_middleware(JsonBodyLimit)
        @app.post('/api/v1/assessments/attempts/id/submission')
        async def echo(request: Request):
            return await request.json()
        client = TestClient(app)
        path = '/api/v1/assessments/attempts/id/submission'
        for data in [b'x' * (1024 * 1024 + 1), iter([b'x' * 600000, b'x' * 600000])]:
            response = client.post(path, content=data, headers={'content-type': 'application/json'})
            self.assertEqual(response.status_code, 413)
        self.assertEqual(client.post(path, json={'ok': True}).status_code, 200)
