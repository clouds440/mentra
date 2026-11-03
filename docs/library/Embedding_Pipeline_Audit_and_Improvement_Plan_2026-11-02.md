# Embedding, retrieval and reranking audit — 2 November 2026

**Status: researched plan; production fixes are not implemented.** Audited source baseline: `444e6bb90ad1d9e270c3191ac5002983540b160b`. This change adds audit documentation and offline evidence only. No live LLM calls, model downloads, application database changes, reindex, collection reset or deployment were performed.

The strongest immediate finding is candidate starvation introduced by reranking. The infrastructure already protects ownership, active generations, model identity and resumable publication; retain those protections. Fix selection, warning delivery, reliability and evidence quality before changing embedding models or adopting more infrastructure.

This document extends the [historical implementation plan](Mentra_RAG_System_Implementation_Plan.md), [contracts](rag.md) and [verification history](rag-verification.md). It does not overwrite earlier evidence or claim an older implementation is still current. The current contracts themselves contain drift listed below. Changes must carry a before/after evidence record and a supersession entry.

## 1. Scope and current execution path

| Stage | Current implementation and observed contract | Audit implications |
| --- | --- | --- |
| Intake | Files owns private originals; `RAGService.accept_upload` binds owned file metadata, context, idempotency key and revision. `accept_extracted` reuses an internal Documents snapshot. | Preserve originals, version IDs, canonical text, ownership and extraction warnings. Do not reintroduce volume-based storage. |
| Extraction | `documents/service.py`, format readers and Vision; isolated parsing with process deadlines. Native text/code/Office/HTML and English OCR feed blocks. | Multilingual embeddings cannot recover text omitted by English-only OCR. Per-format warnings are part of evidence. |
| Chunking | `rag/processing.py:chunk_blocks`; independent blocks, no merging/overlap, ceiling `min(450, max_tokens-2)`, exact tokenizer checks, deterministic generation UUIDs and normalized offsets. | A deliberate conservative baseline, but small paragraphs create many tiny chunks; boundary context and title/heading relevance need evaluation. |
| Embedding | `SentenceTransformerEmbeddingService`; E5 roles centralized; query/passages and symmetric query/query; normalized vectors, dimension/count/finite checks and local model identity. | Current E5 contract is correct in focused tests. Do not add prefixes in callers or impose a language allowlist. |
| Process isolation | `ProcessEmbeddingService`; spawned reusable process, one lock, 32-text requests, separate initialization/inference timeouts and restart identity check. | Tokenization shares the same serialized worker; repeated tiny IPC calls and request-wide deadlines deserve measurement. |
| Durable indexing | `IngestionWorker`; lease-fenced stages, reuse canonical chunks, skip known point IDs, upsert, count/ID verification, revision-checked publication. | Preserve old active generation on replacement failure. Verify edge cases around leases, identity changes and recovery. |
| Vector storage | `QdrantVectorStore`; unnamed vectors, model/revision/dimension marker, owner/record-type/generation filters and payload indexes. | Equal-dimensional old BGE vectors are rejected. Canonical PostgreSQL data, not Qdrant payload text, remains authoritative. |
| Scope and retrieval | `RAGService.search`; Learner context selection or explicit scope, canonical concepts, 80 dense and 80 lexical candidates, RRF, owner-scoped hydration. | No quality threshold; fixed candidate limits and lexical policy require representative comparisons. |
| Caches | Query vectors: 128/60 seconds; candidates: 128/120 seconds with owner, model/config, scope and active generation/revision signature. | Candidate hits still hydrate and reauthorize. Query normalization preserves case/code/operators; no case-folding bug found. |
| Reranking | Optional CPU `mmarco-mMiniLMv2-L12-H384-v1`, local assets, default 20/max 40 candidates, pair limit 512, query limit 240, single nonblocking lock, cold allowance at least 30 seconds. | Prefix clipping, saturation fallback, cold latency and candidate starvation are separate issues. |
| Packing and fetching | Hash deduplication, four chunks per document, whole chunks under E5 token budget, final scope/generation recheck, usage write, source/version/generation IDs. | Reranking currently removes the tail before packing. Usage write is an unnecessary hard dependency. |
| Consumers | HTTP search, document search, assessment grounding, chat workflow tools and source-view routes. Chat tool requests three chunks/1,000 embedding tokens. | Source warnings do not all survive the chat projection. Model context budgets must remain separate from embedding token counts. |
| Other embedding consumer | `history_management/memory/semantic.py` uses symmetric embeddings, PostgreSQL vectors, revision/model keys, local similarity and conservative deferral. | Any shared adapter change needs memory regression coverage too; this is not a second Qdrant pipeline. |

