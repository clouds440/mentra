"""Private visual files; immutable provenance and leases remain RAG-owned."""

import base64
import hashlib
from io import BytesIO
from uuid import UUID, uuid5
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.core.exceptions import AppError
from app.files.tables import assets
from app.rag.errors import not_found, ExtractionError
from .repositories.tables import visuals, versions, documents, chunks, generations
from .repositories.postgres import now


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


class Visuals:
    def __init__(self, repository, files, settings):
        self.repo, self.files, self.settings = repository, files, settings

    def persist(self, job, version, parsed):
        items = parsed.get("visuals", [])
        if len(items) > 32:
            raise ExtractionError("Visual count exceeds the processing limit.")
        total = 0
        for item in items:
            self.repo.stage(job, "saving_visuals", self.settings.rag_job_lease_seconds)
            try:
                data = base64.b64decode(item["data_base64"], validate=True)
            except (ValueError, KeyError) as error:
                raise ExtractionError("Invalid extracted visual.") from error
            total += len(data)
            if (
                len(data) > 8 * 1024 * 1024
                or total > 24 * 1024 * 1024
                or hashlib.sha256(data).hexdigest() != item["sha256"]
            ):
                raise ExtractionError("Visual integrity or size limit failed.")
            from PIL import Image

            try:
                with Image.open(BytesIO(data)) as image:
                    if (
                        image.size != (item["width"], item["height"])
                        or image.format not in ("PNG", "JPEG")
                        or image.width * image.height > 30_000_000
                    ):
                        raise ValueError("Visual dimensions or format mismatch")
                    if item["media_type"] != (
                        "image/png" if image.format == "PNG" else "image/jpeg"
                    ):
                        raise ValueError("Visual media type mismatch")
                    image.verify()
            except (OSError, ValueError) as error:
                raise ExtractionError("Invalid extracted visual.") from error
            refs = item.get("block_refs", [])
            if not refs or any(
                type(i) is not int or i < 0 or i >= len(parsed["blocks"]) for i in refs
            ):
                raise ExtractionError("Visual source mapping is invalid.")
            extension = "png" if item["media_type"] == "image/png" else "jpg"
            if item["sha256"] == version["file_hash"]:
                stored = dict(id=version["file_id"])
            else:
                stored = self.files.upload(
                    job["learner_id"],
                    BytesIO(data),
                    "diagram." + extension,
                    "library",
                    f"visual:{version['id']}:{item['sha256'][:40]}",
                )
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
                    0 if counted or stored["id"] == version["file_id"] else len(data)
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
                caption = (
                    " / ".join(parsed["blocks"][refs[0]].get("heading_path", []))
                    .replace("\x0b", " ")
                    .strip()[:200]
                    or "Source diagram"
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
                        block_refs=refs,
                        locations=item["locations"],
                        created_at=now(),
                    )
                    .on_conflict_do_nothing()
                )

    def for_chunks(self, owner, records):
        if not records:
            return {}
        if not any(
            span.get("visual_keys") for record in records for span in record["spans"]
        ):
            return {}
        ids = [row["id"] for row in records]
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
        result = {}
        for record in records:
            blocks = {span["block"] for span in record["spans"]}
            result[record["id"]] = [
                self.public(row)
                for row in rows
                if row["_chunk"] == record["id"]
                and blocks.intersection(row["block_refs"])
            ][:4]
        return result

    @staticmethod
    def public(row):
        return {
            key: row[key]
            for key in (
                "id",
                "document_id",
                "version_id",
                "generation_id",
                "media_type",
                "width",
                "height",
                "caption",
                "locations",
            )
        }

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
