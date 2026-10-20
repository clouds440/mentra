"""One storage lifecycle shared by every upload purpose."""

import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from uuid import uuid4
from sqlalchemy import select, update, delete, func, or_, exists
from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from .tables import assets, bindings, reads, speech, exports


def now():
    return datetime.now(timezone.utc)


def missing():
    return AppError("FILES_NOT_FOUND", "This file is no longer available.", 404)


def image_media(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class FilesService:
    def __init__(self, sessions, provider, settings):
        self.sessions, self.provider, self.settings = sessions, provider, settings
        self.slots = BoundedSemaphore(settings.files_concurrency)
        from app.documents import create_document_reader

        self.reader = create_document_reader()

    def close(self):
        self.provider.close()

    def check_configuration(self):
        self.provider._ready()

    def _limit(self, purpose):
        if purpose not in ("chat", "library", "assessment", "speech", "export"):
            raise AppError("FILES_PURPOSE", "Unsupported file purpose.", 422)
        if purpose == "speech":
            return self.settings.speech_max_upload_bytes
        if purpose in ("chat", "assessment"):
            return 25 * 1024 * 1024
        return self.settings.rag_max_upload_bytes

    def metadata(self, owner, identifier, purpose=None):
        with self.sessions() as session:
            row = (
                session.execute(
                    select(assets).where(
                        assets.c.id == identifier, assets.c.learner_id == owner
                    )
                )
                .mappings()
                .first()
            )
        if (
            not row
            or row["state"] not in ("STAGED", "ACTIVE")
            or (row["expires_at"] and row["expires_at"] <= now())
        ):
            raise missing()
        if purpose and row["purpose"] != purpose:
            raise AppError(
                "FILES_PURPOSE", "This upload belongs to another operation.", 409
            )
        return dict(row)

    @staticmethod
    def public(row):
        return {
            key: row[key]
            for key in (
                "id",
                "filename",
                "size_bytes",
                "media_type",
                "state",
                "purpose",
            )
        }

    def receipt(self, owner, key):
        with self.sessions() as session:
            row = (
                session.execute(
                    select(assets).where(
                        assets.c.learner_id == owner, assets.c.request_key == key
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise missing()
        return self.public(row)

    def upload(self, owner, stream, filename, purpose, key):
        maximum = self._limit(purpose)
        if not 1 <= len(key) <= 120:
            raise AppError("FILES_KEY", "Invalid upload operation key.", 422)
        if not self.slots.acquire(blocking=False):
            raise AppError(
                "FILES_BUSY", "File transfer capacity is busy. Please retry.", 429
            )
        try:
            with TemporaryDirectory(prefix="mentra-upload-") as directory:
                path = Path(directory) / "original"
                digest, size = hashlib.sha256(), 0
                with path.open("xb") as output:
                    while chunk := stream.read(min(256 * 1024, maximum - size + 1)):
                        size += len(chunk)
                        if size > maximum:
                            raise AppError(
                                "FILES_SIZE",
                                "This file exceeds the upload size limit.",
                                413,
                            )
                        digest.update(chunk)
                        output.write(chunk)
                if not size:
                    raise AppError("FILES_EMPTY", "Choose a non-empty file.", 422)
                filename = Path((filename or "file").replace("\\", "/")).name[:200]
                with path.open("rb") as source:
                    header = source.read(32)
                media = image_media(header)
                resource = "image" if media else "raw"
                if purpose == "speech":
                    from app.speech.engine import decode_audio

                    # Validate the real container and duration before storing externally.
                    decode_audio(path.read_bytes(), self.settings.speech_max_seconds)
                    media, resource = "application/octet-stream", "video"
                elif purpose == "export":
                    media = "text/calendar"
                elif media:
                    from app.vision.chat_images import prepare_chat_image

                    prepare_chat_image(path.read_bytes())
                else:
                    from app.documents import DocumentReadError

                    try:
                        media = self.reader.detect(path, filename)
                    except DocumentReadError as error:
                        raise AppError("FILES_FORMAT", str(error), 422) from None
                fingerprint = digest.hexdigest()
                token = str(uuid4())
                with self.sessions.begin() as session:
                    lock_owner(session, owner)
                    row = (
                        session.execute(
                            select(assets)
                            .where(
                                assets.c.learner_id == owner,
                                assets.c.request_key == key,
                            )
                            .with_for_update()
                        )
                        .mappings()
                        .first()
                    )
                    if row:
                        if (
                            row["sha256"] != fingerprint
                            or row["purpose"] != purpose
                            or row["filename"] != filename
                        ):
                            raise AppError(
                                "FILES_CONFLICT",
                                "This upload key was used for another file.",
                                409,
                            )
                        if row["state"] in ("STAGED", "ACTIVE"):
                            if row["expires_at"] and row["expires_at"] <= now():
                                raise missing()
                            return self.public(row)
                        if row["state"] != "UPLOADING":
                            raise missing()
                        if row["lease_until"] and row["lease_until"] > now():
                            raise AppError(
                                "FILES_PENDING",
                                "This upload is still processing. Retry shortly.",
                                409,
                            )
                        row = dict(row)
                        session.execute(
                            update(assets)
                            .where(assets.c.id == row["id"])
                            .values(
                                lease_token=token,
                                lease_until=now() + timedelta(minutes=5),
                            )
                        )
                    else:
                        staged = session.scalar(
                            select(func.count())
                            .select_from(assets)
                            .where(
                                assets.c.learner_id == owner,
                                assets.c.state.in_(["UPLOADING", "STAGED"]),
                            )
                        )
                        if staged >= 8:
                            raise AppError(
                                "FILES_CAPACITY",
                                "Finish or remove pending uploads first.",
                                429,
                            )
                        used = session.scalar(
                            select(
                                func.coalesce(func.sum(assets.c.size_bytes), 0)
                            ).where(
                                assets.c.learner_id == owner,
                                assets.c.purpose == purpose,
                                assets.c.state.in_(["UPLOADING", "STAGED"]),
                            )
                        )
                        quota = (
                            100 * 1024 * 1024
                            if purpose == "chat"
                            else self.settings.rag_storage_quota_bytes
                        )
                        if used + size > quota:
                            raise AppError(
                                "FILES_CAPACITY", "Pending file storage is full.", 413
                            )
                        identifier = str(uuid4())
                        # Provider suffix is an opaque storage detail, never the
                        # downloaded filename. Cloudinary rejects .bin; normalize
                        # supported text/code/extensionless originals to .txt.
                        suffix = {
                            "application/pdf": ".pdf",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
                            "text/calendar": ".ics",
                        }.get(media, ".txt")
                        public_id = (
                            f"{self.settings.files_namespace}/{self.settings.app_env}/{identifier}"
                            + (suffix if resource == "raw" else "")
                        )
                        row = dict(
                            id=identifier,
                            learner_id=owner,
                            purpose=purpose,
                            request_key=key,
                            filename=filename,
                            size_bytes=size,
                            sha256=fingerprint,
                            media_type=media,
                            environment=self.provider.environment,
                            public_id=public_id,
                            resource_type=resource,
                            state="UPLOADING",
                            created_at=now(),
                            expires_at=now() + timedelta(minutes=15)
                            if purpose == "speech"
                            else now() + timedelta(days=1),
                            lease_token=token,
                            lease_until=now() + timedelta(minutes=5),
                        )
                        session.execute(assets.insert().values(**row))
                try:
                    result = self.provider.upload(path, row)
                    self.provider.verify(row)
                    with self.sessions.begin() as session:
                        updated = session.execute(
                            update(assets)
                            .where(
                                assets.c.id == row["id"],
                                assets.c.lease_token == token,
                                assets.c.state == "UPLOADING",
                            )
                            .values(
                                state="STAGED",
                                asset_id=result.get("asset_id"),
                                version=result.get("version"),
                                lease_token=None,
                                lease_until=None,
                            )
                        )
                        if not updated.rowcount:
                            raise AppError(
                                "FILES_CANCELLED", "This upload was cancelled.", 409
                            )
                    return self.public(dict(row, state="STAGED"))
                except Exception:
                    # Deterministic ID + overwrite=false make ambiguous upload retries safe.
                    with self.sessions.begin() as session:
                        session.execute(
                            update(assets)
                            .where(
                                assets.c.id == row["id"], assets.c.lease_token == token
                            )
                            .values(lease_until=now(), error="FILES_UPLOAD_FAILED")
                        )
                    raise
        finally:
            self.slots.release()

    def bind(self, session, owner, identifier, purpose, target, *, reuse=False):
        row = (
            session.execute(
                select(assets)
                .where(assets.c.id == identifier, assets.c.learner_id == owner)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if (
            not row
            or row["state"] not in ("STAGED", "ACTIVE")
            or (row["expires_at"] and row["expires_at"] <= now())
        ):
            raise missing()
        existing = session.execute(
            select(bindings.c.id).where(
                bindings.c.file_id == identifier,
                bindings.c.learner_id == owner,
                bindings.c.released_at.is_(None),
                *[bindings.c[k] == v for k, v in target.items()],
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        if not reuse and (row["purpose"] != purpose or row["state"] != "STAGED"):
            raise AppError(
                "FILES_ALREADY_USED", "This upload has already been used.", 409
            )
        identifier_binding = str(uuid4())
        session.execute(
            bindings.insert().values(
                id=identifier_binding,
                learner_id=owner,
                file_id=identifier,
                purpose=purpose,
                created_at=now(),
                **target,
            )
        )
        session.execute(
            update(assets)
            .where(assets.c.id == identifier)
            .values(
                state="ACTIVE",
                expires_at=row["expires_at"]
                if purpose in ("speech", "export")
                else None,
            )
        )
        return identifier_binding

    def binding(self, owner, file_id, purpose, target):
        with self.sessions() as session:
            value = session.scalar(
                select(bindings.c.id).where(
                    bindings.c.learner_id == owner,
                    bindings.c.file_id == file_id,
                    bindings.c.purpose == purpose,
                    bindings.c.released_at.is_(None),
                    *[bindings.c[k] == v for k, v in target.items()],
                )
            )
        if not value:
            raise missing()
        return value

    def release(self, session, owner, **target):
        session.execute(
            update(bindings)
            .where(
                bindings.c.learner_id == owner,
                bindings.c.released_at.is_(None),
                *[bindings.c[k] == v for k, v in target.items()],
            )
            .values(released_at=now())
        )

    def cancel(self, owner, identifier):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            session.execute(
                update(assets)
                .where(
                    assets.c.id == identifier,
                    assets.c.learner_id == owner,
                    assets.c.state.in_(["UPLOADING", "STAGED"]),
                )
                .values(state="DELETE_PENDING", expires_at=now())
            )

    @contextmanager
    def open_original(self, owner, identifier):
        row = self.metadata(owner, identifier)
        token = str(uuid4())
        with self.sessions.begin() as session:
            current = session.execute(
                select(assets.c.state)
                .where(assets.c.id == identifier)
                .with_for_update()
            ).scalar_one()
            if current not in ("ACTIVE", "STAGED"):
                raise missing()
            session.execute(
                reads.insert().values(
                    id=token,
                    file_id=identifier,
                    expires_at=now() + timedelta(minutes=15),
                )
            )
        try:
            yield row
        finally:
            with self.sessions.begin() as session:
                session.execute(delete(reads).where(reads.c.id == token))

    @contextmanager
    def materialize(self, owner, identifier):
        with (
            self.open_original(owner, identifier) as row,
            TemporaryDirectory(prefix="mentra-file-") as directory,
        ):
            path = Path(directory) / "original"
            digest, size = hashlib.sha256(), 0
            with self.provider.stream(row) as response, path.open("xb") as output:
                for chunk in response.iter_bytes(256 * 1024):
                    size += len(chunk)
                    if size > row["size_bytes"]:
                        raise AppError(
                            "FILES_INTEGRITY", "Stored file verification failed.", 502
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if size != row["size_bytes"] or digest.hexdigest() != row["sha256"]:
                raise AppError(
                    "FILES_INTEGRITY", "Stored file verification failed.", 502
                )
            yield path

    def read(self, owner, identifier):
        with self.materialize(owner, identifier) as path:
            return path.read_bytes()

    def cleanup(self, limit=50):
        """Durable deletion queue is embedded in registry state, with fenced leases."""
        from app.chat.repositories.tables import attachments, conversations
        from app.chat.repositories.attachments import AttachmentRepository
        from app.rag.repositories.tables import versions, documents

        # Use the existing owner lock/recheck for unsent expiry, so cleanup
        # cannot release a file while the same owner binds it to a message.
        AttachmentRepository(self.sessions, self).cleanup_unsent(limit=limit)

        with self.sessions.begin() as session:
            # Revocation precedes deletion; these also recover missed domain cleanup.
            expired_chats = (
                select(attachments.c.id)
                .outerjoin(
                    conversations, attachments.c.conversation_id == conversations.c.id
                )
                .where(conversations.c.deleted_at.is_not(None))
            )
            deleted_versions = (
                select(versions.c.id)
                .join(documents, versions.c.document_id == documents.c.id)
                .where(documents.c.deleted_at.is_not(None))
            )
            session.execute(
                update(bindings)
                .where(
                    bindings.c.released_at.is_(None),
                    or_(
                        bindings.c.chat_attachment_id.in_(expired_chats),
                        bindings.c.document_version_id.in_(deleted_versions),
                    ),
                )
                .values(released_at=now())
            )
            session.execute(delete(reads).where(reads.c.expires_at < now()))
            candidates = (
                session.execute(
                    select(assets)
                    .where(
                        assets.c.state != "DELETED",
                        assets.c.environment == self.provider.environment,
                        assets.c.public_id.startswith(
                            f"{self.settings.files_namespace}/{self.settings.app_env}/",
                            autoescape=True,
                        ),
                        or_(
                            assets.c.lease_until.is_(None), assets.c.lease_until < now()
                        ),
                        or_(assets.c.retry_at.is_(None), assets.c.retry_at <= now()),
                        or_(
                            assets.c.expires_at <= now(),
                            assets.c.state == "DELETE_PENDING",
                            (assets.c.state == "ACTIVE")
                            & ~exists(
                                select(bindings.c.id).where(
                                    bindings.c.file_id == assets.c.id,
                                    bindings.c.released_at.is_(None),
                                )
                            ),
                        ),
                        ~exists(
                            select(reads.c.id).where(
                                reads.c.file_id == assets.c.id,
                                reads.c.expires_at > now(),
                            )
                        ),
                    )
                    .order_by(assets.c.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            claimed = []
            for row in candidates:
                # Re-read references after acquiring the asset lock. A binding
                # or read lease can commit after the candidate query's snapshot.
                if session.scalar(
                    select(reads.c.id)
                    .where(reads.c.file_id == row["id"], reads.c.expires_at > now())
                    .limit(1)
                ):
                    continue
                expired = row["expires_at"] is not None and row["expires_at"] <= now()
                if (
                    row["state"] == "ACTIVE"
                    and not expired
                    and session.scalar(
                        select(bindings.c.id)
                        .where(
                            bindings.c.file_id == row["id"],
                            bindings.c.released_at.is_(None),
                        )
                        .limit(1)
                    )
                ):
                    continue
                token = str(uuid4())
                session.execute(
                    update(assets)
                    .where(assets.c.id == row["id"])
                    .values(
                        state="DELETE_PENDING",
                        lease_token=token,
                        lease_until=now()
                        + timedelta(
                            seconds=max(
                                300, self.settings.files_timeout_seconds * limit + 60
                            )
                        ),
                    )
                )
                claimed.append(dict(row, lease_token=token))
            session.execute(delete(speech).where(speech.c.expires_at < now()))
            session.execute(delete(exports).where(exports.c.expires_at < now()))
        for row in claimed:
            try:
                self.provider.destroy(row)
                values = dict(
                    state="DELETED", lease_token=None, lease_until=None, error=None
                )
            except Exception:
                values = dict(
                    attempts=row["attempts"] + 1,
                    lease_token=None,
                    lease_until=None,
                    error="FILES_DELETE_FAILED",
                    retry_at=now()
                    + timedelta(seconds=min(3600, 10 * 2 ** min(row["attempts"], 8))),
                )
            with self.sessions.begin() as session:
                session.execute(
                    update(assets)
                    .where(
                        assets.c.id == row["id"],
                        assets.c.lease_token == row["lease_token"],
                    )
                    .values(**values)
                )
        return len(claimed)