Primary source paths above are under `backend/app/`. Important boundaries: [service](../../backend/app/rag/service.py), [worker](../../backend/app/rag/worker.py), [repository](../../backend/app/rag/repositories/postgres.py), [embedding adapter](../../backend/app/rag/embeddings.py), [process](../../backend/app/rag/embedding_process.py), [reranker](../../backend/app/rag/reranker.py), [Qdrant](../../backend/app/rag/qdrant_store.py), [chat projection](../../backend/app/langchain/workflow_tools.py).

## 2. Evidence from this audit

All new comparisons below ran without live LLM calls. Mock-model tests verify contracts and control flow; they do not measure semantic model quality. No current real-model quality, server Qdrant latency, PostgreSQL query plan or production load result is claimed.

The [evidence manifest](verification/embedding-audit-2026-11-02-manifest.json) records the source baseline, Python version, test totals and SHA-256 hashes of the ten raw logs/probe artifacts. Logs retain unsuccessful attempts rather than presenting only green results.

| Executed check | Result | Evidence |
| --- | --- | --- |
| Processing, index initialization, embedding adapter and Qdrant contract suites | **24 passed**, 1.134 seconds | [Core test log](verification/embedding-audit-2026-11-02-core-tests.txt) |
| Shared document readers and RAG parser structure | **23 passed**, 6.483 seconds | [Reader log](verification/embedding-audit-2026-11-02-reader-tests.txt) |
| Complete mocked reranker/bake suite | **8 passed**, 11.510 seconds | [Reranker log](verification/embedding-audit-2026-11-02-full-reranker-tests.txt) |
| Embedding and reranker native timeout/restart tests | **2 passed**, 3.782 seconds; one overlaps the complete reranker suite | [Process log](verification/embedding-audit-2026-11-02-process-tests.txt) |
| Chat refinement and prefetch suites | **8 passed, 1 error**, 4.328 seconds | [Consumer retry log](verification/embedding-audit-2026-11-02-consumer-retry-tests.txt) |
| Dedicated database preflight using a workflow test | **Blocked/error in setup**, missing `TEST_DATABASE_URL`; no assertion executed | [DB preflight](verification/embedding-audit-2026-11-02-db-preflight.txt) |
| New adversarial selection, clipping, usage-write and tokenizer-call probes | Completed against production functions with fake dependencies | [Reproducible script](verification/embedding-audit-2026-11-02-probes.py), [JSON](verification/embedding-audit-2026-11-02-probes.json) |

Deduplicated completed test accounting: **64 passed, 1 errored** across the listed executable suites, plus one blocked database setup. The four-test reranker subset is retained as an intermediate run, not added again. Initially Windows temporary-directory permissions caused embedding fixture errors; redirecting TEMP/TMP to the ignored workspace `.tmp/embedding-audit` resolved them. An initial consumer attempt stalled in Windows asyncio's loopback socket setup, confirmed by the [20-second traceback](verification/embedding-audit-2026-11-02-consumer-tests.txt). Its bounded retry outside that sandbox restriction reached the actual assertions. Two earlier broad attempts were interrupted and are not counted as completed tests.

Docker Desktop's Linux engine was unavailable. There was no dedicated PostgreSQL test URL. Real baked model assets/server-backed evaluation was not executed. These limitations are pending verification gates, not passing or failing retrieval quality results.

### Controlled selection comparison

Each case supplies the same 30 ordered candidates: 20 from document A, 10 from B. The fake reranker preserves the supplied order, isolating selection behavior from model quality. Production `RAGService.search` performs hydration, reranker truncation, deduplication and packing; scope/database/model dependencies are synthetic. Requested limit is eight.

