# Lecture retrieval, latency and retained diagrams — 2026-11-03

The Week 7 lecture response was clear but incomplete, and its retrieval path did unnecessary work. This change adds planner-directed document reads, separates bounded local-model preparation from active search time, removes automatic search retries, and retains embedded diagram files with immutable source provenance. Earlier implementation and benchmark artifacts remain unchanged.

Baseline: `51924b1` (source); deployed application before this change: `ed6197d`. Current embeddings remain multilingual E5. Older BGE benchmark results remain historical evidence and are not relabeled as E5 results. This investigation makes **zero live LLM calls**. Local OCR, scripted model responses and database/vector checks are identified separately below.

## Exact response trace

Trace `969159669a1846a8a0ecc836ca194e39`, generation workflow `266672b32c7f447d839412f7f87249e4`, on 2026-11-03. Structured log evidence was read locally; raw logs, private material bytes and learner identifiers are not copied into this report's evidence directory.

| Observation | Evidence / implication |
| --- | --- |
| Overall `chat.generate` | **106.535 seconds**, rather than an assumed 90 seconds. This is one historical request, not a latency distribution. |
| Model work | Seven serial calls, **16.742 seconds** total; individual durations 2.057, 1.356, 1.203, 1.642, 1.745, 1.240 and 7.500 seconds. |
| Physical RAG work | Eight searches: **19.378, 9.210, 3.456, 10.404, 9.196, 10.342, 9.404, 11.551 seconds**. Some overlapped; do not add them to derive overall time. |
| Reranker | Seven calls: **8.034 seconds cold**, then 0.298, 0.317, 0.285, 0.309, 0.327, 0.339 seconds warm. |
| Timeout/retry interaction | Ten-second outer timeout discarded late successful thread-pool results. Three retries duplicated work while earlier searches continued. A later same-key exhausted request could not recover the missing section. |
| Hidden scope work | STANDARD search called full learner-context retrieval to choose Library scope, then repeated it during reauthorization. Sixteen learner packets occurred in the trace, including the explicit learner tool. Several packets cost about 3.6 seconds. |
| Document summary mismatch | Search returned at most three passages / 1,000 tokens. Summarizing an entire lecture required repeated narrow searches instead of an ordered read. |
| Remaining infrastructure cost | Activity fencing and checkpoint writes also contributed. Their cancellation/write protection is retained; this change does not weaken them to manufacture faster results. |
| Existing prefetch behavior | No Library evidence was fetched before the planner requested a tool. Stale descriptions suggesting otherwise are corrected. Profile/memory preparation and explicit source authorization remain separate from evidence retrieval. |

## Diagram loss and answer assessment

The original PPTX contains 26 slides, eight native tables and four embedded raster images. The published generation contained 46 chunks and 10,703 normalized stored characters. Its four diagrams were picture placeholders (`p:pic`), whose reported shape type is PLACEHOLDER. The old reader handled only PICTURE, silently skipping slides **8, 24, 25 and 26**. Originals remained inside the PPTX; separate diagram files and retrieval associations did not exist.

The old blanket warning about speaker notes/charts/drawing text appeared even though this deck has no charts or nonempty speaker notes. It was not a diagnosis of individual diagrams. The new reader extracts actual notes and emits chart limitations only when charts are present.

| Answer dimension | Assessment |
| --- | --- |
| Teaching | Useful step-by-step explanation, analogy, table and Mermaid, generally readable and relevant. |
| Coverage | Missing checked versus unchecked exceptions, hierarchy, catch ordering/multiple catches, built-in types and the exact source custom-exception example. Diagram OCR recovers material needed for those sections. |
| Java correctness | The answer generalized the `throws` requirement: checked exceptions require declaration or handling; unchecked exceptions can be declared but need not be. See [JLS throws clauses](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.4.6). |
| Flowchart correctness | Routing an uncaught exception straight to the default handler omitted execution of an enclosing `finally` during unwinding. See [JLS try/finally execution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.20.2). |
| Calibration | Labeling a generic custom exception example as a standard pattern was appropriate when source evidence was unavailable. The historical incomplete outcome remains valid; this fix does not rewrite the old answer or hide genuine missing evidence. |

## Implemented contracts and supersession

