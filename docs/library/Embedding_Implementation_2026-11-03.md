# Embedding pipeline implementation — 3 November 2026

This ledger follows the [2 November audit](Embedding_Pipeline_Audit_and_Improvement_Plan_2026-11-02.md). Historical reports, probes and their original manifest remain unchanged. The previous operational guide is retained in [history](history/rag-contracts-before-2026-11-03.md). This is working-tree implementation and isolated runtime evidence, not an application deployment record.

## Implemented replacements

| Findings | Previous behavior → replacement | Reindex / rollback |
| --- | --- | --- |
| F01 | Reranking discarded every candidate after its cap → prefilter individually oversized and duplicate passages, cap per-document candidates before scoring, preserve the original tail. Reranked and tail scores retain separate types and are never numerically mixed. | No reindex. Revert selection change or disable optional reranker. |
| F02 | OCR/extraction warnings stayed only in server provenance → new and repeated chat tool receipts include source-specific warnings. | No reindex; preserve warning delivery when rolling back other changes. |
| F04 | Usage write failure aborted retrieval → best-effort metadata write after mandatory authorization, also used by original-source fetching. | No reindex; authorization and binding failures still propagate. |
| F05, F06 | Silent prefix scoring and opaque unavailable result → explicit truncation count/warning, fallback reason, missing-asset preflight and five-second cooldown after unavailable worker/assets. Invalid score counts/NaNs fall back. | No reindex. Prefix policy remains unchanged pending quality experiments; query-budget errors are disclosed as fallback. |
| F07 | Lease only checked parser duration; unbounded expired reclaim → configuration also covers embedding startup/inference/wait/cleanup, point verification renews between 500-ID batches, three exhausted attempts become terminal failure. | No schema migration. Deliberate retry resets attempts; purge reconciliation retains its existing retry policy. |
| F12 | Capabilities claimed English retrieval only → explicit multilingual/no-input-allowlist policy and embedding model; OCR languages remain independently reported by Documents. | No reindex. Empty legacy `languages` list is non-exhaustive; clients must not infer an allowlist. |
| F13 | Build selected moving model HEAD → optional explicit revision inputs supported by baking scripts, pinned defaults in Compose build arguments and `.env.example`, runtime embedding/reranker revision validation when configured. | Existing images remain usable when runtime pins are empty. Changing model names requires changing matching revisions. Encoder identity changes need planned collection migration. |
| F14 | Static pipeline identity and opaque packing/fallback → v2 pipeline marker, embedding identity, actual reranked/truncated counts, fallback reason, dependency health and packing rejection counts. Empty scope records total elapsed time. Empty degraded retrieval remains degraded. | Additive API diagnostics; no reindex. |
| F15 | Test expected preparation to create old 8/6 budget field → assert preparation delegates to coordinator; existing adaptive coordinator budget tests also executed. | Historical failing audit log retained; no old budget policy restored. |
| F16 | Current guide mixed old model/storage/routes with current contracts → corrected guide, previous guide snapshot, explicit legacy filter documentation. | Compatibility functions and tests remain available. Historical model names/results remain intact. |
| F17 | Hardcoded 80/80 candidates → bounded configurable dense/lexical limits with limits included in candidate-cache identity; live identity checks preserved. | Defaults unchanged. Settings flow through API and worker Compose environments. |
| F18 | A 1,000-row cap could present a truncated semantic memory corpus as complete → fetch 1,001 and defer on overflow, preserving conservative memory admission. | No vector/model-key change; memory domain behavior otherwise unchanged. |
| F19 | Recovery blindly concatenated old chunks → verify single-span mapping, contiguous coverage, exact overlap equality and content lengths; reject unsupported multi-span/gapped reconstruction. Missing safe retained extraction becomes a permanent, actionable extraction error. | Old source versions and canonical generations remain intact. Future chunker changes must supply reversible mappings before promotion. |
| F20 | Implicit token-budget interpretation → document embedding-token versus model-context budget, preserve final ToolBudget authority and exercise receipt/adaptive-budget regressions. | No reindex. |

## Evidence and comparisons

All model execution was local with outbound Hugging Face/Transformers access disabled. No live LLM calls were made. PostgreSQL used the disposable `mentra-embedding-audit-db` database; Qdrant used a disposable server and temporary collection. Application containers, databases, collections and original uploads were not used. Current source was mounted read-only into the cached backend image; this validates current source with existing packaged dependencies/assets, not a newly built release image.

