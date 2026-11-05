"""Private CPU-local semantic lookup; PostgreSQL owns vectors and deletion."""

from threading import Lock
from time import monotonic

import numpy as np
from app.rag.text_windows import token_windows
from app.core.logging import workflow_logger

from app.core.config import settings
from ..repositories.memory_vectors import MemoryVectorRepository



class MemorySemanticLookup:
    def __init__(self, sessions, embedding=None):
        self.sessions, self.embedding = sessions, embedding
        self.repository = MemoryVectorRepository(sessions)
        self.lock = Lock()
        self.retry_after = 0

    def close(self):
        if self.embedding is not None and hasattr(self.embedding, "close"):
            self.embedding.close()

    def related(self, owner, text):
        if not settings.memory_semantic_enabled:
            return [], True
        if monotonic() < self.retry_after:
            return [], False
        with self.lock:
            try:
                if self.embedding is None:
                    from app.rag.embedding_process import ProcessEmbeddingService

                    self.embedding = ProcessEmbeddingService(settings)
                engine = self.embedding
                key = f"{engine.model_name}:{engine.model_version}:{engine.dimension}:symmetric-v2"
                missing = self.repository.missing(owner, key)
                if missing:
                    ready, spans, flattened = [], [], []
                    for row in missing:
                        try:
                            parts = self.windows(engine, row['content'], 8)
                        except ValueError:
                            workflow_logger.event('memory.semantic_input_unavailable', reason='token_budget')
                            continue
                        if not parts:
                            workflow_logger.event('memory.semantic_input_unavailable', reason='empty')
                            continue
                        ready.append(row)
                        spans.append((len(flattened),len(flattened)+len(parts)))
                        flattened.extend(parts)
                    encoded=np.asarray(engine.embed_similarity(flattened),dtype=np.float32) if flattened else []
                    if len(encoded)!=len(flattened):
                        raise ValueError('Incomplete memory embedding batch')
                    vectors=[encoded[start:end].mean(axis=0) for start,end in spans]
                    missing = ready
                    entries = []
                    for row, vector in zip(missing, vectors, strict=True):
                        data = np.asarray(vector, dtype="<f4")
                        if data.shape != (engine.dimension,) or not np.isfinite(data).all() or not np.linalg.norm(data):
                            raise ValueError("Invalid local embedding")
                        entries.append(dict(learner_id=owner, memory_id=row['id'], revision=row['revision'],
                            model_key=key, dimension=engine.dimension, vector=data.tobytes()))
                    if not self.repository.save(owner, entries):
                        return [], False
                rows = self.repository.rows(owner, key)
                if len(rows) > 1000 or any(row["vector"] is None for row in rows):
                    workflow_logger.event('memory.semantic_incomplete', reason='overflow' if len(rows) > 1000 else 'backfill')
                    return [], False
                if not rows:
                    return [], True
                # Multiple small windows retain corrections late in long or
                # multilingual messages; no private text leaves this process.
                windows = []
                # Keep the original small, overlapping query windows: a long
                # message must not dilute a short correction into one large vector.
                for start in range(0,min(len(text),6000),192):
                    windows.extend(self.windows(engine,text[start:start+256],32-len(windows)))
                if not windows:
                    return [], False
                queries = np.asarray(engine.embed_similarity(windows), dtype=np.float32)
                queries /= np.maximum(
                    np.linalg.norm(queries, axis=1, keepdims=True), 1e-12
                )
                scored = []
                for row in rows:
                    try:
                        vector = np.frombuffer(row["vector"], dtype="<f4")
                    except (TypeError, ValueError):
                        vector = np.asarray([], dtype=np.float32)
                    if (
                        vector.size != engine.dimension
                        or row["dimension"] != engine.dimension
                        or not np.isfinite(vector).all()
                        or not np.linalg.norm(vector)
                    ):
                        self.repository.invalidate(owner, row['id'], row['revision'], key)
                        workflow_logger.event('memory.semantic_incomplete',reason='invalid_vector_rebuild')
                        return [], False
                    score = float(
                        np.max(queries @ vector)
                        / max(float(np.linalg.norm(vector)), 1e-12)
                    )
                    scored.append((score, row))
                scored.sort(key=lambda item: item[0], reverse=True)
                return [
                    {
                        key: value
                        for key, value in row.items()
                        if key not in ("vector", "dimension")
                    }
                    for _, row in scored[:8]
                ], True
            except Exception as error:
                workflow_logger.event(
                    "memory.semantic_unavailable", error_type=type(error).__name__
                )
                self.retry_after = monotonic() + 120
                return [], False  # Defer rather than creating avoidable duplicates.

    @staticmethod
    def windows(engine, text, maximum):
        if hasattr(engine, 'query_token_count') and hasattr(engine, 'max_tokens'):
            return token_windows(text, engine.query_token_count, engine.max_tokens, max_windows=maximum)
        # Compatibility for injected test adapters; production implements exact counting.
        return [text] if text else []