| Gap | Replacement behavior | Verification |
| --- | --- | --- |
| Cold inference consumes search timeout | Trusted executor preparation hook initializes/restarts the embedding worker and warms the reranker outside active search time. Preparation is bounded at 75 seconds and clamped to the existing turn deadline minus answer reserve. Separate initialization timing is logged. Invalid calls do not initialize models. | Frozen original fails the calibrated regression; fixed path succeeds; global deadline prevents search from starting after preparation exhaustion. |
| Duplicate timeout retries | Library search and ordered reads allow **one physical attempt**, with **20 seconds active execution**, clamped to remaining turn time. Exhausted identical calls return their receipt. Other tools keep their own policies. | Slow-read regression asserts one invocation across timeout and repeat. |
| Topic heuristics hide unknown material | STANDARD Library scope uses owned, nonarchived context summaries. The planner supplies query and optional scope; owner/archive/current-generation checks remain authoritative on every read. No learner recommendation packet runs implicitly. | Unknown-topic lookup spy; ownership/archive/candidate-cache workflow suites; paired real database SQL counts. |
| Whole-document summary via many searches | `find_study_material` finds a ready owned title/filename; `read_study_material` returns an ordered outline and cited body passages with bounded continuation. No embedding/reranking is needed. | Scripted complete planner path, catalog registration and source-read budget checks. |
| Skipped picture placeholders | Recognize actual `p:pic` XML in addition to PICTURE. Preserve slide provenance, OCR text and original raster bytes. | Synthetic placeholder regression and actual four-image lecture comparison. |
| Diagrams only in original archive | Documents emits bounded transient visuals; RAG stores private Files assets and `rag_visual` provenance for owner/document/version/generation/block/page/slide. SHA-256, format, dimensions and limits are checked. Identical raster bytes share one file while retaining all locations. | Upload/read/reindex/superseded citation, integrity, quota and lifecycle regressions. |
| Diagram retrieval | Passage/source references carry server-owned visual IDs. `read_study_visual` accepts only diagrams from already-read passages, reauthorizes them, and adds up to three bounded images to subsequent model input. Provider rejection falls back to cited OCR with an explicit statement that graphical details remain unverified. | Scripted four-round find/read/inspect/finish; fake provider rejection; cached-image reauthorization. |
| Checkpoint bloat / stale authorization | Checkpoints retain diagram IDs, never raster base64. Resume reloads and reauthorizes files. Undelivered read projections roll back visual IDs with source references. | Checkpoint privacy and reauthorization regressions. |
| Source viewer cannot show diagram | Lazy authenticated file delivery beside the associated passage, bounded image rendering and revoked object URLs on teardown. Grouped passages preserve visual associations. Archive/delete mutations invalidate diagram file caches. | Headless browser checks that the image decodes; source status/upload notice regressions retained. |
| Reindex / deletion / storage | Reindex preserves old generation citations and reuses version-owned diagram files; source deletion releases all version bindings. Derived bytes count against Library quota. Upload leases renew for each visual. Migration 0041 refuses downgrade when retained visual rows exist. | File delivery authorization, supersession/deletion, migration upgrade/downgrade/upgrade and Alembic metadata parity. |
| Stale retained extraction | Image manifests cause worker-side rereading of the retained original, keeping base64 out of PostgreSQL extraction records. Old v3 retained extraction is reparsed on new ingestion/reindex so the old missing-image bug is not silently reused. | Reader revision bump to `documents-native-vision-v4`; ingestion workflow checks. |

## Paired measurements, without live LLM calls

Probe: `backend/scripts/study_pipeline_probe.py`, frozen original methods/readers exported from `51924b1`, current reader, same retained lecture and configured database. Only source-read leases are transiently created; no learner answers, source bytes or generations are modified by this comparison.

