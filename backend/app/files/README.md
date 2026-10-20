# Files

The single backend file module. All original uploads, provider access, metadata,
bindings, transient materialization, downloads and deletion live here. Domain
modules retain their authorization and processing rules; they do not implement
storage providers or serve original bytes themselves.

## Configuration and deployment

- Set **server-only** `CLOUDINARY_URL=cloudinary://KEY:SECRET@CLOUD_NAME`.
- Default namespace is **`mentra/<APP_ENV>/`**, separate from EduVerse. The
  adapter explicitly sets the Media Library `asset_folder` and public ID prefix.
  Reads/deletes reject assets outside the configured namespace or cloud account.
- Originals use authenticated delivery, immutable generated IDs and no upload
  transformations. No public asset URLs or provider credentials reach clients.
- Run `python -m app.files.worker` (included in Compose) for deletion, expiry
  and orphan reconciliation. It initializes no model, OCR or embedding service.
- Apply Alembic head before starting API/workers. `20261020_0028` refuses to drop
  legacy columns if legacy file data still exists. This installation discarded
  only explicitly authorized test file records; no backfill was requested.
- Schema rollback is supported only while the file registry is empty. Once files
  exist it refuses to discard their references or recreate unavailable DB bytes.

## Interface

| Operation | Contract |
| --- | --- |
| `POST /api/v1/files/uploads` | Only multipart intake. File, purpose and stable operation key. Returns private file metadata after exact-original verification. |
| `GET /api/v1/files/uploads/{operation_key}` | Owner-scoped upload receipt, including an upload with a lost response. |
| `DELETE /api/v1/files/uploads/{file_id}` | Cancel an unbound upload; never deletes another domain's active source. |
| `GET /api/v1/files/{file_id}` | Owner-scoped sanitized metadata. |
| `GET/HEAD /api/v1/files/{file_id}/content?binding_id=...` | Current binding authorization; inline/attachment policy, ranges and streaming. |
| Domain source URLs | Existing chat/Library/calendar URLs remain thin delegates to the same delivery implementation. |
| `FilesService.bind` | Runs in the domain transaction; consumes staged uploads with owner/purpose checks. Explicit server-authorized reuse adds another typed binding. |
| `FilesService.materialize` / `read` | Internal original access after domain authorization, with a read lease, checksum checks and temporary cleanup. |
| `FilesService.release` | Release a typed domain binding in its transaction; GC preserves every surviving reference. |

Public file metadata contains no Cloudinary URL. Domain file association APIs
accept JSON references rather than multipart bytes. Upload receipt caching in
the frontend avoids resending originals when a later association request fails.

## Preservation and performance

- Chat still uploads on Send, keeps local previews and original filenames, and
  allows up to three images per message. Library keeps replacements, old source
  versions, citations, context/archive policy and source viewers.
- Chat → Library and chat → assessment reuse the original asset; they do not
  upload or copy it. Logical quotas remain domain-owned.
- A shared bounded connection pool and streaming proxy provide backpressure,
  HEAD and single ranges. No full-file DB reads, permanent local mirror or
  base64 upload transport. A range-ignorant upstream is sliced while streaming.
- Active downloads have a lease longer than their bounded stream lifetime.
  Disconnects close the upstream connection and release capacity/leases.
- Uploads spool in bounded temporary files, validate their actual type, hash once,
  upload without transformation, and verify the provider original before use.
- Supported text/code/extensionless files use a safe `.txt` provider suffix;
  originals are unchanged and the user always downloads their original filename.
  PDFs/Office/calendar files use their corresponding safe storage suffixes.
- File registry rows embed durable upload/deletion intents, byte reservations,
  retry times and fenced leases. Separate migration/backfill tables and rollout
  stores are intentionally omitted for the authorized empty-data cutover.

## Transient data

Speech originals are private and processor-only, expire after 15 minutes, and
are scheduled for deletion immediately after successful transcription. Failures
may retry within the expiry window. Minimal transcript receipts last 24 hours.
Calendar exports expire after one hour and recheck the event's current revision.
Cloudinary backup retention is separate from application deletion scheduling.

## Verification

`tests/test_files.py` covers receipt replay/conflicts, ownership, bindings,
expiry, cancellation, retryable cleanup, active read leases and authenticated
original/range delivery. Domain and browser tests exercise the consuming flows.

The opt-in `scripts/verify_files_cloudinary.py` checks the real provider through
the Files facade using synthetic originals in a unique Mentra folder and a
verified disposable PostgreSQL schema. It deletes only assets created in that
schema/run. Tests use `testing/files.py`; production has no fallback byte store.

Local acceptance completed on 2026-10-21:

| Check | Result |
| --- | --- |
| Complete backend suite | 817 passed |
| File, speech, assessment and Library workflows in production Python 3.12 image | 71 passed |
| Library, mobile downloads, chat images, assessments, speech and events browser checks | 30 passed |
| Non-root image, private temporary files, offline embedding/speech and real OCR checks | 5 passed |
| Real Cloudinary originals | Source/code, raster images, PDF, Office, WAV and ICS verified byte-for-byte; synthetic assets removed |
| Configured PostgreSQL | Revision `20261020_0028`; three legacy file columns absent; nine assessment attempts preserved |
| Local Compose stack | API/frontend healthy; all four workers running; zero restarts; API readiness and frontend HTTP 200 |
