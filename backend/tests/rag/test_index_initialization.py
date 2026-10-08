import unittest
from unittest.mock import Mock
from app.core.config import Settings
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.vector_store import VectorStoreError


class IndexInitializationTests(unittest.TestCase):
    def store(self):
        client = Mock()
        store = QdrantVectorStore(Settings(), Mock(), client)
        store._get_client = Mock(return_value=client)
        store.ensure_collection = Mock()
        return store, client

    def test_indexes_are_created_once_but_identity_checks_are_not_cached(self):
        store, client = self.store()
        store.initialize_chunk_indexes()
        store.initialize_chunk_indexes()
        self.assertEqual(client.create_payload_index.call_count, 5)
        self.assertEqual(store.ensure_collection.call_count, 2)
        store.ensure_collection.side_effect = VectorStoreError('identity changed')
        with self.assertRaises(VectorStoreError):
            store.initialize_chunk_indexes()

    def test_failed_index_initialization_is_retryable(self):
        store, client = self.store()
        client.create_payload_index.side_effect = RuntimeError('temporary failure')
        with self.assertRaises(VectorStoreError):
            store.initialize_chunk_indexes()
        client.create_payload_index.side_effect = None
        store.initialize_chunk_indexes()
        self.assertEqual(client.create_payload_index.call_count, 6)
