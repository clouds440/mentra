from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass(frozen=True)
class VectorChunk:
    id: str
    learner_id: str
    document_id: str
    generation_id: str
    context_ids: list[str]
    vector: list[float]


@dataclass(frozen=True)
class VectorMatch:
    id: str
    score: float


class VectorStoreError(RuntimeError):
    """Raised when a vector store is unavailable or incompatible."""


@runtime_checkable
class VectorStore(Protocol):
    @property
    def collection_name(self) -> str: ...

    def ensure_collection(self) -> None: ...

    def validate_collection(self) -> None: ...

    def initialize_chunk_indexes(self) -> None: ...

    def close(self) -> None: ...

    def upsert_chunks(self, chunks: list[VectorChunk]) -> None: ...

    def query_chunks(self, learner_id: str, generation_ids: list[str], vector: list[float], limit: int) -> list[VectorMatch]: ...

    def delete_chunks(self, learner_id: str, document_id: str, generation_id: str | None = None) -> None: ...

    def count_chunks(self, learner_id: str, generation_id: str) -> int: ...

    def indexed_chunk_ids(self, learner_id: str, generation_id: str, ids: list[str]) -> set[str]: ...
