# RAG implementation verification

Verified on 2026-10-08 against the working tree. The end-to-end baseline is implemented, including the authenticated frontend. These checks used dedicated test PostgreSQL/Qdrant services and temporary schemas, databases, collections and volumes. Application migrations and deployment were not performed.

## Results

| Check | Result |
| --- | --- |
| Complete backend unittest suite after shared Documents extraction | 231 passed in 89.502 seconds |
| Complete Chromium production-browser suite | 30 passed, including six RAG workflows, five code/Markdown checks and existing auth/profile regressions |
| Frontend TypeScript and Vite production build | Passed |
| Semantic theme checker | Passed |
| Backend and Nginx frontend Docker images | Built successfully |
| Alembic upgrade/downgrade and metadata drift checks | Passed against isolated PostgreSQL; no new upgrade operations detected |
| Compose configuration and packaged operator CLI | Passed |
| Real embedding, server Qdrant, native extraction and OCR | Passed all eight format fixtures |
| Packaged API, separate worker and built frontend | Passed browser and HTTP runtime checks, including restart recovery |

The backend tests exercise ownership, immutable provenance, idempotency, context policy, archive consent, empty explicit selections, canonical concept tags, token budgets, hybrid retrieval, bounded reranker fallback, durable lease fencing, retries, replacement publication, deletion outages and late-write cleanup. Checkpoint recovery reuses canonical chunks and verified vector points; publication checks expected point IDs and their owner/generation payloads. Old citations resolve their exact published generation. Unpublished cancelled generations cannot expose chunks. Trusted assessment grounding and server-bound read-only LangChain tools are covered independently of ordinary chat.

OCR was subsequently extracted unchanged into the shared [Mentra Vision module](../backend/app/vision/README.md). Twelve additional tests verify tool commands, output, limits, exception behavior, provider substitution, temporary-file cleanup, concurrent request isolation and RAG capability/fingerprint compatibility. [Standalone real OCR results](vision-verification.json) and the real format/runtime checks confirm the extraction preserves the existing pipeline. No frontend behavior changed during this extraction; the browser-suite result above remains the preceding frontend verification.

## Frontend code and Markdown rendering

[Code rendering contracts and visual evidence](code-rendering.md) document shared Prism/React Markdown components for user messages, assistant messages and Library sources. Production-browser checks verify copy/wrap behavior, theme palettes, 320px overflow containment, source metadata, original-fetch reuse, HTML inline code, Markdown documents and continuous source chunks. Chunker identity now includes per-span language metadata; old published sources remain accessible. Backend/frontend Docker images were rebuilt.

## Shared document extraction

[Mentra Documents](../backend/app/documents/README.md) now owns standalone format detection, independent reader engines, extraction isolation and Vision handoff. RAG retains a thin error/capability adapter. PDF/DOCX/PPTX use their existing format libraries; HTML uses Beautiful Soup with explicit inclusion of scripts/styles/templates. Text/code use ordinary UTF-8 reads and preserve their respective previous paragraph or exact source conventions. Identical embedded images share one OCR result per document while retaining occurrence provenance.

Twenty reader tests cover native compatibility, exact coding whitespace, HTML code/comments/templates, deep nesting, Office/HTML image routing, OCR failures, signature checks, limits, provider injection, standalone imports, child cancellation and malformed results. A downstream workflow test ingests and retrieves HTML inline code/styles and Python source. [Standalone real documents results](documents-verification.json) cover 16 fixtures through the default isolated public API, including Office-image, HTML and exact Python/TS/TSX/JS/JSX source cases. Source extensions, aliases and named files are checked for exact text preservation; a browser regression uploads Dockerfile and replaces it with a C++ header. All six RAG browser workflows passed (five existing workflows and the new source-upload regression). Frontend TypeScript/Vite and backend/frontend Docker rebuilds also passed. The new reader fingerprint intentionally distinguishes this added functionality from old ingestion configurations. Published sources remain usable; old pending configurations require a new reindex generation.

## Duplicate-work and correctness review

The follow-up review removed repeated operations while retaining the accuracy checks:

- Library pages use seven SQL queries regardless of the number of returned documents, rather than repeating full detail queries for each material. Regression checks compare complete summaries, including failed replacement history and the still-active generation, and ensure private storage keys remain excluded.
- Qdrant payload indexes initialize once per worker process. Collection/model identity is still validated for each ingestion; failed initialization remains retryable, and a collection created by this adapter resets its index setup state.
- Resume point lookup fetches all expected IDs in groups of 500 rather than performing a request for every 32-chunk embedding batch. Fully indexed batches skip redundant stage updates and empty upserts. Final coverage and expected point-ID/payload checks still run immediately before lease-fenced publication.
- Fitting chunks tokenize once, with per-prefix counts reused when a split is required. Exact ceilings, character preservation and source offsets remain tested. Reranking checks the query budget once and avoids binary truncation when the entire pair fits; oversized pairs still obey the exact budget.
- Valid query-cache hits avoid repeating their budget tokenization; model identity and maximum sequence length are part of the key. Retrieval still reauthorizes its scope and uses persisted canonical chunk counts for its returned token use.
- PDF parsing probes OCR capabilities once per document and reuses each page's image view. Vision validates standalone positive integer page arguments before provider work and avoids repeated tool discovery in capability reporting.
- Concept-focused retrieval restricts eligible material before dense/lexical candidate ranking, so unrelated material cannot crowd matching concepts out. The concept policy is checked again during final reauthorization. Non-finite embedding vectors and invalid reranker score sets fail safely.

