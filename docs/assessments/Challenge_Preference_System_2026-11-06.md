# Difficulty preference and learner integration

Implementation revision: 2026-11-07. The deterministic mini-system is implemented end to end. It collects typed choices, links served variants, consumes eligible finalized outcomes in a separate durable worker, and supplies scoped suggestions to learner context. Automatic use requires a student opt-in for that skill and context. No existing users are backfilled and no compatibility layer is introduced.

## What changes for the student

The harder/easier buttons keep a natural user message naming the quiz. UUIDs and revisions travel as typed metadata. The server bypasses the general chat planner and enqueues an owned revision directly. Its acknowledgement says that creation is in progress. The original quiz and attempts remain intact; a failed revision retains checkpoints and an explicit retry.

Settings → Profile & preferences → Challenge preferences provides enable/disable and reset controls. Suggestions explain their limited basis. Explicit requests override learned targets. Reset keeps the audit record but excludes older observations. The shared titled dialog, standard icons, buttons and theme tokens are used. Floating shadows remain minimal and dark surfaces neutral and soft.

## Durable data and execution

Seven additive tables are introduced by migration `20261106_0050`: choice, immutable outcome, effective family, derived state, control, idempotent control operation and background job. The choice ledger stores source IDs/revision, root family, requested/served targets, concept IDs, answer mode and prompt hashes; it does not duplicate student answers, grading keys or chat history. Outcomes refer to existing attempt and grade revisions. Deleting an owner cascades these records.

A typed action must match its durable user turn, owner, conversation, source kind/ID/revision and direction. Duplicate operation IDs return the same durable job. Metadata cannot be combined with attachments, source annotations, interaction continuation or a resume instruction. Source changes during generation fence publication. A synthetic button message does not trigger a second passive learner inference.

Choice registration and generation enqueue share their transaction. Formal grading and accepted learner evidence finish before independent mini-system processing. The challenge worker has its own leases, retry budget, reclaim fencing and failed-job state; an unavailable mini-system cannot roll back a student's completed grade. Reports, corrections, deletion and withdrawals invalidate effective family support. Replaying an immutable outcome cannot revive it. An ineligible later sibling cannot erase an eligible independent family observation.

## Policy and evidence quality

Scope is owner/context/canonical concept/language/answer mode. The policy reads at most 32 distinct root families from the preceding 90 days. Support requires at least three families, six eligible items and two sessions **within the relevant direction**. A session combines conversation and submission UTC date. Repeated variants from one root family supply at most one effective vote per scope.

Harder mean raw correctness ≥0.8 supports a provisional +0.1 offset. Repeated easier choices support −0.1; poor easier performance also recommends a diagnostic. Strong harder plus weak easier outcomes retain the harder signal and flag mixed results for investigation. Poor harder performance never promotes a higher target. Automatic targets clamp to 0.1–0.9; an explicit revision uses the original target ±0.1 within 0–1.

Eligibility requires an independent first attempt, a first-exposure snapshot, accepted formal evidence, grade and concept-grade confidence ≥0.8, an answerable current source, a genuinely changed prompt and target, and verified choice semantics/challenge change. Known exposure, assistance, invalidation and uncertain work abstain. Performance adaptation currently qualifies English/Arabic; other content languages remain supported, but unknown-language observations abstain. No challenge outcome directly writes mastery, relevance, priority or prerequisite knowledge.

The parameters are conservative engineering controls, not empirically calibrated psychometrics. Opt-in does not establish a causal benefit. Automatic default targeting remains gated on prospective calibration and subgroup evaluation. Roadmaps receive the scoped provisional challenge preference separately from demonstrated knowledge and learning priorities; a preference cannot establish prerequisite mastery.

## Generation reliability and quality

The failed source included a seven-option item. Its historical path spent 20.5 seconds in general chat, about 14 seconds waiting for generation, and 41.7 seconds in generation/repair before failing. The first rejected output exceeded the option limit. The second raw output was unavailable, so its exact validity cannot be established from retained logs.

The provider schema now exposes the six-option limit. Valid whole structured objects/tool arguments are recovered without another provider call; prose, arrays, truncation, duplicate JSON keys and unexpected calls are rejected. Repairs retain validated items and regenerate only rejected positions, then revalidate the whole batch. Revisions reuse public source structure without copying old private keys. Difficulty revisions preserve exact canonical concept IDs; clicks cannot create aliases or concepts.

All new choice items receive a separate model cross-check that derives the choice answer without the proposed key. Mixed-format difficulty revisions first solve the public questions without the generated key or rubric, then compare that independent solution with the generated answer. Official DeepSeek review calls use schema-prompted JSON mode to avoid malformed named-tool output. Partial checks use local sequential positions and map them back on the server. Difficulty revisions additionally review written prompts, model answers and rubrics. Deterministic Unicode word facts supply exact letters, adjacent joins and visible diacritics; selectable single-letter lists must match the offered options. False premises, contradictory explanations, wrong scope, ambiguous/missing options and insufficient certainty prevent publication. The reviewer records a specific correction for localized repair. At least two thirds of reviewed items per batch must demonstrate a changed cognitive operation; simply swapping examples, glyphs or numeric labels is insufficient. Unchanged controls do not supply preference evidence. Mixed written/choice revisions use bounded three-item parallel batches, at most two at once.

