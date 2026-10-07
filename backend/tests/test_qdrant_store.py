import sys
import types
import unittest
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import Settings
from app.rag.qdrant_store import (
    IncompatibleCollectionError,
    QdrantVectorStore,
    VectorStoreConfigurationError,
)


class FakeDistance(Enum):
    COSINE = "Cosine"
    EUCLID = "Euclid"


class FakeVectorParams:
    def __init__(self, size: int, distance: FakeDistance) -> None:
        self.size = size
        self.distance = distance


class FakePointStruct:
    def __init__(
        self,
        id: str,
        vector: list[float],
        payload: dict[str, object],
    ) -> None:
        self.id = id
        self.vector = vector
        self.payload = payload


class FakeQdrantClient:
    def __init__(
        self,
        *,
        exists: bool = False,
        dimension: int = 3,
        distance: FakeDistance = FakeDistance.COSINE,
        identity: dict[str, object] | None = None,
    ) -> None:
        self.exists = exists
        self.dimension = dimension
        self.distance = distance
        self.identity = identity
        self.created_config: FakeVectorParams | None = None
        self.closed = False

    def collection_exists(self, _collection_name: str) -> bool:
        return self.exists

    def create_collection(
        self, *, collection_name: str, vectors_config: FakeVectorParams
    ) -> None:
        self.exists = True
        self.dimension = vectors_config.size
        self.distance = vectors_config.distance
        self.created_config = vectors_config

    def get_collection(self, _collection_name: str) -> SimpleNamespace:
        vectors = FakeVectorParams(self.dimension, self.distance)
        return SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(vectors=vectors))
        )

    def upsert(self, *, collection_name: str, points: list[FakePointStruct], wait: bool) -> None:
        self.identity = points[0].payload["_mentra_index_metadata"]

    def retrieve(
        self,
        *,
        collection_name: str,
        ids: list[str],
        with_payload: bool,
        with_vectors: bool,
    ) -> list[SimpleNamespace]:
        if self.identity is None:
            return []
        return [SimpleNamespace(payload={"_mentra_index_metadata": self.identity})]

    def close(self) -> None:
        self.closed = True


class FakeEmbeddingService:
    dimension = 3
    model_name = "BAAI/bge-small-en-v1.5"
    model_version = "resolved-revision"


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "qdrant_url": "https://qdrant.example",
        "qdrant_api_key": "test-key",
        "qdrant_collection": "mentra-index",
        "qdrant_distance": "Cosine",
    }
    values.update(overrides)
    return Settings(**values)


class QdrantStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        models = types.SimpleNamespace(
            Distance=FakeDistance,
            VectorParams=FakeVectorParams,
            PointStruct=FakePointStruct,
        )
        qdrant_module = types.ModuleType("qdrant_client")
        qdrant_module.models = models
        self.module_patcher = patch.dict(
            sys.modules,
            {
                "qdrant_client": qdrant_module,
                "qdrant_client.models": models,
            },
        )
        self.module_patcher.start()

    def tearDown(self) -> None:
        self.module_patcher.stop()

    def test_missing_collection_is_created_using_embedding_dimension(self) -> None:
        client = FakeQdrantClient()
        store = QdrantVectorStore(settings(), FakeEmbeddingService(), client)

        store.ensure_collection()

        self.assertIsNotNone(client.created_config)
        assert client.created_config is not None
        self.assertEqual(client.created_config.size, FakeEmbeddingService.dimension)
        self.assertEqual(client.created_config.distance, FakeDistance.COSINE)
        self.assertEqual(
            client.identity,
            {
                "model_name": FakeEmbeddingService.model_name,
                "model_version": FakeEmbeddingService.model_version,
                "dimension": FakeEmbeddingService.dimension,
            },
        )

    def test_existing_collection_must_have_matching_dimension(self) -> None:
        client = FakeQdrantClient(
            exists=True,
            dimension=12,
            identity={
                "model_name": FakeEmbeddingService.model_name,
                "model_version": FakeEmbeddingService.model_version,
                "dimension": 12,
            },
        )
        store = QdrantVectorStore(settings(), FakeEmbeddingService(), client)

        with self.assertRaisesRegex(IncompatibleCollectionError, "vector dimension"):
            store.ensure_collection()

    def test_existing_collection_must_have_matching_embedding_identity(self) -> None:
        client = FakeQdrantClient(
            exists=True,
            identity={
                "model_name": "different-model",
                "model_version": "different-revision",
                "dimension": FakeEmbeddingService.dimension,
            },
        )
        store = QdrantVectorStore(settings(), FakeEmbeddingService(), client)

        with self.assertRaisesRegex(IncompatibleCollectionError, "different-model"):
            store.ensure_collection()

    def test_existing_collection_must_have_matching_distance(self) -> None:
        client = FakeQdrantClient(
            exists=True,
            distance=FakeDistance.EUCLID,
            identity={
                "model_name": FakeEmbeddingService.model_name,
                "model_version": FakeEmbeddingService.model_version,
                "dimension": FakeEmbeddingService.dimension,
            },
        )
        store = QdrantVectorStore(settings(), FakeEmbeddingService(), client)

        with self.assertRaisesRegex(IncompatibleCollectionError, "distance"):
            store.ensure_collection()

    def test_existing_untracked_collection_fails_without_recreation(self) -> None:
        client = FakeQdrantClient(exists=True)
        store = QdrantVectorStore(settings(), FakeEmbeddingService(), client)

        with self.assertRaisesRegex(IncompatibleCollectionError, "no Mentra"):
            store.ensure_collection()
        self.assertIsNone(client.created_config)

    def test_missing_qdrant_configuration_is_reported(self) -> None:
        client = FakeQdrantClient()
        store = QdrantVectorStore(
            settings(qdrant_url="", qdrant_api_key="", qdrant_collection=""),
            FakeEmbeddingService(),
            client,
        )

        with self.assertRaisesRegex(
            VectorStoreConfigurationError,
            "QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION",
        ):
            store.ensure_collection()


if __name__ == "__main__":
    unittest.main()
