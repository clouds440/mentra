"""All previews and original downloads use this authenticated streaming path."""

import re
from threading import Lock
import anyio
from urllib.parse import quote
from sqlalchemy import select
from fastapi.responses import StreamingResponse, Response
from starlette.concurrency import run_in_threadpool
from .tables import bindings, exports
from .service import missing, now


class OriginalResponse(StreamingResponse):
    """Reap provider connections/leases even on an immediate disconnect."""

    def __init__(self, *args, cleanup, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            with anyio.move_on_after(600):
                await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self.cleanup)


def authorize(request, owner, file_id, binding_id, include_archived=False):
    files = request.app.state.files_service
    with files.sessions() as session:
        binding = (
            session.execute(
                select(bindings).where(
                    bindings.c.id == binding_id,
                    bindings.c.file_id == file_id,
                    bindings.c.learner_id == owner,
                    bindings.c.released_at.is_(None),
                )
            )
            .mappings()
            .first()
        )
    if not binding:
        raise missing()
    purpose = binding["purpose"]
    if purpose == "chat":
        from app.chat.repositories.tables import attachments, conversations

        with files.sessions() as session:
            found = session.scalar(
                select(attachments.c.id)
                .join(
                    conversations, attachments.c.conversation_id == conversations.c.id
                )
                .where(
                    attachments.c.id == binding["chat_attachment_id"],
                    attachments.c.file_id == file_id,
                    attachments.c.learner_id == owner,
                    conversations.c.deleted_at.is_(None),
                )
            )
        if not found:
            raise missing()
    elif purpose == "library":
        from app.rag.repositories.tables import versions

        with files.sessions() as session:
            doc = session.scalar(
                select(versions.c.document_id).where(
                    versions.c.id == binding["document_version_id"],
                    versions.c.learner_id == owner,
                    versions.c.file_id == file_id,
                )
            )
        if not doc:
            raise missing()
        request.app.state.rag_service.source(
            owner, doc, binding["document_version_id"], include_archived
        )
    elif purpose == "assessment":
        from app.assessments.repositories.tables import attempts

        with files.sessions() as session:
            found = session.scalar(
                select(attempts.c.id).where(
                    attempts.c.id == binding["assessment_attempt_id"],
                    attempts.c.learner_id == owner,
                    attempts.c.source_file_id == file_id,
                )
            )
        if not found:
            raise missing()
    elif purpose == "export":
        with files.sessions() as session:
            export = (
                session.execute(
                    select(exports).where(
                        exports.c.id == binding["export_id"],
                        exports.c.learner_id == owner,
                        exports.c.expires_at > now(),
                    )
                )
                .mappings()
                .first()
            )
        if not export:
            raise missing()
        event = request.app.state.history_management.events.detail(
            owner, export["event_id"]
        )
        if event["revision"] != export["event_revision"]:
            raise missing()
    else:
        raise missing()  # Speech is processor-only, never a download entitlement.
    return files.metadata(owner, file_id)


def byte_range(value, size):
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()):
        return False
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix <= 0:
            return False
        start, end = max(0, size - suffix), size - 1
    else:
        start, end = int(first), min(int(last), size - 1) if last else size - 1
    return (start, end) if 0 <= start <= end < size else False


async def deliver(
    request,
    owner,
    file_id,
    binding_id,
    disposition="attachment",
    include_archived=False,
):
    row = await run_in_threadpool(
        authorize, request, owner, file_id, binding_id, include_archived
    )
    files = request.app.state.files_service
    selected = byte_range(request.headers.get("range"), row["size_bytes"])
    common = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    if selected is False:
        return Response(
            status_code=416,
            headers={**common, "Content-Range": f"bytes */{row['size_bytes']}"},
        )
    safe = (
        row["media_type"].startswith("image/") or row["media_type"] == "application/pdf"
    )
    mode = "inline" if disposition == "inline" and safe else "attachment"
    common["Content-Disposition"] = (
        f"{mode}; filename*=UTF-8''{quote(row['filename'], safe='')}"
    )
    start, end = selected or (0, row["size_bytes"] - 1)
    common["Content-Length"] = str(end - start + 1)
    if selected:
        common["Content-Range"] = f"bytes {start}-{end}/{row['size_bytes']}"
    status = 206 if selected else 200
    if request.method == "HEAD":
        return Response(
            status_code=status, headers=common, media_type=row["media_type"]
        )
    if not files.slots.acquire(blocking=False):
        from app.core.exceptions import AppError

        raise AppError(
            "FILES_BUSY", "File transfer capacity is busy. Please retry.", 429
        )
    # Acquire upstream before emitting success headers. A lazy generator would
    # turn upstream authentication/outage failures into truncated HTTP 200s.
    lease = files.open_original(owner, file_id)
    upstream = None
    try:
        leased = await run_in_threadpool(lease.__enter__)
        upstream = files.provider.stream(
            leased, f"bytes={start}-{end}" if selected else None
        )
        response = await run_in_threadpool(upstream.__enter__)
    except BaseException:
        if upstream:
            await run_in_threadpool(upstream.__exit__, None, None, None)
        await run_in_threadpool(lease.__exit__, None, None, None)
        files.slots.release()
        raise
    cleanup_lock = Lock()
    cleaned = False

    def cleanup():
        nonlocal cleaned
        with cleanup_lock:
            if cleaned:
                return
            cleaned = True
        try:
            upstream.__exit__(None, None, None)
        finally:
            try:
                lease.__exit__(None, None, None)
            finally:
                files.slots.release()

    def chunks():
        skip = start if selected and response.status_code != 206 else 0
        remaining = end - start + 1
        try:
            for chunk in response.iter_bytes(256 * 1024):
                if skip:
                    drop = min(skip, len(chunk))
                    skip -= drop
                    chunk = chunk[drop:]
                if not chunk:
                    continue
                value = chunk[:remaining]
                remaining -= len(value)
                if value:
                    yield value
                if remaining == 0:
                    break
            if remaining:
                raise IOError("Original transfer was incomplete")
        finally:
            cleanup()

    return OriginalResponse(
        chunks(),
        cleanup=cleanup,
        status_code=status,
        media_type=row["media_type"],
        headers=common,
    )