| Case | Dense selection | Reranked selection | What the comparison establishes |
| --- | --- | --- | --- |
| Four-per-document cap | 8 chunks, A+B | 4 chunks, A only | Tail loss prevents filling from a second document. |
| First 20 candidates share content hash | 5 chunks, A+B | 1 chunk, A only | Duplicate candidates consume the entire reranker allowance before deduplication. |
| First 20 cost 450 tokens; budget 100; later candidates cost 10 | 4 chunks from B | 0, `no_matches` | Enabling reranking can manufacture an empty result even though fitting candidates were retrieved and hydrated. |
| Usage metadata write throws | Exception | Exception | Useful authorized results are discarded if `record_usage` fails. |

Additional deterministic probes: a 514-character synthetic passage was clipped to 504 and lost its answer suffix; a synthetic 241-token query triggered the reranker's 240-token rejection; 100 three-word blocks became 100 chunks; a 50,000-character block required 287 tokenizer calls for 23 chunks while retaining all 50,000 characters. These are character/word-count fake tokenizers, explicitly **not measured E5 tokenization, latency or relevance**.

### Historical comparisons, preserved rather than reinterpreted

| Recorded experiment | Recorded result | Limits and disposition |
| --- | --- | --- |
| [BGE + older English reranker, six queries/four sources](verification/rag-real-verification.json) | Dense/hybrid/reranked all answerable Recall@3, MRR and nDCG 1.0. p50 116.67/75.39/118.03 ms. One no-support query returned sources in all three. | Historical baseline only. Cannot establish current E5 speed or reranker lift. Keep original model identities and results unchanged. |
| [E5 multilingual smoke](verification/e5-multilingual-verification.json) | 27/27 top-1 cases, E5 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. | Small language-pair smoke, not a representative benchmark. |
| [Multilingual reranker smoke](verification/reranker-real-verification.json) | 27/27 direct reranker and pipeline cases; cold 6.8831 seconds, maximum warm 0.0477 seconds. | Recorded, not rerun. Tiny passages/candidate sets do not predict 20–40 long candidates or concurrency. |

The verification narrative already labels the old BGE report historical; **that label is not missing**. The remaining gap is the absence of a current, representative E5 dense-versus-hybrid-versus-reranked comparison, plus stale operational examples elsewhere. The six-case harness also runs variants sequentially on one service: hybrid can reuse dense query vectors; reranked can reuse hybrid candidates. It labels the maximum of six samples `p95`. These numbers are not a fair uncached A/B latency comparison.

## 3. Findings and fixes

Evidence labels: **reproduced** = executed this audit; **source-confirmed** = direct code path, not a live incident; **risk/experiment** = requires the stated further measurement. P1 means fix before treating the affected behavior as reliable; P2 means reliability/quality follow-up; P3 means conditional optimization. No P0 security breach was established.