The final full suite passed 231 tests. `docker compose build backend` rebuilt `mentra-backend:latest`; the packaged runtime and standalone OCR checks used that actual Compose image. Running application services were not recreated. No schema change was needed for this review.

Browser coverage includes upload, refresh/polling, grounded chat, citation navigation and original download, replacement, archive/unarchive, reindex and deletion. It also checks cross-account isolation, explicit selection after source removal, archive-consent reset in automatic mode, 320px Light/Dark layouts, keyboard dismissal and focus restoration. Final visual review caught inherited Markdown/section spacing on dialogs; source and deletion dialogs now portal outside those content layouts, and a viewport-centering regression assertion passes.

## Real dependencies and packaged runtime

[Real-model results](rag-real-verification.json) record BGE small English v1.5, its resolved revision, 384 dimensions, the optional local cross-encoder revision and parser/OCR versions. TXT, native PDF, DOCX, PPTX, PNG, JPEG, scanned PDF and mixed native/image PDF were ingested and retrieved. The three simple printed OCR fixtures matched their expected text exactly; this does not measure handwriting or general OCR accuracy. Separate native-parser tests cover nested DOCX headings, grouped PowerPoint shapes and short native PDF text without unnecessary OCR.

[Packaged runtime results](rag-runtime-verification.json) use the built backend image without a source-code bind mount, an independent worker process, a private shared volume, real embeddings and a server Qdrant. They verify:

- Upload stays queued while the worker is stopped and publishes when it starts.
- Chat orchestration returns an authorized citation and the exact original bytes.
- API restart preserves the cookie session, source metadata and persisted source bytes.
- Worker restart claims queued reindex work without losing the active source.
- A second authenticated learner receives 404 for another learner's source.
- Deletion excludes access immediately and eventually purges persisted bytes.
- The built Nginx frontend completes registration/onboarding, upload, ready polling, grounded chat, citation viewing, original download and deletion. Refreshing a material-detail URL verifies SPA routing.

The chat provider in these runtime checks is a deterministic local HTTP fixture. It verifies the real provider request/response plumbing and source prompt composition; it is not an answer-quality evaluation of a deployed language model. A [production-build browser screenshot](rag-production-browser.png) records the loaded source viewer.

## Retrieval measurements and limits

The compact comparison has six judged queries over four short sources: five answerable cases and one no-support case. Dense, hybrid and locally reranked retrieval all achieved answerable Recall@3, MRR@3 and nDCG@3 of 1.0, with zero excluded-source violations. This small corpus cannot establish a ranking improvement or a production quality threshold.

| Pipeline | p50 | Observed p95 | Samples |
| --- | ---: | ---: | ---: |
| Dense | 116.67 ms | 128.07 ms | 6 |
| Hybrid | 75.39 ms | 79.53 ms | 6 |
| Hybrid with optional reranker | 118.03 ms | 207.00 ms | 6 |

Measurements include cold-start queries and shared query-embedding cache effects. These are smoke-test measurements on a shared host, not a controlled before/after latency comparison. At six samples, the reported p95 is the largest observed time, not a reliable capacity estimate. Peak process RSS was approximately 678 MiB for the smoke/evaluation process; this is not the combined API/worker/parser deployment memory requirement. All six reranker calls completed within the configured five-second timeout.

The no-support query returned two candidates in each pipeline. Retrieval returns candidates rather than declaring their factual sufficiency; the answer prompt requires support or abstention, but representative real-model answer/abstention calibration remains necessary before claiming answer-quality targets. English OCR, handwriting, equations, multilingual inputs and realistic long-document/load benchmarks also need representative judgments.

## Reproduction

Use an explicitly dedicated `TEST_DATABASE_URL`; tests do not fall back to the application database. From the workspace root in PowerShell:

```powershell
$env:PYTHONPATH = 'backend'
$env:TEST_DATABASE_URL = '<dedicated PostgreSQL test URL>'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
```

From `frontend`, run `npm run test:e2e`, `npm run check:theme` and `npm run build`. The browser fixture uses real authentication and PostgreSQL with deterministic inference and local Qdrant; see `playwright.config.ts` for the dedicated fixture ports.

`backend/testing/rag_real.py` requires a model/OCR-equipped verification image, `TEST_DATABASE_URL` and `TEST_QDRANT_URL`. It uses temporary PostgreSQL schemas and a unique collection. `backend/testing/rag_runtime.py` expects the dedicated `mentra-rag-test-postgres` and `mentra-rag-test-qdrant` containers on ports 15438 and 16335, the `mentra-rag-verify:latest` backend image and `mentra-rag-frontend-verify:latest` frontend image built with `VITE_API_URL=http://127.0.0.1:18401`. Set `RAG_RUNTIME_IMAGE=mentra-backend:latest` to check the Compose image instead. It creates and cleans unique runtime resources and uses ports 18401, 18402 and 15174. Run it with `python -m testing.rag_runtime`; Playwright must be installed in `frontend`.

## Release boundaries

See [RAG setup and contracts](rag.md) for configuration, API contracts, quota/retention behavior, backup, recovery and operator rebuild commands. The implementation plan retains the mapping to all 40 original phases and identifies measured or conditional work separately.

The baseline includes hybrid retrieval and an optional, tested local reranker. Fine-tuning, sparse-vector migration, query expansion and zero-downtime dual-model routing remain conditional improvements. Model/schema changes currently require a new collection and a maintenance-window rebuild with rollback backups. They are not silently treated as normal reindex jobs. No production-corpus quality result, live-provider answer-quality result or application rollout is claimed by this verification.
