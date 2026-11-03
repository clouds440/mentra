# Embedding pipeline completion and acceptance — 3 November 2026

This is the current completion record for the [audit and fixing plan](Embedding_Pipeline_Audit_and_Improvement_Plan_2026-11-02.md). The [first increment](history/Embedding_Implementation_2026-11-03-first-increment.md), its failed/blocked runs, older BGE/E5 reports and previous guides remain preserved. Conditional experiments were executed and given explicit adoption decisions. Rejection of an unsafe or unhelpful default is a completed research decision, not a hidden implementation claim.

The [machine-checked acceptance summary](verification/embedding-completion-2026-11-03-acceptance-summary.json) records closed gates, decisions and source hashes. The work is repository implementation plus isolated release acceptance. It does not claim public deployment, production-corpus accuracy, or use of real learner records. All generative model responses in consumer tests were fixtures; no live LLM calls were made.

## Delivered behavior and finding closure

| Finding | Completed implementation / decision | Evidence |
| --- | --- | --- |
| F01 | Viable deduplicated/document-diverse reranker pool, separately typed original tail, correct packing and no cross-score numeric sorting. The old 8→4, 5→1 and 4→0 failures retain 8, 5 and 4 viable results. | Selection regressions, scoring-cap/tail integration assertion. |
| F02 | Extraction/OCR warnings travel with new and repeated tool receipts. Canonical warnings remain retained. | Consumer receipt regression. |
| F03 | Versioned 60-source/300-query synthetic corpus, exact support spans, source/course-separated calibration and held-out cohorts, language slices, no-support judgments and per-source uncertainty analysis. There are 55 held-out sources, 220 answerable queries and 55 no-support queries; five calibration sources contain the other 25 queries. | [Corpus](../../backend/testing/retrieval_corpus.py), [full report](verification/embedding-completion-2026-11-03-research.json). |
| F04 | Advisory usage failures cannot abort search or original-source binding lookup. Mandatory ownership/content/binding failures still propagate. | Search and source-fetch regressions. |
| F05 | At most four exact pair-budget windows cover a passage; scores aggregate by maximum. Coverage overflow explicitly falls back. Winning character windows are returned relative to the canonical chunk, while the original excerpt and provenance stay intact. Queries above the cross-encoder limit fall back without silently changing the question. | [Window ablations](verification/embedding-completion-2026-11-03-ablations-final.json), late-support and overflow tests. |
| F06 | Optional bounded startup warmup, asset preflight, cold/warm deadlines, bounded cooldown and typed fallback reasons. Pipe submission **and** receipt have deadlines. Per-thread outcomes prevent busy callers from corrupting another request's diagnostics/window provenance. Ingestion-only workers skip warmup. | Nonreading-worker/native-hang, restart, warmup and concurrent-diagnostic tests. |
| F07 | Lease budget includes embedding startup, chunking/inference, waiting and cleanup. Point verification renews between 500-ID batches; exhausted reclaim attempts become terminal and deliberately retryable. | Lease/config/batched-verification and expired-attempt integration tests. |
| F08 | Revision-bound opt-in support threshold implemented and tested. Calibration was executed; its candidate threshold falsely abstained on 20% of answerable held-out questions. **Rejected as a global default.** Default remains unassessed support, not a fabricated confidence probability. | [Calibration results](verification/embedding-completion-2026-11-03-research.json), support-gate/config tests. |
| F09 | Optional exact phrase/punctuated-identifier boosting implemented. Simple/structured and English-stemmed lexical alternatives evaluated. Simple stays the default: full hybrid recall was already 1.0, and the English-only dictionary is not adopted as a universal language policy. A separate runtime discovery required the index repair described below. | [Language comparison](verification/embedding-completion-2026-11-03-lexical-languages.json), C++/C# owner-scoped tests, SQL plans. |
| F10 | Targets 250/350/450, overlap 0/32/64 and heading context compared on head/middle/tail placements, including Urdu, Arabic and mixed text. All six variants reached the same Recall@3; **retain block-v2/450/no-overlap defaults**. A reversible packed-block prototype was checked but not promoted: it adds no demonstrated retrieval gain and requires chunk-local offsets beyond the current public span contract. | [Ablations and packing mapping](verification/embedding-completion-2026-11-03-ablations-final.json). |
| F11 | Production chunking executes beside the tokenizer in the reusable process; exact output/IDs/spans remain equal to the legacy path. Native batches have both 32-item and 4,096-token caps. | [165 normalization/span checks and exact equivalence](verification/embedding-completion-2026-11-03-normalization.json), token-batch test. |
| F12 | Retrieval language policy separated from English OCR capability. All input languages remain accepted; tested scripts are fixtures, not an allowlist. | Capability contract and multilingual/window tests. |
| F13 | Pinned model revisions in Docker/Compose/examples; checksum manifests include weights, tokenizer/pooling assets, role policy and inference package versions. Startup validates identity, hashes, file coverage and runtime packages. Clean build, offline source packaging, asset/package parity, exact packaged-source verification and cross-image rollback executed. | Build logs, asset parity, source/image manifests, packaged canary and rollback report. |
| F14 | Pipeline v3, embedding identity, scored/winning windows, candidate/packing counters, thread-isolated fallback reasons and explicit degraded empty results. Empty scope records total time. | HTTP serialization and diagnostics tests. |
| F15 | Obsolete preparation-budget assertion replaced at its real delegation boundary; adaptive coordinator budget/finalization regressions retained. | Consumer suites; original failing log preserved. |
| F16 | Current docs corrected; prior guides/ledger snapshots retained. Legacy scope/filter APIs stay explicitly labelled for compatibility, with their known callers protected. Old BGE and earlier E5 evidence stays historical. | [History](history/), current [contracts](rag.md), prior audit files. |
| F17 | Candidate caps configurable and part of cache identity. Scope reads are bounded to `RAG_MAX_SCOPE_DOCUMENTS + 1`; oversized scopes receive an explicit error before inference, never silently partial results. The default is 1,000 documents; existing explicit selection fits within the minimum supported bound of 20. All 36 size/cache/concurrency cohorts were executed through a real Qdrant server. | [Post-index load matrix](verification/embedding-completion-2026-11-03-indexed-load.json), scope-bound test. |
| F18 | Exact token-aware symmetric windows and versioned derived-memory vector key; healthy windows are batched and the original small overlapping query windows retain late corrections; healthy rows backfill despite oversized poison records. Incomplete/overflow coverage defers memory admission. Corrupt, empty, malformed and non-finite derived vectors are invalidated under the owner/revision fence and rebuilt without changing canonical memories. | Full memory suite, >32 and 1,001-row coverage, poison/vector-repair tests. |
| F19 | Retained-extraction recovery checks exact contiguous/overlap mappings and rejects unsupported/gapped multi-span reconstruction instead of inventing offsets. Current production chunk layout remains unchanged. | Recovery tests, exact normalized spans, preserved old citation canaries. |
| F20 | Embedding-token accounting stays distinct from final model-context/tool receipt budgets. Final ToolBudget remains authoritative; source snippets/provenance stay bounded and unchanged. | Receipt/adaptive budget and packing regressions. |