| ID / priority | Finding and evidence | Proposed change and acceptance |
| --- | --- | --- |
| F01 / P1 | **Reranker candidate starvation — reproduced.** `service.py:337–355` replaces the entire ranking with the first capped subset before hash/document/budget checks. | Build a viable, deduplicated, document-diverse pool before expensive scoring; retain a separate ordered tail for filling. Never mix raw RRF and reranker scores in one numeric sort. Prefer reranked tier, then explicitly typed fallback tier, or bounded extra rerank batches. All three selection regressions must retain viable coverage; preserve owner/concept/generation checks. |
| F02 / P1 | **Source warnings disappear on chat delivery — source-confirmed.** `SourceReference.warnings` contains OCR/extraction warnings, but `workflow_tools.py:project_search` emits token/title/excerpt and only `result.warnings`, which contains retrieval failures, not source warnings. | Include bounded source-specific warnings in the tool receipt and citation registry. Test English OCR limitations, missing original/recovered text, partial Office extraction, repeated-source receipts and cached retrieval. No LLM required: assert emitted tool data. |
| F03 / P1 | **Evidence/benchmark cannot choose current defaults — source-confirmed.** Four sources, six questions, sequential cache reuse, no substantial distractors, source-level rather than support-span scoring. Exclusion case excludes a source already outside explicit selection. | Build the held-out evaluation in section 5. Separate cache states, cold start, concurrency and model revisions. Add actual archived/replaced/deleted/foreign records inside candidate fixtures. Keep old reports as historical; never replace their contents with new runs. |
| F04 / P2 | **Successful retrieval depends on a usage write — reproduced.** `service.py:382` calls `record_usage` without failure isolation. | Make usage recording best effort with content-free diagnostic/event, or a bounded batched update mechanism. Return authorized results despite metadata-write failure. Do not swallow failures in hydration, scope checks or publication. |
| F05 / P2 | **Long-query/passage reranking coverage loss — reproduced with fake tokenizer; production policy source-confirmed.** `_rank` rejects queries above 240 tokens and clips passage prefixes to fit 512. E5-fitting queries may still bypass reranking; late evidence can be unseen by the scorer. | Expose reason and truncated-token counts. Compare shorter semantic chunks, query-aware passage windows and bounded multiwindow max/aggregate scoring. Keep full canonical excerpts/spans; record exactly which window was scored. No silent arbitrary query truncation or unbounded window multiplication. |
| F06 / P2 | **Cold/failure/saturation policy is opaque — source-confirmed.** A cold request permits at least 30 seconds plus cleanup; busy lock and child errors all become `None`; no cooldown; optional availability is inferred from configured path. | Separate load/inference/end-to-end deadlines; validate assets during startup without making optional reranking a required service; bounded warmup and retry cooldown. Return typed fallback reasons: busy, cold timeout, inference timeout, missing assets, invalid scores, query budget. Test repeated unavailable assets and concurrent requests. |
| F07 / P2 | **Lease configuration omits worst-case stage duration — source-confirmed risk.** Config only requires lease > parser timeout. Embedding restart can use initialization + inference + cleanup; point scans make multiple calls; chunk deadline checks occur between potentially blocking token calls. `_lease` rejects renewal once expired. | Validate safety margins or renew independently with fencing; use a shared stage deadline propagated into nested work. Test shortest valid lease, delayed startup/point scans, crash/reclaim, late writes and repeated expired jobs. Ensure poison jobs cannot cycle forever without an actionable terminal state. Default 300-second behavior was not shown failing. |
| F08 / P2 | **No calibrated no-support policy — source-confirmed, historical smoke exhibits it.** Dense retrieval always returns nearest eligible chunks; reranking sorts but never abstains. | Add labelled no-support and near-negative cases; calibrate an optional support gate on held-out data with false-abstention constraints. RRF values and cross-encoder scores are not universal confidence probabilities. Preserve legitimate low-score/cross-language recall; do not hardcode a guessed threshold. |
| F09 / P2 | **Lexical query transformation loses structure — source-confirmed.** Regex `\w+` + OR ignores quotes, punctuation and exclusions; identifiers such as C++/C# collapse, stopword-heavy queries yield noisy candidates, combining-mark scripts need analysis. | Preserve an exact-identifier/phrase branch or structured lexical query policy; compare it with current simple FTS and language-aware alternatives. Retain parameter binding and identical scope. Existing GIN index is present; use EXPLAIN before claiming an index is missing or unusable. No global English-only stemming. |
| F10 / P2 | **Chunk quality and granularity limits — source-confirmed; optimization not yet proved.** Every paragraph/block becomes at least one chunk; no cross-block packing, no overlap, headings stored separately but not embedded/reranked. | Compare block packing, 250/350/450-token targets, 0/32/64 overlap for prose, heading context and structure-aware table/code splitting. Preserve reversible normalized offsets and multi-span provenance. Do not overlap code/tables indiscriminately. Promote only with quality/throughput evidence. |
| F11 / P3 | **Tokenizer IPC amplification — reproduced call counts.** Exact split search makes multiple synchronous `token_count` requests through the model process; validation repeats tokenization before encode. | Add bounded batch token-count/tokenize support or colocate chunk splitting with the tokenizer worker, maintaining a single policy. Benchmark wall time and lock wait separately from inference. Recheck exact budgets after proposed sentence/heading/window changes. |
| F12 / P2 | **Capabilities conflate retrieval and OCR languages — source-confirmed.** `RAGService.capabilities` returns `languages=['en']` while E5 accepts multilingual text; shared Documents correctly reports English OCR. | Separate retrieval model language coverage from installed OCR languages and tested fixtures. Do not turn English/Urdu/Arabic fixtures or reranker training languages into an application allowlist. Test capability API and its frontend consumers. |
| F13 / P2 | **Build identity is recorded but not reproducible from configuration — source-confirmed.** Both baking scripts resolve current model HEAD on each build. Reranker loader only checks nonempty metadata identity. | Add explicit model revision inputs/lock manifest, artifact hashes, dependency/tokenizer/max-length/prefix/pooling identity and reported reranker identity. Validate expected identity at startup. Embedding pipeline identity changes must force an explicit migration, not silently mix existing vectors. |
| F14 / P2 | **Incomplete diagnostics can hide degradation — source-confirmed.** Empty fallback becomes `no_matches` even with dependency warnings; reranking exposes only ok/fallback; static pipeline version lacks effective reranker/config; selection rejection reasons are absent. | Separate retrieval outcome and dependency health, always record total duration including empty scope/errors, and count budget/dedup/document-limit rejection and reauthorization removals. Include effective identities/config and cache layer accurately, without raw user text. Update API consumers/tests compatibly. |
| F15 / P2 | **Obsolete consumer test expectation — reproduced.** `test_rag_gets_modest_extra_budget_and_plain_chat_keeps_default` errors with `KeyError('_tool_budget')`. It mocks `chat.reply`, bypassing the current history coordinator that creates this budget. | Verify current adaptive budget policy and test at its actual creation/use boundary. Document supersession of old 8-versus-6 expectations if intentional; do not restore an old private field merely to satisfy a stale test. Keep the other eight passing delivery/prefetch regressions. |
| F16 / P2 | **Historical/current documentation and compatibility remnants — source-confirmed.** See section 4. | Correct operational docs, label historical artifacts, inventory compatibility callers, and add source-grounded contract checks. Removal needs compatibility evidence, not search absence alone. |
| F17 / P3 | **Retrieval cost scales with broad scopes — source-confirmed risk.** `eligible` is unbounded for an automatic context; each dense miss validates collection + identity before query; all fused candidates are hydrated before rerank. Fixed 80/80 does not adapt to corpus size or filters. | Measure eligible-list size, SQL/serialization, Qdrant requests and hydration bytes at increasing corpus sizes. Parameterize candidate budgets; batch/projection-stage hydration if beneficial. Do not weaken live identity or authorization checks simply to reduce RPC count. Any TTL identity cache needs an explicit invalidation/fail-closed design. |
| F18 / P2 | **Shared memory embedding edge cases — source-confirmed risk.** Up to 32 missing vectors encoded before checking up to 1,000 active memories; any missing vector defers the whole lookup. Character windows/content limits are not exact tokenizer budgets; one bad item can abort a batch and trigger 120-second cooldown. | Add token-aware batching and explicit poison-item/backfill diagnostics; test >32 missing, >1,000 active, multilingual worst-case tokens, empty query, stale/deleted vectors and model revision change. Preserve deferral rather than admitting duplicate/conflicting memories when coverage is incomplete. Do not silently return a partial result as complete. |
| F19 / P2 | **Recovery assumes the old chunk layout — source-confirmed risk for future chunker changes.** `retained_extraction` uses only `spans[0]` and concatenates chunks per block. It works for the current nonoverlapping single-block design, not future overlap/multispan packing. | Before F10 migration, persist/recover normalized extraction or implement versioned span reconstruction with overlap deduplication and gap detection. Test exact hashes and source mapping. Keep existing canonical generations and old citations immutable. |
| F20 / P2 | **Context packing is not a model-context budget — source-confirmed design boundary.** RAG token use is measured with E5; chat serialization adds metadata and uses another tokenizer, and whole-chunk packing can skip all large chunks. | Preserve the orchestration ToolBudget/context cap as the final authority; explicitly name RAG embedding-token counts. Test serialized receipt limits and targeted source snippets with accurate spans for small budgets. Never claim E5 token counts equal chat-provider token counts. |