| Check | Recorded evidence |
| --- | --- |
| Initial local regression suites | [58 passed](verification/embedding-implementation-2026-11-02-tests.txt) before later additive changes. |
| Chat delivery, prefetch, adaptive budget/finalization | [25 passed](verification/embedding-implementation-2026-11-02-consumer-tests.txt), including the corrected budget test and repeated-source warnings. |
| Latest local adapter/selection/reranker/process contracts | [25 passed](verification/embedding-implementation-2026-11-03-contract-tests.txt). |
| Dedicated PostgreSQL shared-memory, lease-exhaustion, retained-source recovery and selection checks | [8 passed](verification/embedding-implementation-2026-11-03-final-checks.txt). |
| Complete isolated RAG suite | [63 passed, one old-contract assertion failed](verification/embedding-implementation-2026-11-03-integration-tests.txt), 239.206 seconds. It expected a scoring cap to discard the tail. The replacement assertion verifies two reranker scores plus one typed RRF tail result. [Targeted retry: five passed](verification/embedding-implementation-2026-11-03-tail-regression.txt), 8.589 seconds. Counts from separate runs overlap and must not be added as unique tests. |
| Real multilingual E5 + reranker | [27/27 direct and pipeline cases](verification/embedding-implementation-2026-11-03-real-reranker.json), worker reuse and fallback passed. Recorded cold 12.5726 seconds; warm maximum 0.1207 seconds. |
| Real server comparison: formats + dense/hybrid/reranked | [Structured report](verification/embedding-implementation-2026-11-03-comparison.json), [raw output](verification/embedding-implementation-2026-11-03-comparison.txt). |

Candidate caches and query vectors are cleared for every measured request in the revised comparison harness. Each variant records 30 warm samples separately from its first request, actual nearest-rank p95 and raw samples. Parent RSS is labelled as parent RSS rather than total model memory. The old sequential/cached benchmark output is preserved.

| Pipeline | Answerable Recall@3 / MRR / nDCG | Warm p50 / p95 | No-support query returned candidates |
| --- | --- | --- | --- |
| E5 dense | 1.0 / 1.0 / 1.0 | 64.04 / 80.13 ms | Yes |
| E5 + lexical RRF | 1.0 / 1.0 / 1.0 | 83.375 / 101.12 ms | Yes |
| E5 + lexical RRF + multilingual reranker | 1.0 / 1.0 / 1.0 | 124.9 / 191.52 ms | Yes |

These six questions/four judged sources are a smoke comparison. They establish no ranking gain and do not justify a relevance threshold. Easy format fixtures also do not establish general OCR quality. The adversarial selection fixtures now retain baseline viable counts (8, 5 and 4); original failing counts (4, 1 and 0) remain in the audit JSON.

The first Docker test attempt omitted production thread limits, ran slowly and was interrupted. Its [partial log](verification/embedding-implementation-2026-11-02-integration-tests.txt) is retained; it is not counted as a passing suite. The retry uses `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`. Windows asyncio tests ran outside the filesystem sandbox to permit local loopback sockets.

## Research gates still open

The plan explicitly makes these changes conditional on measured held-out improvements. They have **not** been implemented or silently enabled:

| Findings | Remaining gate |
| --- | --- |
| F03 | Representative >=200-query, >=50-source, source/course-separated judged corpus; support-span labels, language slices and paired uncertainty estimates. The new real comparison repairs cache/latency methodology but remains a smoke corpus. |
| F05 | Passage-window versus prefix/shorter-chunk quality experiment, with bounded CPU cost. Truncation is now visible; late-support quality remains an open limitation. |
| F06 | Dedicated warmup policy and representative concurrent load/deadline measurements. Cooldown and reason reporting are implemented. |
| F08 | Calibrated support/abstention policy with false-abstention constraints. Current comparison confirms the no-support limitation; no guessed cutoff added. |
| F09 | Identifier/phrase/language-aware lexical alternatives and PostgreSQL EXPLAIN under realistic data. Current OR/simple FTS preserved. |
| F10, F11 | Chunk packing/overlap/heading and tokenizer-IPC ablations, exact multi-span recovery and measured throughput/quality gain. Current block-v2 chunk identity preserved. |
| F13 | Full artifact checksum/dependency/pooling manifest and newly built image reproducibility test. Revision pins and runtime checks are implemented. |
| F17 | Corpus-size/concurrency/RSS/hydration matrix before changing identity RPC policy or broad-scope retrieval design. |
| F18 | Token-aware poison-item/backfill diagnostics and >32/>1,000-memory load tests. Overflow now safely defers; no partially complete lookup is admitted. |
| Rollout | New image build, application canary, production SLO selection and rollback exercise remain deployment work. No application deployment was requested or performed in this increment. |

Thus the entire research roadmap is not marked complete. Safe fixes and a real offline verification path are implemented; experimental policy changes remain gated by the evidence the plan requires.

## Reproduction, preservation and rollback

Use the PowerShell setup from the audit for local tests. The new regression module is `backend.tests.rag.test_selection_regressions`. Database tests require a dedicated `TEST_DATABASE_URL`. In the cached backend image, set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`, `PYTHONPATH=/repo/backend`; mount the repository read-only at `/repo` and a separate evidence output path writable. For the multilingual suite set `TEST_EMBEDDING_PATH=/opt/mentra/models/embedding`, `TEST_RERANKER_PATH=/opt/mentra/models/reranker`, and `RERANKER_TEST_REPORT` to a new report filename. For the real comparison additionally set `TEST_QDRANT_URL` to the disposable Qdrant server, enable the baked `RAG_RERANKER_PATH`, then run `python -m testing.rag_real`.

No schema or embedding reset is required for this increment. Restore previous code/config for rollback; retain source generations, originals and model identity. Do not change an encoder revision against an incompatible collection. Snapshot the existing deployment before a later rollout and record its image digest/config/collection identity. Compatibility exports stay present; documentation history is additive. The unrelated pre-existing observability investigation is outside this work.
