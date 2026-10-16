# Mentra prompt improvements and live validation

Implemented locally in `C:\Users\Xclouds\Documents\mentra` on 16 October 2026. Not deployed.

## Final size reductions

Exact `cl100k_base` counts for static text/schema JSON; these are not complete request sizes or DeepSeek token counts.

| Component | Before | After | Reduction |
|---|---:|---:|---:|
| Universal chat | 1,490 | 537 | 64.0% |
| Assessment design | 586 | 424 | 27.6% |
| Assessment generation | 1,032 | 704 | 31.8% |
| Generation output schema | 850 | 410 | 51.8% |

Detailed assessment chat guidance now loads as a separate 507-token fragment when assessment capabilities or existing assessment context need it. Discovery, schema-admission checks, fallback and finalization retain the relevant policy. Ordinary chat avoids that cost. Supporting recovery, web, history and other necessary instructions still contribute to full requests.

The earlier audit used rough character/4 estimates. A verified tokenizer vocabulary exists under `backend/.cache/tokenizers`; setting TIKTOKEN_CACHE_DIR enabled exact local comparisons. Docker already bakes/configures its tokenizer. The existing conservative byte fallback remains available and is now explicitly labeled in usage logs.

## Changes

- Shortened chat, assessment design and generation instructions while preserving explicit request precedence, uncertain learner estimates, source grounding, flexible question types, private keys and outcome honesty.
- Moved assessment-specific invocation/discussion rules out of universal chat; removed duplicate summary instructions from dynamic data and shortened tool field descriptions.
- Removed duplicate current-batch entries from plan/revision overviews; single-batch requests omit redundant overviews. Full current-batch originals, confidence/status information and source excerpts remain available.
- Prepared shared request, learner and source data once and placed it before changing batch data in serialized requests to improve prefix reuse.
- Introduced an internal generation output schema without the server-owned paper structure. Public/saved assessment contracts, validation, checkpoints, concept resolution and grading remain intact.
- Normalized redundant outline weights when explicit leaves already supply marks. Clarified unique part paths, ordinary quiz structure and the authoritative capped count.
- Kept explicit worked-solution and rubric guidance. Single-choice rubrics now state the same all-or-nothing scoring used by the server; multiple-select retains its penalty formula.
- Preserved DeepSeek cache counters through streaming and buffered adapters. `model.usage` records actual provider counts when present, cached/uncached input counts and the local estimation method. Missing usage stays unavailable.

## Live API results against the final schemas

**18/18 scenarios passed, using 22 model calls in the final matrix.** All 16 design/generation scenarios returned schema-valid output on their first attempt and passed Mentra's domain checks. The routing scenarios exercised the actual coordinator with the real argument schema and a harmless replacement for the assessment write service.

Validation included Pydantic parsing; exact count and answer mode; private choice keys; planned marks; allowed citation tokens; duplicate prevention; paper totals, nesting and numbering; retained revision wording; fenced Python code; Urdu output; omitted settings on a bare request; and capability discovery.

| Scenario | Result | Model calls |
|---|---|---:|
| true_false | Pass | 1 |
| mcq_three | Pass | 1 |
| urdu_short_answers | Pass | 1 |
| multiple_select | Pass | 1 |
| custom_matching | Pass | 1 |
| worked_numerical | Pass | 1 |
| custom_ordering | Pass | 1 |
| proof | Pass | 1 |
| python_code | Pass | 1 |
| revision | Pass | 1 |
| grounded_mixed | Pass | 1 |
| quick_mixed_design | Pass | 1 |
| multipart_paper_design | Pass | 1 |
| feedback_design | Pass | 1 |
| nested_parts_design | Pass | 1 |
| capped_twenty_design | Pass | 1 |
| bare_assessment_routing | Pass | 2 |
| urdu_assessment_discovery | Pass | 4 |

The Urdu routing scenario first attempted an unbound tool call with invented argument names. The real coordinator rejected it before execution, then the model discovered the capability and supplied valid count=3, short_answer, Grade 7 and feedback arguments. It completed in four rounds. This is successful bounded recovery, not perfect first-call tool selection; it can add latency and input cost. No invalid tool invocation reached the synthetic action function.

Earlier live checks exposed duplicate empty part paths in a 20-question outline and a single-choice rubric offering working credit. Those prompted the final clarifications. The final 20-question outline has exactly 20 main questions with one leaf each; the final choice rubrics match deterministic scoring. A test-harness assertion that incorrectly treated “Choose the correct answer” as an answer leak was also corrected without changing application validation.

Manual review checked the synthetic arithmetic, correct option sets, even-integer proof, matching/ordering answers, Python examples and revisions. These samples support the changes but do not prove quality parity across every subject or language. Schema validity alone does not establish educational correctness.

## Actual provider input savings

Baseline and final candidate comparisons used synthetic public content. Routing comparisons used the same tool schema; generation comparisons included the narrower output schema.

| Example | Baseline input tokens | Final input tokens | Reduction |
|---|---:|---:|---:|
| Concise Urdu explanation | 1,576 | 614 | 61.0% |
| Interactive quiz routing | 2,649 | 2,216 | 16.3% |
| Multipart paper design | 1,362 | 1,199 | 12.0% |
| Grounded mixed generation | 2,767 | 1,784 | 35.5% |

These are observed provider counts for individual examples, not production-wide savings. Sample timings varied and are not a latency benchmark. A separate streaming test preserved the streamed answer and reported 558 input tokens, including 384 cached tokens. Other live requests also returned cache hits; some returned zero.

## Caching recommendation

Keep DeepSeek's automatic prefix cache alongside the smaller prompts. The API still needs complete necessary instructions/context on each request. Caching can reuse computation for matching prefixes; it is best effort and does not reduce context-window occupancy. See [DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache/?trk=article-ssr-frontend-pulse_little-text-block).

DeepSeek's [Responses API](https://api-docs.deepseek.com/api/create-response/) is also stateless and does not retain conversations. Switching endpoints would not allow Mentra to replace instructions/context with a remembered prompt ID. Keep stable instructions and shared data first, changing data later, and measure actual cached/uncached provider usage. Do not pad prompts to chase cache hits or cache complete learner answers in place of fresh inference.

All live tests used synthetic content. No learner records were read and no application assessment, event, grading or learner state was written. Detailed synthetic results are in `Mentra_Live_API_Validation.json`.

## Regression verification

The final scoped run passed **214 tests in 96.173 seconds** against a dedicated
PostgreSQL 17.11 server on loopback port 55441. It covered chat prompt assembly,
discovery/finalization, concise preferences, streaming, provider adapters, assessment
generation/selection, mixed formats, multipart papers, revisions, checkpoint recovery,
private keys, grounding, grading/evidence alignment, ownership and history summaries.
Ten new focused checks exercise packet deduplication, schema narrowing, conditional
prompt activation, design-mark normalization and cache-counter preservation.

The database cluster was created in this chat's work folder; application data was
not used. No deployment, production load test or exhaustive subject/language quality
evaluation was performed. The temporary database server is stopped after verification.
