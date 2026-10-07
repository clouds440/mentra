from typing import Protocol, runtime_checkable


class VectorStoreError(RuntimeError):
    """Raised when a vector store is unavailable or incompatible."""


@runtime_checkable
class VectorStore(Protocol):
    @property
    def collection_name(self) -> str: ...

    def ensure_collection(self) -> None: ...

    def validate_collection(self) -> None: ...

    def close(self) -> None: ...