| Comparison | Before | After | Interpretation |
| --- | --- | --- | --- |
| Scope SQL statements, each of three runs | 14 | 2 | Removes 12 statements per authorization pass, without removing ownership checks. |
| Scope elapsed, first paired run | 3,929.56 / 3,718.76 / 3,681.20 ms | 554.05 / 550.65 / 565.11 ms | About 85% lower in this small remote-database sample; not a production p95 claim. |
| Raw reader blocks | 46 | 50 | Four previously skipped OCR blocks recovered. |
| Raw reader characters | 10,707 | 13,969 | **+3,262 characters**. Raw reader counts differ from normalized persisted counts; do not mix those baselines. |
| Retainable image files | 0 | 4 | Images on slides 8, 24, 25, 26 now have private file/provenance payloads. |
| Upload-time extraction, first paired run | 152.61 ms | 2,119.19 ms | OCR costs more during upload; it is not repeated during ordinary search. This is an intentional completeness tradeoff. |
| Ordered read of original published text | Unavailable | 26 outline sections, 22 body chunks, 2,767 tokens; around 2.1 seconds | Covers the currently published text in one bounded read; diagram coverage is verified after targeted reindex. |
| Ordered-read tool receipt, pre-reindex | Unavailable | 15,172 bytes / 3,793 estimated tokens | Fits existing 25,600-byte / 6,400-token tool-result limits. |
| Scripted planner | Previous search-only path | Find → ordered read → inspect diagram → finish, four scripted rounds, zero semantic searches | Proves wiring and evidence availability, not live model wording, query choices or latency. |

Evidence: [paired comparison](verification/oop-week7-2026-11-03/local-comparison-2.txt), [receipt admission comparison](verification/oop-week7-2026-11-03/local-comparison-3.txt), [calibrated original failure](verification/oop-week7-2026-11-03/calibrated-cold-baseline.txt), [31-test inference/OCR group](verification/oop-week7-2026-11-03/targeted-1.txt), [79-test recovery/reader group](verification/oop-week7-2026-11-03/regression-3.txt). Final cross-check/deployment receipts are linked from the evidence index.

No new live chat was generated, so **no new end-to-end answer time or live answer-quality score is claimed**. The original 106.535-second result and its failures remain historical evidence.

## Bounds and remaining limitations

| Boundary | Current behavior |
| --- | --- |
| OCR | Existing free CPU-local English OCR retained. Equations, handwriting and graphical relationships are not guaranteed accurate. Original images remain inspectable. |
| Raster coverage | Embedded PPTX/DOCX/HTML images, direct raster sources, native PDF embedded images and scanned-PDF page rasters. External HTML image URLs are never fetched. |
| Native Office charts, vector drawings, SmartArt | No Office renderer is introduced. Native text is retained and actual chart limitations are explicit; this change does not claim faithful rendered images of every native drawing. |
| Storage bounds | Up to 32 unique visuals, 8 MiB each, 24 MiB total per extraction, 30 million pixels/image. Additional assets remain in the preserved original with an extraction note. Completely uniform blank scans do not become false diagram evidence. |
| Read bounds | At most 5,000 ordered chunks, 200 outline entries with truncation flag, 64 source chunks per read, 500–5,000 requested text tokens, continuation offset when needed. A passage larger than the requested budget produces a clear budget error. |
| Visual input | Up to three diagrams per response, resized model copies up to 1,600 × 1,600, conservative image-token accounting. Stored originals are preserved. Provider vision availability remains a runtime capability; rejection produces an honest OCR fallback. |
| Broad libraries | Existing scope maximum still applies. Oversized libraries require selected documents/contexts rather than unrestricted scans. Catalog matching is literal title/filename matching; the planner can refine terms or use semantic search. |
| Activity/checkpoint latency | Additional measured cost remains. Changing write/cancellation fencing requires independent correctness and latency evidence; it is not silently bypassed. |

## Rollout and rollback

1. Run the local-only regression groups, browser source tests, frontend production build, static checks, migration roundtrip and metadata parity.
2. Commit the implementation and evidence. Build backend and frontend images labeled with that exact implementation revision; workers share the backend image.
3. Check no active work is interrupted; preserve a new private PostgreSQL custom-format backup under ignored `.cache/rollbacks/`. Do not overwrite earlier backups.
4. Apply additive migration `20261103_0041`, then recreate backend, RAG/assessment/summarizer/events/files workers and frontend; check health/readiness and revision labels.
5. Reindex **only the affected Week 7 document** with the current reader/model configuration. Preserve the prior generation and citations. Verify four visual files, slide OCR, exact vector/chunk identities, delivery authorization and ordered-read receipt admission.
6. Record deployment and targeted repair results in a new evidence receipt. Keep historical audits, failed intermediate runs and prior manifests unchanged.

Rollback application images to the prior known image revision while keeping the additive table. Do not downgrade 0041 after visuals have been stored: its guard intentionally refuses to destroy retained provenance. Stop ingestion before any full database restore; a backup restore also rolls back later user work and is a recovery operation, not routine application rollback. Original Office/PDF files and earlier generations are preserved by this implementation.