## 4. Superseded implementation and documentation register

| Existing item | Actual status | Planned disposition and required evidence |
| --- | --- | --- |
| BGE model and old English reranker identities in `verification/rag-real-verification.json` | Valid historical evidence, already labelled in the narrative | Preserve immutable. Add a new report for current E5; cross-link model/date/config manifests. Do not bulk-replace old model names. |
| `rag.md` Optional reranking example uses `cross-encoder/ms-marco-MiniLM-L6-v2` | Operational example disagrees with `.env.example` multilingual model | Replace current example and identity references; preserve the old recommendation in a dated supersession entry. Verify build args, Settings, Compose and real baked manifest agree. |
| `rag.md` materials-volume backup wording, in-memory history description and old multipart document routes | Earlier architecture mixed into current guide; same guide later documents Cloudinary | Rewrite current file/upload/citation/backup contracts from current routes and Files/Chat modules. Preserve historical storage migration evidence separately. |
| `Mentra_RAG_System_Implementation_Plan.md` private-volume baseline | Explicit historical plan | Keep with status banner and link to current Files contracts/new plan; do not rewrite completed history as though originally designed for Cloudinary. |
| `learner_scope.py:qdrant_filter`, `legacy_scope_filter`, `LearnerDocumentMetadata` | Compatibility API for old `learning_context_id/status` payloads; tests and Learner README still reference it. Production RAG uses active-generation filters. | Mark legacy vs production explicitly. Add production-filter integration coverage. Remove only after checking exports/external consumers and providing a deprecation path; do not substitute this filter into current chunk retrieval. |
| `rag_real.py` six-query A/B and `p95=max(samples)` | Useful smoke with misleading benchmark interpretation | Keep smoke; introduce dedicated repeated/seeded benchmark runner with independent services/cache controls and actual percentile labels. Archive baseline output, not silently overwrite. |
| `test_rag_refinements.py` budget test | Failing old private-state assumption | Replace with current coordinator-level policy assertions after confirming intended behavior. Record old assertion, new policy and before/after logs. |
| `RAGService.capabilities.languages=['en']` | Stale language signal | Replace with explicit embedding/reranker/OCR capability semantics and API/UI checks. |

