# RAG setup and contracts

The Library and chat workflow is implemented. Upload owned material into a learning context, wait for the durable worker, select automatic or explicit sources in chat, and open/download cited passages. Replacement, reindex, context reassignment, archive/unarchive and deletion operate on the same canonical records. Chat history and citation snapshots are persisted by Chat; source access rechecks ownership and lifecycle.

## Runtime and startup

Use the existing PostgreSQL URL and remote Qdrant configuration. The API and `rag-worker` use the same backend image and shared authenticated Cloudinary originals through Files. Set the normal chat provider variables for answers. Originals live in Cloudinary; parsing, English OCR and embeddings run locally; vectors and filter IDs go to Qdrant, and only selected excerpts go to the configured chat provider.

```bash
docker compose up -d --build --force-recreate
```

The backend command applies Alembic migrations before starting the API; the worker waits for backend startup. Migration `20261008_0004` adds RAG records. Apply `20261103_0039` before starting the updated backend: it repairs the lexical GIN expression index concurrently without changing canonical rows or vectors. Implementation verification used isolated databases; it did not apply migrations to the application database or deploy the application stack. Back up PostgreSQL and retain the matching Cloudinary originals and Files bindings before rollout. Restore matching metadata and originals to preserve source references. Qdrant is a derived index and can be rebuilt from retained sources.

Defaults are 25 MiB per upload, 512 MiB of retained source bytes per learner, 200 PDF pages/slides, 5,000 chunks, 5 million extracted characters, a 120-second parser timeout and a 300-second renewable job lease. The lease must exceed the parser timeout. Parsing runs in a killable process group with Linux memory/CPU limits; publication batches contain at most 32 chunks; native embedding requests are further bounded to 4,096 counted tokens. Chunking runs beside the tokenizer in the reusable embedding process. Compose limits inference threads to two per process. API and worker each load their own embedding model; allow RAM for both and for parser children. One ingestion is admitted per learner at a time. Quota includes older versions and bytes awaiting deletion cleanup.

Configure limits through `.env.example`. New model assets are baked into the image, never downloaded at runtime. Liveness remains `/api/v1/health`; `/api/v1/health/ready` checks configured inference and Qdrant identity. The operator health command additionally checks canonical generation coverage and pending/cleanup lag.

## Extraction and provenance

The capability API advertises installed formats. The Docker image supports TXT, PDF, DOCX, PPTX, PNG/JPG, HTML and common coding/data files. Legacy DOC/PPT and password-protected PDFs are rejected. A thin RAG adapter delegates to [Mentra Documents](../../backend/app/documents/README.md), which owns native reading, routing, warnings and provenance. Text PDFs retain native layout text; scanned pages use [Mentra Vision](../../backend/app/vision/README.md), and mixed pages retain native text plus embedded-image OCR. DOCX paragraphs/headings/tables and PPTX slides/text/tables retain locations; body/table DOCX images and grouped PPTX pictures also use Vision. HTML includes inline scripts/styles and embedded-image OCR without executing scripts or fetching references. Coding files retain source whitespace. Headers/footers/comments, speaker notes, charts and some drawing content remain incomplete and produce warnings. OCR is English; equations, handwriting and reading order require source verification.

Chunks preserve normalized text, indentation, heading/page/slide spans and exact normalized character offsets. Token counts use the active tokenizer; query prefix budgets belong to the embedding adapter. Sources have immutable upload/version and generation IDs. Old published citation generations remain accessible under ownership/archive policy after replacement or reindex. Superseded vectors are cleaned; retained canonical chunks and original versions support old citations until deletion. Retained source versions count against quota and are not silently expired.

## Authenticated APIs

All routes below are under `/api/v1`, require an authenticated onboarded identity and bind the internal learner UUID server-side. Cookie mutations require the existing trusted browser Origin. No endpoint accepts a caller-selected owner.