## Additional confirmed bug: the missing lexical index

The initial source audit saw `Index(...)` declarations and inferred that the GIN index was present. **That inference was wrong for migrated databases.** PostgreSQL inspection showed only the primary/ordinal/generation indexes. SQLAlchemy did not infer the table from the expression's leading regconfig literal, leaving the index unattached; historical migration `0004` enumerated `table.indexes` and therefore never created it.

The historical migration is unchanged. New migration **`20261103_0039`** creates the GIN index concurrently, repairs an invalid interrupted build and refuses an incompatible existing valid definition. Current metadata explicitly attaches the expression index. The query uses a fixed `'simple'::regconfig` literal so generic prepared plans can use the expression index; user query values remain bound parameters.

| Controlled 10,000-row generic-plan check | Result |
| --- | --- |
| Before repair | Both parameterized and fixed configurations scanned the table; the index was absent. |
| After repair, parameterized configuration | Sequential scan; repeated p50 50.7765 ms, p95 74.315 ms. |
| After repair, fixed configuration | Bitmap/index plan; repeated p50 1.229 ms, p95 3.234 ms. |
| Method | 32 samples per variant, randomized execution order, real PostgreSQL; raw plans and buffers retained. |

See [original plan discovery](verification/embedding-completion-2026-11-03-sql-plans.json), [repaired plan](verification/embedding-completion-2026-11-03-sql-fixed.json) and [repeated acceptance](verification/embedding-completion-2026-11-03-sql-acceptance.json). Migration tests cover fresh creation, upgrade/downgrade/upgrade with canonical row equality, invalid concurrent-build recovery, valid-index idempotence and competing migration safety.