## 5. Test and experiment plan — no live LLM required

Use dedicated PostgreSQL schemas and a disposable Qdrant collection/server. Deny outbound model/provider access during execution; bake pinned local assets beforehand. Synthetic or consented/redacted study material only. Never point test tooling at application storage. Existing tests already isolate database URLs; retain that guard.

| Dimension | Required variants / cases | Measurement |
| --- | --- | --- |
| Baseline ranking | Dense only; lexical only (evaluation adapter); current RRF; fixed selection + RRF; fixed selection + reranker | Candidate Recall@20/80 before rerank, final Recall/MRR/nDCG@3/8, document and support-span metrics |
| Reranker budget | Off, 10, 20, 40; same candidate pool and final budgets | Lift, candidates actually scored, truncation rate, lost viable candidates, CPU/RSS and fallback reasons |
| Passage strategy | Prefix-only vs shorter chunks vs bounded passage windows | Late-answer recall, boundary-question recall, duplicate rate, latency and scored-token cost |
| Chunking | Current block-v2; packed blocks; target 250/350/450; overlap 0/32/64 for prose only; headings on/off | Ingestion throughput, chunk/vector count, index bytes, exact text/span reconstruction and retrieval quality |
| Lexical | Current OR/simple FTS; phrase/identifier-aware policy; selected language-aware alternatives | SQLSTATE, C++/C#, snake_case, version strings, URLs, negation, quoted terms, stopwords, combining marks and mixed scripts |
| Corpus | At least 200 judged queries initially across >=50 sources; expand hard cases before tuning; split by source/course | Separate English, Urdu, Arabic, mixed-language and additional-script slices without restricting supported input languages |
| Hard negatives | Same topic/wrong fact, repeated boilerplate, duplicate documents, obsolete version, wrong owner/context, tail-only support, no support | False-support/false-abstention and forbidden-source count; exact-source and cross-context coverage |
| Formats | Native/scanned/mixed PDFs, Office paragraphs/tables/images, HTML/code/data, empty/malformed/encrypted material | Character/span preservation, warnings delivered to tools, format-specific CER where manually labelled; no claims about general OCR from easy printed fixtures |
| Lifecycle | Upload, replace, reindex, retag/merge, reassign context, archive/unarchive, delete; each cold and cached | Zero forbidden source returns; old published citations still resolve according to policy; cleanup after late writes |
| Failures | Embedding/vector/lexical outage, missing assets, NaN/short score arrays, hung model, usage write failure, lease reclaim, mid-index crash | Typed fallback, bounded latency, old generation survival, no mixed model vectors, retry limits and recovery |
| Load | 1/2/4/8 callers; 100/1,000/10,000+ chunks, multiple owners, 20/40 long reranker candidates | p50/p95/p99, timeout/fallback %, queue/lock time, throughput, parent+child RSS, per-stage I/O |
| Caches | Fully cold; warmed model with cold query/candidates; query hit only; candidate hit; concurrent same query | Independent cohorts, reset between variants; no cross-variant warm-cache credit |
| Consumer delivery | HTTP, chat tool, assessment source contract, source viewer and semantic memory | Exact emitted source IDs/warnings, bounded receipts, canonical citations, proper budget owner, no LLM invocation |

