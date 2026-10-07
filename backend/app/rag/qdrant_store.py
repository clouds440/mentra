import logging
import uuid
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import VectorStore, VectorStoreError

logger = logging.getLogger("mentra")
METADATA_PAYLOAD_KEY = "_mentra_index_metadata"


class VectorStoreConfigurationError(VectorStoreError):
    """Raised when Qdrant settings are incomplete or invalid."""


class IncompatibleCollectionError(VectorStoreError):
    """Raised when an existing collection cannot safely store active embeddings."""


class QdrantVectorStore(VectorStore):
    def __init__(
        self,
        app_settings: Settings,
        embedding_service: EmbeddingService,
        client: Any | None = None,
    ) -> None:
        self._settings = app_settings
        self._embedding_service = embedding_service
        self._client = client

    @property
    def collection_name(self) -> str:
        return self._settings.qdrant_collection

    def ensure_collection(self) -> None:
        client = self._get_client()
        models = self._get_models()
        distance = self._distance(models)
        try:
            if not client.collection_exists(self.collection_name):
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self._embedding_service.dimension,
                        distance=distance,
                    ),
                )
                self._write_index_identity(client, models)
            self._validate_collection(client)
        except VectorStoreError:
            raise
        except Exception as exc:
            logger.exception(
                "Could not initialize Qdrant collection %r.",
                self.collection_name,
            )
            raise VectorStoreError(
                f"Could not initialize Qdrant collection "
                f"{self.collection_name!r}: {exc}"
            ) from exc

    def validate_collection(self) -> None:
        client = self._get_client()
        try:
            self._validate_collection(client)
        except VectorStoreError:
            raise
        except Exception as exc:
            logger.exception(
                "Could not validate Qdrant collection %r.",
                self.collection_name,
            )
            raise VectorStoreError(
                f"Could not validate Qdrant collection "
                f"{self.collection_name!r}: {exc}"
            ) from exc

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _get_client(self) -> Any:
        missing = [
            name
            for name, value in (
                ("QDRANT_URL", self._settings.qdrant_url),
                ("QDRANT_API_KEY", self._settings.qdrant_api_key),
                ("QDRANT_COLLECTION", self._settings.qdrant_collection),
            )
            if not value.strip()
        ]
        if missing:
            raise VectorStoreConfigurationError(
                f"Missing required Qdrant configuration: {', '.join(missing)}."
            )
        qdrant_url = urlsplit(self._settings.qdrant_url)
        if qdrant_url.scheme not in {"http", "https"} or not qdrant_url.netloc:
            raise VectorStoreConfigurationError(
                "QDRANT_URL must be an absolute HTTP or HTTPS URL."
            )
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise VectorStoreConfigurationError(
                    "The qdrant-client package is required for the vector store."
                ) from exc
            self._client = QdrantClient(
                url=self._settings.qdrant_url,
                api_key=self._settings.qdrant_api_key,
            )
        return self._client

    @staticmethod
    def _get_models() -> Any:
        try:
            from qdrant_client import models
        except ImportError as exc:
            raise VectorStoreConfigurationError(
                "The qdrant-client package is required for the vector store."
            ) from exc
        return models

    def _distance(self, models: Any) -> Any:
        value = self._settings.qdrant_distance.strip().upper()
        distance = getattr(models.Distance, value, None)
        if distance is None:
            supported = ", ".join(
                item.name.title() for item in models.Distance
            )
            raise VectorStoreConfigurationError(
                f"Unsupported QDRANT_DISTANCE {self._settings.qdrant_distance!r}; "
                f"supported values: {supported}."
            )
        return distance

    def _validate_collection(self, client: Any) -> None:
        try:
            collection = client.get_collection(self.collection_name)
        except Exception as exc:
            logger.exception(
                "Could not reach Qdrant collection %r.",
                self.collection_name,
            )
            raise VectorStoreError(
                f"Could not reach Qdrant collection {self.collection_name!r}: {exc}"
            ) from exc

        models = self._get_models()
        distance = self._distance(models)
        vectors = collection.config.params.vectors
        if isinstance(vectors, dict):
            raise IncompatibleCollectionError(
                f"Qdrant collection {self.collection_name!r} uses named vectors; "
                "Mentra expects one unnamed vector."
            )

        actual_dimension = getattr(vectors, "size", None)
        actual_distance = getattr(vectors, "distance", None)
        if actual_dimension != self._embedding_service.dimension:
            raise IncompatibleCollectionError(
                f"Qdrant collection {self.collection_name!r} has vector dimension "
                f"{actual_dimension!r}, but the active embedding model "
                f"{self._embedding_service.model_name!r} has dimension "
                f"{self._embedding_service.dimension}. Reindex or migrate the "
                "collection; it will not be recreated automatically."
            )
        if self._distance_name(actual_distance) != self._distance_name(distance):
            raise IncompatibleCollectionError(
                f"Qdrant collection {self.collection_name!r} uses distance "
                f"{self._distance_name(actual_distance)!r}, but Mentra is configured "
                f"for {self._distance_name(distance)!r}."
            )

        records = client.retrieve(
            collection_name=self.collection_name,
            ids=[self._metadata_point_id()],
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            raise IncompatibleCollectionError(
                f"Qdrant collection {self.collection_name!r} has no Mentra "
                "embedding identity marker. Reindex or explicitly migrate it "
                "before use."
            )
        payload = records[0].payload or {}
        expected = self._index_identity()
        actual = payload.get(METADATA_PAYLOAD_KEY)
        if actual != expected:
            raise IncompatibleCollectionError(
                f"Qdrant collection {self.collection_name!r} was indexed with "
                f"{actual!r}, but the active embedding identity is {expected!r}. "
                "Reindex or migrate the collection; vectors from different "
                "embedding models or versions must not be mixed."
            )

    def _write_index_identity(self, client: Any, models: Any) -> None:
        vector = [0.0] * self._embedding_service.dimension
        vector[0] = 1.0
        client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=self._metadata_point_id(),
                    vector=vector,
                    payload={METADATA_PAYLOAD_KEY: self._index_identity()},
                )
            ],
            wait=True,
        )

    def _index_identity(self) -> dict[str, Any]:
        return {
            "model_name": self._embedding_service.model_name,
            "model_version": self._embedding_service.model_version,
            "dimension": self._embedding_service.dimension,
        }

    def _metadata_point_id(self) -> str:
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"mentra:{self.collection_name}:embedding-identity",
            )
        )

    @staticmethod
    def _distance_name(distance: Any) -> str:
        return str(getattr(distance, "value", distance)).upper()