## Quality, cost and adoption decisions

| Held-out variant | Recall@3 | MRR | nDCG@3 | Observed p50 / p95 | Degraded queries |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense E5 | 1.0 | 1.0 | 1.0 | 72.58 / 127.89 ms | 0 |
| Simple lexical + dense RRF | 1.0 | 0.9811 | 0.9860 | 70.89 / 125.53 ms | 0 |
| Structured lexical + dense RRF | 1.0 | 0.9811 | 0.9860 | 68.37 / 85.19 ms | 0 |
| Rerank 10 | 1.0 | 0.9841 | 0.9883 | 720.48 / 1983.38 ms | 0 |
| Rerank 20 | 1.0 | 0.9750 | 0.9815 | 891.07 / 1981.85 ms | 0 |
| Rerank 40 | 0.9955 | 0.9667 | 0.9741 | 992.86 / 3245.88 ms | 47 |

These are synthetic workflow fixtures with four templated phrasings per source, not 300 independent real-user intents. The first ranking run used a fixed variant order and overlapped other verification work. Its latency observations are not a causal isolated A/B speed claim. Model weights and inference-package parity between the research and release images were verified. Analysis groups paraphrases by source for uncertainty estimates; production quality must not be inferred from fixture perfection.

Decisions: retain the existing 20-candidate default and optional reranking deployment policy; reject increasing it to 40. Do not promote structured/English lexical defaults from these fixtures. The English analyzer improved lexical-only Recall@3 from 0.9455 to 1.0 here, but those queries use English prefixes and full dense/simple hybrid already recovered every judged source. Keep language-specific stemming as an experiment rather than changing every language's token policy.

For late-support passages, randomized candidate positions produced **1/13 prefix-only versus 9/13 full-window top-1**; exploratory paired bootstrap lift was 0.6154 (95% interval 0.2308–0.9231 within this fixture). One individual English case regressed and four full-window cases remained wrong, including both Arabic long-passage cases. Aggregate tested-script slices did not worsen. This supports bounded coverage instead of silent clipping, not a claim of reliable multilingual answer support. Winning offsets and fallback remain visible.

The calibrated cutoff `-1.7055683135986328` had held-out false-abstention 0.20 and false-support 0.0364; it is **not enabled**. Raw cross-encoder values are not probabilities. Whole-chunk support delivery remains the caller's responsibility.

After the SQL fix, 36 cohorts × 32 requests = **1,152 measured requests** covered 100/1,000/10,000 canonical chunks, concurrency 1/2/4/8 and cold/query-hit/candidate-hit modes. There were zero observed degraded responses; worst cohort p95 was 774.05 ms, below the local 2-second regression bound chosen from the earlier 1.69-second baseline. This is a local acceptance bound, not a production SLO. The load fixture deliberately repeats canonical content to stress candidate/filter/packing work; it is not a diverse 10,000-document quality corpus. Sampled parent-plus-child peak RSS was 1,159.57 MiB for this E5-only load; the separate embedding-plus-reranker ablation sampled 2,716.12 MiB. Separate database/vector containers are excluded from those process-tree figures.

## Final acceptance and artifact identity

| Gate | Evidence |
| --- | --- |
| Frozen-image combined suites | [Final-image test log](verification/embedding-completion-2026-11-03-finished-tests.txt); **154 passed in 87.263 seconds** against the exact source-fingerprinted image. The preceding complete accepted-image run passed all 153 tests. |
| Real multilingual local models | [27/27 direct and pipeline cases](verification/embedding-completion-2026-11-03-accepted-multilingual.json), reuse and fallback passed; cold 10.2029 s, warm maximum 0.0572 s. |
| Exact packaged source, assets, HTTP and lifecycle canary | [Final-image canary](verification/embedding-completion-2026-11-03-finished-canary.json), [source fingerprint](verification/embedding-completion-2026-11-03-finished-source-manifest.json). App source was not bind-mounted; only test helpers/evidence were mounted. |
| Native deadlines | Nonreading-worker tests use a 2 MB pipe submission; native hangs are killed and workers restart. Warm/cold inference bounds include IPC; cleanup has a separate bounded allowance. |
| Canonical spans | [165 normalized span checks](verification/embedding-completion-2026-11-03-normalization.json), exact remote/local chunk equality. Sampled legacy IPC 62.30 ms versus colocated 35.42 ms. |
| Cross-image rollback | [Rollback report](verification/embedding-completion-2026-11-03-artifact-rollback.json): new image → index-only downgrade → retained old image → re-upgrade/new image; same document, generation and vectors remained usable. Synthetic targets were explicitly removed. |
| Model reproducibility | [Asset/package parity](verification/embedding-completion-2026-11-03-asset-parity.json): weights/tokenizer/config bytes, identity and inference package versions matched the research image. |
| Build | Clean pinned build plus offline source refresh; [ready build](verification/embedding-completion-2026-11-03-finished-build.txt), [reproduction Dockerfile](verification/embedding-completion-2026-11-03-final.Dockerfile). Image IDs and source/data hashes are recorded in the completion manifest. |

