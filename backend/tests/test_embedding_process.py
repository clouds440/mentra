import unittest
from app.core.config import Settings
from app.rag.embedding_process import ProcessEmbeddingService
from app.rag.embeddings import EmbeddingModelError


def fake_worker(connection, config):
    import time
    connection.send(('ok', dict(model_name=config['model'], model_version='v1', dimension=3, max_tokens=512)))
    try:
        while True:
            message = connection.recv()
            if message is None:
                break
            operation, argument = message
            if argument == 'hang':
                time.sleep(60)
            value = [[1., 0., 0.] for _ in argument] if operation in ('embed_documents', 'embed_similarity') else [1., 0., 0.] if operation == 'embed_query' else len(argument)
            connection.send(('ok', value))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


class EmbeddingProcessTests(unittest.TestCase):
    def test_native_timeout_is_killed_and_worker_restarts_with_same_identity(self):
        settings = Settings(_env_file=None, embedding_worker_timeout=.05)
        service = ProcessEmbeddingService(settings, worker_target=fake_worker)
        self.addCleanup(service.close)
        self.assertEqual(service.embed_query('query'), [1., 0., 0.])
        with self.assertRaises(EmbeddingModelError):
            service.embed_query('hang')
        self.assertIsNone(service._process)
        self.assertEqual(service.embed_query('query'), [1., 0., 0.])
        self.assertEqual(len(service.embed_documents(['note'] * 70)), 70)
        self.assertEqual(len(service.embed_similarity(['note'] * 70)), 70)
        self.assertEqual(service.embed_similarity([]), [])
        self.assertEqual(service.dimension, 3)
        service.close()
        with self.assertRaises(EmbeddingModelError):
            service.embed_query('query')
