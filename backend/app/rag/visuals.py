"""Private visual files; immutable provenance and leases remain RAG-owned."""

import base64
import hashlib
from io import BytesIO
from .repositories.visuals import VisualStore, visual_bytes_used
from app.rag.errors import not_found, ExtractionError


class Visuals:
    def __init__(self, repository, files, settings):
        self.repo, self.files, self.settings = repository, files, settings
        self.store = VisualStore(repository, files, settings)

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
            caption = (
                " / ".join(parsed["blocks"][refs[0]].get("heading_path", []))
                .replace("\x0b", " ")
                .strip()[:200]
                or "Source diagram"
            )
            self.store.save(job, version, item, stored, len(data), caption)

    def for_chunks(self, owner, records):
        if not records:
            return {}
        if not any(
            span.get("visual_keys") for record in records for span in record["spans"]
        ):
            return {}
        ids = [row["id"] for row in records]
        rows = self.store.rows(owner, ids)
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
        return self.store.get(owner, identifier)
