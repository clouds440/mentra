"""Private visual metadata transactions and quota/lease enforcement."""
from uuid import UUID, uuid5
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.core.exceptions import AppError
from app.files.tables import assets
from app.rag.errors import not_found
from .tables import visuals, versions, documents, chunks, generations
from .postgres import now

def visual_bytes_used(session, owner):
    ids = (
        select(visuals.c.file_id)
        .join(documents, visuals.c.document_id == documents.c.id)
        .where(visuals.c.learner_id == owner, documents.c.purged_at.is_(None))
        .distinct()
    )
    originals = select(versions.c.file_id).where(versions.c.learner_id == owner)
    return session.scalar(
        select(func.coalesce(func.sum(assets.c.size_bytes), 0)).where(
            assets.c.id.in_(ids), ~assets.c.id.in_(originals)
        )
    )


class VisualStore:
    def __init__(self, repository, files, settings):
        self.repo, self.files, self.settings = repository, files, settings

    def save(self, job, version, item, stored, data_size, caption):
        with self.repo.sessions.begin() as session:
            from app.auth.repositories.tables import learner

            session.execute(
                select(learner.c.id)
                .where(learner.c.id == job["learner_id"])
                .with_for_update()
            ).scalar_one()
            self.repo._lease(session, job)
            original_used = session.scalar(
                select(func.coalesce(func.sum(versions.c.size_bytes), 0))
                .join(documents, versions.c.document_id == documents.c.id)
                .where(
                    versions.c.learner_id == job["learner_id"],
                    documents.c.purged_at.is_(None),
                )
            )
            counted = session.scalar(
                select(visuals.c.id)
                .where(
                    visuals.c.learner_id == job["learner_id"],
                    visuals.c.file_id == stored["id"],
                )
                .limit(1)
            )
            extra = (
                0 if counted or stored["id"] == version["file_id"] else data_size
            )
            if (
                original_used
                + visual_bytes_used(session, job["learner_id"])
                + extra
                > self.settings.rag_storage_quota_bytes
            ):
                raise AppError(
                    "RAG_QUOTA_EXCEEDED",
                    "Your material storage quota is full.",
                    413,
                )
            self.files.bind(
                session,
                job["learner_id"],
                stored["id"],
                "library",
                dict(document_version_id=version["id"]),
                reuse=True,
            )
            session.execute(
                insert(visuals)
                .values(
                    id=str(uuid5(UUID(job["generation_id"]), item["sha256"])),
                    learner_id=job["learner_id"],
                    document_id=job["document_id"],
                    version_id=version["id"],
                    generation_id=job["generation_id"],
                    file_id=stored["id"],
                    sha256=item["sha256"],
                    media_type=item["media_type"],
                    width=item["width"],
                    height=item["height"],
                    caption=caption,
                    block_refs=item['block_refs'],
                    locations=item["locations"],
                    created_at=now(),
                )
                .on_conflict_do_nothing()
            )

    def rows(self, owner, ids):
        with self.repo.sessions() as session:
            rows = (
                session.execute(
                    select(visuals, chunks.c.id.label("_chunk"))
                    .join(chunks, chunks.c.generation_id == visuals.c.generation_id)
                    .join(generations, visuals.c.generation_id == generations.c.id)
                    .where(
                        visuals.c.learner_id == owner,
                        chunks.c.learner_id == owner,
                        chunks.c.id.in_(ids),
                        generations.c.indexed_at.is_not(None),
                        generations.c.state.in_(["READY", "SUPERSEDED"]),
                    )
                    .order_by(visuals.c.id, chunks.c.ordinal)
                )
                .mappings()
                .all()
            )
        return rows

    def get(self, owner, identifier):
        with self.repo.sessions() as session:
            row = (
                session.execute(
                    select(visuals)
                    .join(generations, visuals.c.generation_id == generations.c.id)
                    .where(
                        visuals.c.learner_id == owner,
                        visuals.c.id == identifier,
                        generations.c.indexed_at.is_not(None),
                        generations.c.state.in_(["READY", "SUPERSEDED"]),
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise not_found()
        return dict(row)
