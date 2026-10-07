import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.rag.embeddings import (
    QUERY_INSTRUCTION,
    EmbeddingModelError,
    SentenceTransformerEmbeddingService,
)


class FakeSentenceTransformer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return 2

    def encode(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.calls.append((texts, kwargs))
        return [[0.6, 0.8] for _ in texts]


class EmbeddingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.model_path = Path(self.temp_dir.name)
        (self.model_path / "model-metadata.json").write_text(
            json.dumps(
                {
                    "model_name": "BAAI/bge-small-en-v1.5",
                    "model_version": "test-revision",
                }
            ),
            encoding="utf-8",
        )
        self.settings = Settings(
            embedding_model="BAAI/bge-small-en-v1.5",
            embedding_device="cpu",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_query_uses_bge_instruction_and_normalized_vectors(self) -> None:
        model = FakeSentenceTransformer()
        service = SentenceTransformerEmbeddingService(
            self.settings,
            model_path=self.model_path,
            model_loader=lambda *_args, **_kwargs: model,
        )

        vector = service.embed_query("What is a vector?")

        self.assertEqual(vector, [0.6, 0.8])
        self.assertEqual(
            model.calls[0][0],
            [f"{QUERY_INSTRUCTION}What is a vector?"],
        )
        self.assertTrue(model.calls[0][1]["normalize_embeddings"])
        self.assertEqual(service.dimension, 2)
        self.assertEqual(service.model_name, "BAAI/bge-small-en-v1.5")
        self.assertEqual(service.model_version, "test-revision")

    def test_documents_are_encoded_in_a_configured_batch(self) -> None:
        model = FakeSentenceTransformer()
        service = SentenceTransformerEmbeddingService(
            self.settings,
            model_path=self.model_path,
            model_loader=lambda *_args, **_kwargs: model,
            batch_size=2,
        )

        vectors = service.embed_documents(["first", "second", "third"])

        self.assertEqual(vectors, [[0.6, 0.8], [0.6, 0.8], [0.6, 0.8]])
        self.assertEqual(model.calls[0][0], ["first", "second", "third"])
        self.assertEqual(model.calls[0][1]["batch_size"], 2)
        self.assertTrue(model.calls[0][1]["normalize_embeddings"])

    def test_empty_documents_do_not_call_model(self) -> None:
        model = FakeSentenceTransformer()
        service = SentenceTransformerEmbeddingService(
            self.settings,
            model_path=self.model_path,
            model_loader=lambda *_args, **_kwargs: model,
        )

        self.assertEqual(service.embed_documents([]), [])
        self.assertEqual(model.calls, [])

    def test_model_load_is_local_only_after_image_bake(self) -> None:
        captured: dict[str, Any] = {}

        def loader(model_path: str, **kwargs: Any) -> FakeSentenceTransformer:
            captured["model_path"] = model_path
            captured.update(kwargs)
            return FakeSentenceTransformer()

        SentenceTransformerEmbeddingService(
            self.settings,
            model_path=self.model_path,
            model_loader=loader,
        )

        self.assertEqual(captured["model_path"], str(self.model_path))
        self.assertTrue(captured["local_files_only"])
        self.assertEqual(captured["device"], "cpu")

    def test_missing_baked_model_metadata_fails_without_downloading(self) -> None:
        empty_path = Path(self.temp_dir.name) / "empty"
        empty_path.mkdir()
        loader_called = False

        def loader(*_args: Any, **_kwargs: Any) -> FakeSentenceTransformer:
            nonlocal loader_called
            loader_called = True
            return FakeSentenceTransformer()

        with self.assertRaisesRegex(EmbeddingModelError, "Rebuild the backend image"):
            SentenceTransformerEmbeddingService(
                self.settings,
                model_path=empty_path,
                model_loader=loader,
            )
        self.assertFalse(loader_called)

    def test_runtime_model_must_match_baked_model(self) -> None:
        settings = Settings(embedding_model="different-model")

        with self.assertRaisesRegex(EmbeddingModelError, "does not match"):
            SentenceTransformerEmbeddingService(
                settings,
                model_path=self.model_path,
                model_loader=lambda *_args, **_kwargs: FakeSentenceTransformer(),
            )


if __name__ == "__main__":
    unittest.main()