At least 30 warm repetitions per latency scenario plus separately labelled cold starts; randomize variant order, record seeds and raw samples. Use enough queries for per-slice estimates and bootstrap paired confidence intervals before declaring a quality gain. These sample sizes are proposed minimums, not completed measurements. Model-source benchmark claims alone cannot decide Mentra defaults.

Mandatory gates: zero unauthorized/stale-generation leakage; exact span/provenance reconstruction; no candidate starvation on F01 fixtures; warnings reach the actual tool receipt; optional metadata failure cannot discard results; no silent truncation in embedding; invalid reranker output falls back; every failure/degradation is represented accurately. Quality promotion requires no material regression in any safety-critical or language slice and measured benefit on the held-out set. Set numerical latency/recall SLOs from the new baseline before choosing optimizations; do not invent an already-met target.

## 6. Delivery sequence and rollback

| Phase | Scope / dependency | Deliverable and completion gate | Rollback |
| --- | --- | --- | --- |
| 0 — Evidence baseline | F03, F15, F16 | Repair evaluation isolation/current test assumptions; current identity manifest; dedicated dependency services; fresh baseline report. No production behavior change. | Keep previous tooling/report; mark new run invalid if its environment cannot be reproduced. |
| 1 — Correctness and delivery | F01, F02, F04, F14, F20 | Separate selection/scoring/packing functions, preserve fallback tier, deliver warnings, isolate usage writes, coherent diagnostics. All new deterministic regressions and existing API/consumer tests pass. | Revert code/flags; no reindex. Reranker may be disabled if necessary; retain warning and security fixes independently. |
| 2 — Runtime and compatibility | F06, F07, F12, F13, F18 | Typed reranker lifecycle, deadline/lease checks, pinned manifest, language capability contract, shared memory regressions. | Restore previous runtime configuration/worker version with matching embedding identity; optional reranker rollback does not require E5 rebuild. |
| 3 — Measured retrieval improvements | F05, F08–F11, F17 | Controlled ablations; adopt only winning candidate/window/lexical/cache/tokenization policies. Resolve F19 before changing chunk structure. | Flags for ranking-only changes. Retain prior generation pointers and chunker config for chunking changes. |
| 4 — Migration, rollout and cleanup | F10, F13, F19 and accepted experimental changes | Build immutable image; verify isolated services; canary selected documents/owners; compare baseline and new evidence; bounded reindex if needed. Update operator/consumer docs with actual outcome. | Keep old artifacts/index snapshot and canonical generations; stop conflicting workers before incompatible cutover. Restore matching config/index and generation routing; never leave an old encoder querying new vectors. |

Do not use `reset-embeddings --apply` as the normal path for these fixes. Selection, reranker timeout, warning and documentation changes need no embedding reset. Chunking/heading-content changes create new immutable generations and require re-embedding affected documents; retain old canonical chunks for citations. Encoder/model/pooling/prefix identity changes need a distinct compatible collection and explicit cutover/rollback plan. Existing code has no proven zero-downtime dual-model router: use a controlled maintenance window unless that router is separately implemented and tested.

