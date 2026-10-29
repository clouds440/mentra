"""Private CPU-local semantic lookup; PostgreSQL owns vectors and deletion."""

from threading import Lock
from time import monotonic

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.owner_transactions import lock_owner

from ..repositories.tables import memories as m
from ..repositories.tables import memory_vectors as v
from ..repositories.tables import preferences as p


class MemorySemanticLookup:
    def __init__(self, sessions, embedding=None):
        self.sessions, self.embedding = sessions, embedding
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
                key = f"{engine.model_name}:{engine.model_version}:{engine.dimension}:symmetric-v1"
                with self.sessions() as session:
                    missing = list(
                        session.execute(
                            select(m.c.id, m.c.revision, m.c.content)
                            .outerjoin(
                                v,
                                (v.c.learner_id == m.c.learner_id)
                                & (v.c.memory_id == m.c.id),
                            )
                            .where(
                                m.c.learner_id == owner,
                                m.c.status == "active",
                                or_(
                                    v.c.memory_id.is_(None),
                                    v.c.revision != m.c.revision,
                                    v.c.model_key != key,
                                ),
                            )
                            .order_by(m.c.pinned.desc(), m.c.updated_at.desc())
                            .limit(32)
                        ).mappings()
                    )
                if missing:
                    vectors = engine.embed_similarity(
                        [row["content"] for row in missing]
                    )
                    with self.sessions.begin() as session:
                        lock_owner(session, owner)
                        pref = session.scalar(
                            select(p.c.automatic_memory).where(p.c.learner_id == owner)
                        )
                        if pref is False:
                            return [], False
                        current = dict(
                            session.execute(
                                select(m.c.id, m.c.revision).where(
                                    m.c.learner_id == owner,
                                    m.c.id.in_([row["id"] for row in missing]),
                                    m.c.status == "active",
                                )
                            ).all()
                        )
                        entries = []
                        for row, vector in zip(missing, vectors, strict=True):
                            if current.get(row["id"]) != row["revision"]:
                                continue
                            data = np.asarray(vector, dtype="<f4")
                            if (
                                data.shape != (engine.dimension,)
                                or not np.isfinite(data).all()
                            ):
                                raise ValueError("Invalid local embedding")
                            entries.append(
                                dict(
                                    learner_id=owner,
                                    memory_id=row["id"],
                                    revision=row["revision"],
                                    model_key=key,
                                    dimension=engine.dimension,
                                    vector=data.tobytes(),
                                )
                            )
                        if entries:
                            stmt = insert(v).values(entries)
                            session.execute(
                                stmt.on_conflict_do_update(
                                    index_elements=["learner_id", "memory_id"],
                                    set_={
                                        name: getattr(stmt.excluded, name)
                                        for name in (
                                            "revision",
                                            "model_key",
                                            "dimension",
                                            "vector",
                                        )
                                    },
                                )
                            )
                with self.sessions() as session:
                    rows = list(
                        session.execute(
                            select(m, v.c.vector, v.c.dimension)
                            .outerjoin(
                                v,
                                (v.c.learner_id == m.c.learner_id)
                                & (v.c.memory_id == m.c.id)
                                & (v.c.revision == m.c.revision)
                                & (v.c.model_key == key),
                            )
                            .where(m.c.learner_id == owner, m.c.status == "active")
                            .limit(1000)
                        ).mappings()
                    )
                if any(row["vector"] is None for row in rows):
                    return [], False
                if not rows:
                    return [], True
                # Multiple small windows retain corrections late in long or
                # multilingual messages; no private text leaves this process.
                windows = [
                    text[start : start + 256]
                    for start in range(0, min(len(text), 6000), 192)
                ][:32]
                queries = np.asarray(engine.embed_similarity(windows), dtype=np.float32)
                queries /= np.maximum(
                    np.linalg.norm(queries, axis=1, keepdims=True), 1e-12
                )
                scored = []
                for row in rows:
                    vector = np.frombuffer(row["vector"], dtype="<f4")
                    if (
                        vector.size != engine.dimension
                        or row["dimension"] != engine.dimension
                    ):
                        continue
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
                from app.core.logging import workflow_logger

                workflow_logger.event(
                    "memory.semantic_unavailable", error_type=type(error).__name__
                )
                self.retry_after = monotonic() + 120
                return [], False  # Defer rather than creating avoidable duplicates.
