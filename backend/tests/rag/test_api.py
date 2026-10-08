import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.rag import router
from app.core.exception_handlers import register_exception_handlers
from app.rag.upload_limit import MaterialUploadLimit
from app.student_profile.dependencies import require_onboarded_identity


class APIBoundaryTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.state.rag_service = object()
        register_exception_handlers(app)
        app.add_middleware(MaterialUploadLimit, maximum=1024)
        app.include_router(router, prefix='/api/v1')
        app.dependency_overrides[require_onboarded_identity] = lambda: None
        self.client = TestClient(app)

    def test_client_selected_learner_identity_is_rejected(self):
        response = self.client.post('/api/v1/rag/search', json={'query':'notes', 'learner_id':'someone-else'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('error', response.json())

    def test_multipart_transport_is_bounded_before_spooling(self):
        response = self.client.post('/api/v1/documents', content=b'x' * (70 * 1024), headers={'Content-Type':'multipart/form-data; boundary=test'})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()['error']['code'], 'RAG_FILE_TOO_LARGE')

    def test_chunked_upload_without_content_length_is_also_bounded(self):
        def content():
            yield b'--test\r\nContent-Disposition: form-data; name="file"; filename="big.txt"\r\n\r\n'
            yield b'x' * (70 * 1024)
            yield b'\r\n--test--\r\n'
        response = self.client.post('/api/v1/documents', content=content(), headers={'Content-Type':'multipart/form-data; boundary=test'})
        self.assertEqual(response.status_code, 413)