The accepted image is `mentra-backend:embedding-finished-20261103`. Earlier image tags and report files remain available. Model assets are baked; test execution used offline Hugging Face/Transformers modes. Fixtures used dedicated PostgreSQL schemas, temporary Qdrant collections and in-memory original-file providers. HTTP checks used fixture identities and explicitly tested owner isolation; they are not a public-authentication deployment claim.

Failed/intermediate evidence remains: missing test-helper mount and inherited fake revision in the first packaged suite; initial long-input ablation timeout; interrupted unbounded-thread run; raw-versus-normalized newline coverage check; original obsolete budget/tail assertions. Retries corrected the fixture/method or implementation rather than rewriting the old result. Some stress runs emit resource-tracker cleanup warnings after terminated model processes; disposable containers were removed, and normal canaries/accepted suites completed successfully.

## Rollout, rollback and cleanup

No embedding reset, model migration or chunker reindex is required for these changes. **The PostgreSQL migration is required.** Drain/stop conflicting API and worker versions, retain a PostgreSQL snapshot plus matching Cloudinary originals/bindings, build the pinned image, apply Alembic head `20261103_0039`, and recreate backend/RAG/assessment workers together. Compare parser/job configuration across images before resuming queued work; queue a bounded normal rebuild if an independently changed parser identity requires it. Verify readiness, exact index identity/coverage and owned source canaries. Do not use `reset-embeddings --apply` for this repair.

Software rollback across `0039` uses the new image's migration tooling to downgrade to `20261029_0038` before starting the old image: its startup schema gate expects that head. This removes only the derived GIN index and leaves canonical rows, original bindings, citation generations and Qdrant vectors intact. Restore matching prior runtime/model configuration; stop conflicting workers during cutover. The cross-image rehearsal verified this path and subsequent re-upgrade. Do not delete superseded canonical chunks or old original versions to clean up derived indexes.

The implementation and local release gates are closed. Public rollout, a production-data calibration corpus and any future fine-tuning/sparse-model work remain separate operational/product decisions; none is represented as already deployed or validated here. Current defaults were not changed merely to make an experiment appear successful.

## Reproduction

Use dedicated `TEST_DATABASE_URL` and `TEST_QDRANT_URL`, never application URLs. Mount `backend/testing` and `backend/tests` read-only into the baked image for the verification modules; mount only a separate evidence directory writable. Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`. Give every run a new output filename: completed reports refuse overwrites.

- `python -m testing.retrieval_completion --output /evidence/new-research.json` — corpus/ranking/calibration, cache and load experiments; current runner shuffles variant order and groups bootstrap samples by source.
- `python -m testing.retrieval_completion --load-only --output /evidence/new-load.json` — post-index load matrix with process-tree sampling.
- `python -m testing.retrieval_ablations --output /evidence/new-ablations.json` — chunk/overlap/headings/packing/windows.
- `python -m testing.retrieval_sql_plans --output /evidence/new-plans.json` — actual index catalog and randomized prepared-plan timings; requires test helper mounts.
- `python -m testing.retrieval_release --output /evidence/new-canary.json` — packaged HTTP/lifecycle/rollback canary; set `TEST_SOURCE_MANIFEST` for exact source-byte verification.
- `python -m testing.retrieval_artifact_rollback --phase prepare|old|new|cleanup --report /evidence/new-rollback.json` — sequential cross-image rehearsal; `old` runs in the retained prior image. Cleanup validates the synthetic schema/collection prefixes and requires both verification phases to pass.

Review the raw report scope and cache/thread/model identities before comparing timing numbers. Historical BGE/early-E5 results are preserved for lineage and are not silently relabelled as current performance.