| Route | Behavior |
| --- | --- |
| `GET/POST /learning-contexts` | List owned contexts with offset/limit/status filters; resolve/create a context, with explicit activation. |
| `PATCH /learning-contexts/{id}` | Explicit lifecycle transition; making a context current uses exclusive Learner activation. |
| `GET /rag/capabilities` | Installed extraction formats, effective upload limits, parser revision and retrieval features. |
| `GET/POST /documents` | Paginated archive/context-filtered Library list; create from an owned Files upload ID with context IDs and idempotency key, returning 202. |
| `GET/PATCH/DELETE /documents/{id}` | Detail; revision-checked title/context/archive edit; immediate deletion tombstone plus durable purge, returning 202. |
| `GET/POST /documents/{id}/versions` | Paginated retained version history; replacement from an owned Files upload ID with expected revision and idempotency key. |
| `POST /documents/{id}/reindex` | Revision-checked rebuild into a new generation from retained bytes. |
| `POST /documents/{id}/concepts` | Resolve labels through Learner; only known canonical concepts are attached, unknown labels are reported. |
| `GET /rag/jobs/{id}` / `POST .../retry` | Owned stage/state/error and deliberate failed-job retry. |
| `POST /rag/search` | Bounded typed query, source/context/concept scope, budget, ranks and diagnostics. |
| `GET /rag/chunks/{id}` | Owned canonical published passage with source/lifecycle checks. |
| `GET /documents/{id}/versions/{version}/source` | Private authenticated original download, without cacheable public URLs. |
| `GET .../chunks` | Paginated canonical source passages; optional exact generation binds old citations. |
| `POST /chat` | Deprecated stateless compatibility endpoint with role/content and source selection; persistent clients use `/conversations/turns`. |

`STANDARD` delegates relevance to Learner, including intentionally query-matched dormant knowledge. `SOURCE_SPECIFIC` and `CROSS_CONTEXT` validate every requested identity and never broaden an empty selection. Archived use requires explicit consent plus a document/context scope. `CONCEPT_FOCUSED` searches canonical tags; untagged material is not implicitly excluded in ordinary chat. Context reassignment takes effect immediately because Qdrant is filtered by exact authoritative active generation IDs, rather than relying on stale context payloads.

The internal `search_assessment` contract takes server-approved study document IDs and reuses these checks. It is not an ordinary HTTP/chat mode and does not invent an assessment workflow. `create_rag_tools` binds identity/selection/consent in server orchestration; models can request passages but cannot choose an owner or expand their source scope. Chunk tools only resolve passages returned within that workflow and recheck lifecycle on access.

Persistent chat may prefetch to warm the revision-aware candidate cache. Passages,
citations and prefetch failures remain private until the agent requests
`search_study_material`; delivery rechecks current ownership and source eligibility.
General questions can answer directly without retrieval. Selected study materials
clear after one successful response. Optional failures go to the agent rather
than a deterministic Response limitations banner. See [cache policy](../orchestration/Tool_Cache_Policy.md).

Dense candidates and PostgreSQL full-text candidates share the same owner/generation scope and use deterministic RRF. Full-text ranking is not BM25. Canonical hydration and a final policy recheck establish eligibility. Whole chunks are packed under a tokenizer budget with duplicate/per-document limits. Source markers such as `[[S1]]` become buttons only when allowlisted by the server. Consulted sources remain distinct from cited claims; returned passages alone do not prove answer support.

## Optional reranking

To provision a local cross-encoder, set a build-time model and runtime directory:

```dotenv
RAG_RERANKER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
RAG_RERANKER_PATH=/opt/mentra/models/reranker
RAG_RERANKER_TIMEOUT=5
```

Rebuild the backend image. A locally baked metadata file records its resolved revision. At most 40 eligible candidates and one worker task are reranked. Oversized query/passage pairs use up to four exact windows; incomplete coverage falls back explicitly. The default candidate cap remains 20. Scored window offsets are relative to the returned canonical chunk and do not replace source provenance. Timeout/unavailable assets return the original scoped ranking with a degraded warning. Reranking stays disabled by default until a representative corpus shows a useful gain. The [model card](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1) describes its passage-ranking purpose; Mentra's CPU behavior is measured separately in the verification report.

## Recovery and operator commands

Jobs use PostgreSQL `SKIP LOCKED`, renewable fencing tokens and bounded dependency retries. Process restart claims queued or expired jobs. Complete canonical chunks are reused under an identical configuration fingerprint; verified existing generation points avoid repeated embedding. Publication requires the expected point IDs, count, owner/generation payloads, current document revision and live lease. A failed replacement retains the working generation.

Deletion excludes all retrieval/source access immediately, cancels ingest jobs and queues removal of vectors and private bytes. Failed purge dependencies are retried by reconciliation. A bounded rotating sweep repeats cleanup of old failed/superseded/deleted generations after a full lease/parser window, including late writes from cancelled workers. Orphan blob cleanup belongs to the storage adapter. Minimal tombstone/version/job identifiers remain to preserve references and idempotency; source content, filenames, hashes and titles are purged/sanitized.

Run operator commands in the backend image so parser/model identity matches the running workers:

```bash
python -m scripts.rag_admin health
python -m scripts.rag_admin health --learner-id <internal-UUID>
python -m scripts.rag_admin rebuild --learner-id <internal-UUID> --run-id <run-UUID>
python -m scripts.rag_admin rebuild --learner-id <internal-UUID> --run-id <run-UUID> --apply
```

Rebuild defaults to dry-run and records resumable per-document jobs. Reuse the run UUID for idempotency. Health reports a bounded coverage sample (up to 100 generations) and the total corpus count; it does not expose source text. No global admin HTTP route exists. Query diagnostics record timing/counts/ranks and cache hits without raw queries or excerpts. Bounded owner-keyed query vectors and revision-scoped candidate IDs/scores are cached. Source content is hydrated and reauthorized on every hit; responses are never served from a stale content cache.

Keep the current collection/model identity during normal rebuilds. An encoder/vector-collection schema upgrade requires a new collection and a maintenance-window reindex, with retained old source/index backups for rollback. Automatic mixed-model reuse and destructive collection recreation are rejected. A zero-downtime dual-encoder routing/cutover system is not part of this baseline. Fine-tuning, sparse Qdrant migrations and query expansion remain conditional experiments; the source-judgment comparison harness accepts their rankings without adding training dependencies to production.

## Material search and practice entry

The document listing accepts a bounded `query` (up to 200 characters), matched
literally against title/filename without case sensitivity, alongside owner,
context/archive filters and server pagination. The assessment material picker
preserves selected IDs across pages/searches and hydrates preselected material
through owned detail reads. Grounding still goes through the RAG service.

**Quiz this material** prepares the existing creation form with the material,
context and three-MCQ preset; generating remains explicit. Citation readers first
fetch the authorized chunk and validate document/version/generation identity,
then offer full-source browsing. PDF page targeting is a browser-viewer hint.


## Unified files â€” 20 October 2026

Original uploads now use the shared [Files module](../../backend/app/files/README.md). Configure the server-only `CLOUDINARY_URL`; all assets live under `mentra/<APP_ENV>/`. Run `python -m app.files.worker` for expiry/reconciliation/deletion. No persistent materials volume is required. Upload UI, source filenames, Library version history and authenticated previews/downloads remain unchanged.

## Retrieval hardening — 3 November 2026

The [completion and acceptance record](Embedding_Completion_2026-11-03.md) records fixes and measured verification. The [previous guide](history/rag-contracts-before-2026-11-03.md) is retained as history. Candidate limits default to 80 per branch and are configurable through `RAG_DENSE_CANDIDATES` and `RAG_LEXICAL_CANDIDATES`. Reranking filters individually oversized/duplicate passages before scoring and retains a separately typed original-ranking tail for filling. Optional usage metadata writes cannot abort search. Source extraction warnings travel with new and repeated chat receipts. Diagnostics distinguish reranker fallback reasons and prefix-only passage scoring. Embedding token counts are not chat-model context counts.

Pin `EMBEDDING_MODEL_REVISION` and `RAG_RERANKER_MODEL_REVISION` when building. When selecting another model, change its revision too. Revision pins identify the exact artifact; embedding identity changes require a planned rebuild/cutover. Reranker-only changes do not require embedding reindexing.

### Completed runtime policies

Automatic scope is bounded by `RAG_MAX_SCOPE_DOCUMENTS` (default 1,000, configurable up to 10,000). Larger scopes return `RAG_SCOPE_TOO_LARGE` before inference; select explicit documents or narrower contexts. Sources are retained, and results are never silently truncated to manufacture an incomplete successful search.

`RAG_LEXICAL_POLICY=simple` retains multilingual literal matching and its repaired GIN index. The optional `structured` policy boosts exact quoted/punctuated identifiers; it is not enabled by default. `RAG_RERANKER_WARM_ON_STARTUP=false` keeps startup warmup opt-in; ingestion-only workers skip warmup. `RAG_MIN_RERANKER_SCORE` is empty by default. Enabling it requires an active, revision-pinned reranker and corpus-specific calibration; it excludes unscored tails and never treats mixed score types as confidence probabilities. The synthetic calibration rejected a universal threshold.

Pipeline v3 reports thread-isolated reranker diagnostics and winning character windows. Reranker timeouts cover pipe submission and receipt as well as inference; model failures use bounded cooldown. New model builds include checksums, runtime package versions, pooling configuration and role policy. Legacy baked assets without manifests remain compatible; new pinned builds verify manifests before loading. Full historical guides and test reports remain preserved.