Before rollout: snapshot PostgreSQL, retain Cloudinary originals/bindings, record collection identity/coverage, old image digest and generation mappings; dry-run bounded rebuild work. After rollout: verify API/worker model identities, counts and exact point IDs, publication progress, queue failures, cleanup lag, source warnings, cold/warm retrieval and representative multilingual cases. Reconciliation may delete superseded derived vectors only; preserve canonical provenance/history and original retention policy. Clean superseded code/flags only after the rollback window and compatibility checks; retain evidence records indefinitely under documentation policy.

## 7. Evidence and supersession contract for every implementation increment

Every implemented change gets a dated record in `docs/library/verification/` and an entry in this plan's implementation ledger. Required fields:

| Field | Required content |
| --- | --- |
| Identity/status | Finding IDs, commit and worktree state, date, proposed/implemented/verified/deployed distinction |
| Before → after | Exact behavior replaced, source symbols, reason, retained invariants and compatibility impact |
| Reproduction | Exact command, fixture/corpus hash, seed, dependency versions, model/tokenizer revisions, image digest, hardware/thread limits |
| Comparison | Raw output plus summary; same scope/candidate/final budgets; cold/warm/cache states; per-language results and regressions |
| Boundaries | Passed, failed, skipped and blocked counts; mocked vs real dependencies; explicitly no live LLM calls |
| Migration/rollback | Whether re-embedding is needed, artifacts preserved, rollback command/runbook and verified restoration result |
| Supersession | Old implementation/document/report link, new replacement link, removal decision and compatibility proof |

Initial ledger: **2026-11-02 — audit and offline probes completed; all F01–F20 production changes remain proposed.** This audit supersedes no implementation and does not erase historical verification. The separate unrelated observability investigation already in the worktree is outside scope.

## 8. Reproduction and research sources

From repository root in PowerShell:

```powershell
New-Item -ItemType Directory -Force .tmp/embedding-audit | Out-Null
$env:TEMP=(Resolve-Path .tmp/embedding-audit).Path
$env:TMP=$env:TEMP
$env:PYTHONPATH='backend'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
.\.venv\Scripts\python.exe docs/library/verification/embedding-audit-2026-11-02-probes.py
.\.venv\Scripts\python.exe -m unittest backend.tests.rag.test_processing backend.tests.rag.test_index_initialization backend.tests.test_embeddings backend.tests.test_qdrant_store -v
.\.venv\Scripts\python.exe -m unittest backend.tests.documents.test_readers backend.tests.rag.test_parsers -v
.\.venv\Scripts\python.exe -m unittest backend.tests.rag.test_reranker backend.tests.test_embedding_process -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_rag_refinements backend.tests.test_rag_prefetch -v
```

Windows asyncio tests need functioning local loopback sockets. Database suites additionally require an explicitly dedicated `TEST_DATABASE_URL`. Real reranker suite requires `TEST_RERANKER_PATH` and `TEST_EMBEDDING_PATH`; the full real harness also requires `TEST_QDRANT_URL`. Retain real local models as separate checks from mocked adapter tests. Never interpret the final shell `Get-Content` success as unittest success; inspect the stored unittest summary, including the consumer error and DB setup failure above.

Primary references reviewed on 2 November 2026:

- [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small): retrieval roles, symmetric similarity roles and bounded sequence length support retaining centralized prefix/token policy. It does not establish Mentra corpus accuracy.
- [Multilingual cross-encoder model card](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1): query/passage pair scoring; its language coverage/training description is not an input allowlist or proof of equal quality across languages.
- [Sentence Transformers retrieve-and-rerank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html): two-stage candidate retrieval and pair scoring support separately measuring candidate recall and reranker lift.
- [Cross-encoder evaluation](https://www.sbert.net/docs/package_reference/cross_encoder/evaluation.html): distinguish reranker evaluation with injected positives from end-to-end retrieval; do not inject missed positives into Mentra pipeline recall measurements.
- [PostgreSQL text-search controls](https://www.postgresql.org/docs/current/textsearch-controls.html): query parsing, dictionaries and ranking explain why OR/simple FTS must be evaluated as its actual lexical policy, not called BM25.

Recommendations beyond these documented contracts are hypotheses to test under section 5, not guaranteed improvements.
