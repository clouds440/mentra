import logging
import uuid
from typing import Any
from urllib.parse import urlsplit
from threading import Lock

from app.core.config import Settings
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import VectorStore, VectorStoreError, VectorChunk, VectorMatch

logger = logging.getLogger("mentra")
METADATA_PAYLOAD_KEY = "_mentra_index_metadata"


def legacy_scope_filter(learner_id, context_ids):
    from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue
    return Filter(must=[
        FieldCondition(key='learner_id', match=MatchValue(value=learner_id)),
        FieldCondition(key='learning_context_id', match=MatchAny(any=context_ids)),
        FieldCondition(key='status', match=MatchValue(value='ACTIVE')),
    ])


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
        self._index_lock = Lock()
        self._indexes_initialized = False

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
                self._indexes_initialized = False
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

    def _chunk_filter(self, learner_id, *, generation_ids=None, document_id=None):
        m = self._get_models()
        conditions = [m.FieldCondition(key='record_type', match=m.MatchValue(value='chunk')),
                      m.FieldCondition(key='learner_id', match=m.MatchValue(value=learner_id))]
        if generation_ids is not None:
            conditions.append(m.FieldCondition(key='generation_id', match=m.MatchAny(any=generation_ids)))
        if document_id is not None:
            conditions.append(m.FieldCondition(key='document_id', match=m.MatchValue(value=document_id)))
        return m.Filter(must=conditions)

    def initialize_chunk_indexes(self):
        # Identity checks stay live for every ingestion; only redundant index
        # creation is cached. An externally replaced collection must fail closed.
        self.ensure_collection()
        with self._index_lock:
            if self._indexes_initialized:
                return
            m = self._get_models()
            try:
                for field in ('record_type', 'learner_id', 'document_id', 'generation_id', 'context_ids'):
                    self._get_client().create_payload_index(self.collection_name, field, m.PayloadSchemaType.KEYWORD, wait=True)
            except Exception as exc:
                raise VectorStoreError('Could not initialize material filter indexes.') from exc
            self._indexes_initialized = True

    def upsert_chunks(self, chunks: list[VectorChunk]) -> None:
        if not chunks:
            return
        m = self._get_models()
        try:
            self._get_client().upsert(self.collection_name, points=[m.PointStruct(id=c.id, vector=c.vector,
                payload=dict(record_type='chunk', learner_id=c.learner_id, document_id=c.document_id,
                             generation_id=c.generation_id, context_ids=c.context_ids)) for c in chunks], wait=True)
        except Exception as exc:
            raise VectorStoreError('Could not index material.') from exc

    def query_chunks(self, learner_id: str, generation_ids: list[str], vector: list[float], limit: int) -> list[VectorMatch]:
        if not generation_ids:
            return []
        try:
            self.validate_collection()
            result = self._get_client().query_points(self.collection_name, query=vector,
                query_filter=self._chunk_filter(learner_id, generation_ids=generation_ids),
                limit=limit, with_payload=False, with_vectors=False)
            return [VectorMatch(str(p.id), float(p.score)) for p in result.points]
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError('Could not retrieve material.') from exc

    def delete_chunks(self, learner_id: str, document_id: str, generation_id: str | None = None) -> None:
        try:
            self._get_client().delete(self.collection_name, points_selector=self._get_models().FilterSelector(
                filter=self._chunk_filter(learner_id, document_id=document_id,
                    generation_ids=[generation_id] if generation_id else None)), wait=True)
        except Exception as exc:
            raise VectorStoreError('Could not clean material index.') from exc

    def count_chunks(self, learner_id: str, generation_id: str) -> int:
        try:
            return self._get_client().count(self.collection_name,
                count_filter=self._chunk_filter(learner_id, generation_ids=[generation_id]), exact=True).count
        except Exception as exc:
            raise VectorStoreError('Could not verify material index.') from exc

    def indexed_chunk_ids(self, learner_id: str, generation_id: str, ids: list[str]) -> set[str]:
        found = set()
        try:
            for start in range(0, len(ids), 500):
                points = self._get_client().retrieve(self.collection_name, ids=ids[start:start + 500],
                    with_payload=True, with_vectors=False)
                for point in points:
                    payload = point.payload or {}
                    if payload.get('record_type') == 'chunk' and payload.get('learner_id') == learner_id and payload.get('generation_id') == generation_id:
                        found.add(str(point.id))
            return found
        except Exception as exc:
            raise VectorStoreError('Could not verify material point identities.') from exc

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
