import unittest

from langchain_openai import ChatOpenAI
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.langchain.model_factory import ModelFactory
from app.rag.qdrant_store import (
    METADATA_PAYLOAD_KEY,
    IncompatibleCollectionError,
    QdrantVectorStore,
)


class FakeEmbeddingService:
    dimension = 3
    model_name = "BAAI/bge-small-en-v1.5"
    model_version = "test-model-revision"


class RealAdapterTests(unittest.TestCase):
    def test_real_chat_model_constructs_without_making_a_request(self) -> None:
        app_settings = Settings(
            ai_model="chat-test-model",
            ai_base_url="https://compatible.example/v1",
            ai_api_key="not-a-real-key",
            ai_temperature=0.6,
            ai_timeout=17,
            ai_max_retries=5,
        )

        model = ModelFactory(app_settings).get_model()

        self.assertIsInstance(model, ChatOpenAI)
        self.assertEqual(model.model_name, "chat-test-model")
        self.assertEqual(
            str(model.openai_api_base), "https://compatible.example/v1"
        )
        self.assertEqual(model.openai_api_key.get_secret_value(), "not-a-real-key")
        self.assertEqual(model.temperature, 0.6)
        self.assertEqual(model.request_timeout, 17)
        self.assertEqual(model.max_retries, 5)

    def test_real_qdrant_client_creates_and_persists_collection_identity(self) -> None:
        client = QdrantClient(":memory:")
        app_settings = Settings(
            qdrant_url="http://localhost:6333",
            qdrant_api_key="in-memory-test-key",
            qdrant_collection="mentra-test-index",
            qdrant_distance="Cosine",
        )
        store = QdrantVectorStore(app_settings, FakeEmbeddingService(), client)
        try:
            store.ensure_collection()

            collection = client.get_collection("mentra-test-index")
            self.assertEqual(
                collection.config.params.vectors.size,
                FakeEmbeddingService.dimension,
            )
            self.assertEqual(
                collection.config.params.vectors.distance.value, "Cosine"
            )
            marker = client.retrieve(
                collection_name="mentra-test-index",
                ids=[store._metadata_point_id()],
                with_payload=True,
                with_vectors=False,
            )[0]
            self.assertEqual(
                marker.payload[METADATA_PAYLOAD_KEY],
                {
                    "model_name": FakeEmbeddingService.model_name,
                    "model_version": FakeEmbeddingService.model_version,
                    "dimension": FakeEmbeddingService.dimension,
                },
            )
            store.validate_collection()
        finally:
            client.close()

    def test_real_qdrant_client_rejects_a_different_model_revision(self) -> None:
        client = QdrantClient(":memory:")
        app_settings = Settings(
            qdrant_url="http://localhost:6333",
            qdrant_api_key="in-memory-test-key",
            qdrant_collection="mentra-revision-test-index",
        )
        store = QdrantVectorStore(app_settings, FakeEmbeddingService(), client)
        try:
            store.ensure_collection()
            mismatched_embedding = FakeEmbeddingService()
            mismatched_embedding.model_version = "different-revision"
            mismatched_store = QdrantVectorStore(
                app_settings, mismatched_embedding, client
            )

            with self.assertRaisesRegex(
                IncompatibleCollectionError, "different-revision"
            ):
                mismatched_store.validate_collection()
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