The checker uses the configured provider in a separate call; it is not independent human adjudication. Written questions outside typed difficulty revisions retain the existing admission and grading checks. Student reports are saved for trusted review; prepublication checking does not silently turn a report into an approved correction. The original and saved answers are preserved when a new variant cannot pass.

## Database and latency budget

Challenge suggestions are folded into the existing learner context-factor query. The active preparation path remains seven SQL queries, one checkout and zero commits (eight queries with the profile combined). No foreground preference LLM call, separate connection checkout or lifetime-ledger scan is introduced. Outcome inserts and effective-family updates are batched. Scope refreshes use indexed LIMIT 32 windows and batches of 64 scopes.

The synthetic scale fixture contains 40,000 effective family rows across eight skills. Thirty off/on samples measured preparation p95 25.342/28.166 ms, an added 2.824 ms. EXPLAIN ANALYZE used the family-window index and returned 32 rows. This is a local disposable-PostgreSQL scale check, not production or student-effect evidence.

Frontend publication uses the generation result directly. Assessment hydration does not wait for a redundant detail read, local navigation does not persist each page change, and polling/backoff/checkpoints survive refresh. Choice grading remains deterministic with no provider call; challenge processing is outside the grading response. Provider-written grading remains subject to its existing budget and recovery limits.

## Acceptance, edge cases and Plan B

| Gate | Required evidence | Response to failure |
|---|---|---|
| Ownership/integrity | Foreign/stale sources rejected; durable message binding; no forged semantic receipt; original unchanged; owner-scoped controls | Disable capture/adaptation immediately and block affected revision; preserve original |
| Idempotency and races | Lost responses reuse operation; duplicate/reordered grades and worker crash/reclaim produce one effective family vote; late report replay cannot revive it | Pause challenge worker, retain raw ledger, retry/rebuild after correction |
| Evidence validity | Assisted/repeated/low-confidence/known-exposure/invalidated/unknown-language work abstains; reset/disable survive reload and concurrent edits | Continue manual choices; supply no learned offset |
| Revision quality | Correct answer/key/explanation, exact concept scope/count/delivery, meaningful requested change and unchanged original | Repair only defective positions within bounded attempts, otherwise preserve original and offer retry; never publish a known-bad fallback |
| Latency | No general planner for typed clicks; no added foreground DB round trip; preparation budget unchanged; ≤200 ms added p95 in matched rated-load tests | Disable adaptation without disabling assessments; investigate generation queues separately |
| Frontend | Ready-to-interact ≤250 ms desktop / ≤500 ms mobile 4× CPU p95; no blocking hydration read or navigation write; accessibility/reload/retry tests | Revert affected UI path and retain direct result handoff |
| Scale | Indexed ≤32-family windows; no canonical concept growth from difficulty actions; bounded pagination and refresh batches | Disable adaptation reads, retain typed choices and current learner targeting |
| Release | All applicable backend/browser checks pass; production bundle/typecheck; additive migration; all seven containers on final source/image revision and healthy | Keep prior images until checks pass; do not destructively downgrade populated ledgers |
| Calibration/benefit | Prospective baseline vs choice-only vs choice+outcome holdouts; calibration/error/abstention by language/format/group; independent blinded assessment review and student study | Keep qualified opt-in/shadow; no universal-fit or learning-gain claim |

Additional covered cases include per-question concept attribution, multiple skills and >64 scopes, empty support and expiry, mixed harder/easier outcomes, source intermediate descendants, private keys excluded from public DTOs, changed request hashes, unavailable preference API, failed capture retry, unsupported tool providers and destructive migration downgrade preflight.

Stop immediately on an integrity failure. A >20% regression in two adequately sampled matched windows blocks promotion. Small provider smoke samples demonstrate a path, not a population percentile or reliability guarantee. Quality and generation/display/grading metrics must be reported separately, including rejected runs rather than cherry-picking successful retries.

## Operations

Global switches: `LEARNER_CHALLENGE_CAPTURE_ENABLED`, `LEARNER_CHALLENGE_ADAPTATION_ENABLED`, and the existing `LEARNER_PERSONALIZATION_ENABLED`. Defaults permit collection and qualified use, while absent per-skill controls default to disabled. Disabling adaptation immediately removes suggestions from context; disabling capture stops new observations.

Private maintenance CLI: `python scripts/challenge_admin.py --owner UUID export|rebuild|retry`. Export is paginated and excludes answers/keys. Rebuild pages existing projections in bounded transactions; a missing projection is recovered through its durable refresh job/retry. This is not a promise of automatic lifetime-ledger reconstruction. Review the failed worker queue and retained source evidence before retrying.

Roll back application images with adaptation/capture disabled if necessary; retain the additive schema. Populated history downgrades intentionally refuse destructive loss, and the public migration helper preflights crossed guards before issuing DDL. No historical assessment or learner records are rewritten for compatibility.

Release verification also found and fixed response-checkpoint serialization of memory timestamps. Checkpoints now serialize supported data types and still reject service objects. This restores memory recall and retains resumable state.
