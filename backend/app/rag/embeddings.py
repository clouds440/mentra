import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.core.config import Settings, settings

EMBEDDING_CACHE_DIR = Path("/opt/mentra/models/embedding")
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
DOCUMENT_BATCH_SIZE = 32


class EmbeddingModelError(RuntimeError):
    """Raised when the local embedding model is unavailable or invalid."""


@runtime_checkable
class EmbeddingService(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def model_name(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    @property
    def max_tokens(self) -> int: ...

    def token_count(self, text: str) -> int: ...

    def query_token_count(self, text: str) -> int: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class SentenceTransformerEmbeddingService:
    def __init__(
        self,
        app_settings: Settings = settings,
        model_path: Path = EMBEDDING_CACHE_DIR,
        model_loader: Callable[..., Any] | None = None,
        batch_size: int = DOCUMENT_BATCH_SIZE,
    ) -> None:
        metadata_path = model_path / "model-metadata.json"
        if not metadata_path.is_file():
            raise EmbeddingModelError(
                f"Baked embedding model metadata was not found at {metadata_path}. "
                "Rebuild the backend image with the configured EMBEDDING_MODEL."
            )

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EmbeddingModelError(
                f"Could not read embedding model metadata at {metadata_path}."
            ) from exc

        baked_model = metadata.get("model_name")
        model_version = metadata.get("model_version")
        if baked_model != app_settings.embedding_model:
            raise EmbeddingModelError(
                "The baked embedding model does not match EMBEDDING_MODEL "
                f"({baked_model!r} != {app_settings.embedding_model!r}). "
                "Rebuild the backend image and reindex the Qdrant collection."
            )
        if not isinstance(model_version, str) or not model_version:
            raise EmbeddingModelError(
                f"Embedding model metadata at {metadata_path} has no version."
            )
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        if model_loader is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingModelError(
                    "The sentence-transformers package is required for local embeddings."
                ) from exc
            model_loader = SentenceTransformer

        try:
            self._model = model_loader(
                str(model_path),
                device=app_settings.embedding_device,
                local_files_only=True,
            )
            dimension = self._model.get_sentence_embedding_dimension()
        except (OSError, ValueError, RuntimeError) as exc:
            raise EmbeddingModelError(
                f"Could not load local embedding model {baked_model!r} "
                f"from {model_path}."
            ) from exc
        if not isinstance(dimension, int) or dimension <= 0:
            raise EmbeddingModelError(
                f"Embedding model {baked_model!r} reported invalid dimension "
                f"{dimension!r}."
            )

        self._dimension = dimension
        self._model_name = baked_model
        self._model_version = model_version
        self._batch_size = batch_size

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"{QUERY_INSTRUCTION}{text}"])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(texts)

    @property
    def max_tokens(self) -> int:
        return int(self._model.max_seq_length)

    def token_count(self, text: str) -> int:
        return len(self._model.tokenizer.encode(text, add_special_tokens=True, truncation=False))

    def query_token_count(self, text: str) -> int:
        return self.token_count(QUERY_INSTRUCTION + text)

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        if hasattr(self._model, 'tokenizer') and any(self.token_count(text) > self.max_tokens for text in texts):
            raise EmbeddingModelError('Embedding input exceeds the model token budget.')
        embeddings = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        rows = embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
        if len(rows) != len(texts):
            raise EmbeddingModelError(
                "Embedding model returned a different number of vectors than inputs."
            )
        vectors = [[float(value) for value in row] for row in rows]
        if any(len(vector) != self._dimension for vector in vectors):
            raise EmbeddingModelError(
                "Embedding model returned a vector with an unexpected dimension."
            )
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise EmbeddingModelError('Embedding model returned a non-finite vector.')
        return vectors
