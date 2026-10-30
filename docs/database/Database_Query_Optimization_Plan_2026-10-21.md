# Database query optimization plan

**Status:** proposal only; no implementation or database changes authorized by this document.

**Date:** 21 October 2026. **Evidence:** [database fetch audit](audits/Database_Fetch_Latency_Audit_2026-10-21.md).

## 1. Objective and scope

Reduce database round trips, repeated reads, fetched bytes, lock contention, and redundant requests across Memories, Progress, Events, Assessments, Library, Notifications, profile settings, and persistent chat.

Keep existing page layouts, visible information, ordering, counts, search semantics, privacy, scoring, ownership, source provenance, errors, retry behavior, and mutation guarantees. Frontend work is limited to fetching, prefetching, deduplication, and cache invalidation behind existing screens. This plan does not change model prompts, models, assessment generation/grading behavior, or the app's product flows. Hosting changes are not prerequisites.

The order matters: fix session fragmentation and repeated projections first, add safe cache reuse next, then introduce only indexes supported by plans and representative data. A single browser request must also reduce underlying database work; simply wrapping existing expensive methods in another endpoint is insufficient.

## 2. Baseline and proposed budgets

Measured current behavior:

- Protected memory GET: 3 SQL statements, 3 checkouts, approximately 0.82 seconds.
- Event GET on an empty agenda: 6 statements, 3 checkouts, approximately 1.02 seconds.
- Assessment list: 4 statements, 3 checkouts, approximately 1.08 seconds.
- Progress overview business read: 18 statements, 17 checkouts, 4.82 seconds.
- Understanding business read: 6 statements, 5 checkouts, 1.44 seconds.
- Reusing one read session without reducing SQL lowered those last two measurements to 1.63 seconds and 0.63 seconds.

These measurements come from a small database over approximately 65 ms network round trips. They are not production service-level promises.

| Operation | Proposed normal-path HTTP budget | Proposed SQL budget, including one combined identity/onboarding read | Checkout budget |
|---|---:|---:|---:|
| Memories initial view + preferences | 1 | ≤3 | 1 |
| Events agenda + pending proposals | 1 | ≤6 business SELECTs + bounded transaction setup | 1 |
| Progress overview + contexts + first understanding page + pending concepts | 1 | Initially ≤10; target ≤8 after projection reuse | 1 read unit |
| Assessments list + context choices | 1 | ≤4 | 1 |
| Assessment detail + attempts | 1; reuse already-cached list | ≤4, with bounded attempt payloads | 1 |
| Mistake page + totals + facets | 1 | ≤5, bounded result transfer | 1 |
| Library list + context choices | 1 | Establish baseline, then ≤5 if existing contracts permit | 1 |
| Notifications list + unread count | 1 | ≤4 business SELECTs + bounded transaction setup | 1 |
| Chat prompt stable metadata | Existing send request | 1 identity/profile gate + 1 batched version/freshness query; unchanged blobs served from cache | ≤2 before history/tool-specific reads |
| Chat recent messages + conversation summary | Existing send request | ≤2 on a cold payload load; fewer with valid reuse | 1 shared history read unit |

Budgets are design/acceptance targets for ordinary paths, not claims of completed optimization. Exceptional initialization, stale-policy refresh, recovery, and live tool operations must be measured and reported separately. Do not hide meaningful work inside an unbounded SQL statement just to meet a statement-count target.

**Performance acceptance:** same results with at least 50% lower median cold Progress database time in a controlled before/after comparison, no regression in ordinary page p95, and materially lower fetched bytes/query count on large-history assessment/mistake fixtures. Establish p95 under controlled concurrency before setting final numerical limits. Warm cache hits should avoid reloading unchanged profile/summary blobs while still checking current authorization and relevant revisions.

## 3. Required invariants

| Area | Invariant |
|---|---|
| Authorization | Session expiry/revocation and owner checks remain effective on every protected request; cached payloads never authorize a request |
| Cache isolation | Keys contain canonical owner and all relevant resource/filter/version dimensions; logout/owner switches clear browser state |
| Concurrent requests | SQLAlchemy sessions and mutable repository state are never shared between requests, threads, or concurrent tasks |
| Freshness | Relevant mutations increment revision metadata in the same transaction as canonical changes; failures/rollbacks never publish a new cache value |
| Memory | Deletion, correction, conflicts, expiration, disabled preferences, and changed supports cannot leak stale personal statements |
| Learning | Current policy, context status, mastery, verification, evidence, confidence, and provenance remain equivalent |
| Pagination | Preserve exact ordering, cursor bindings, date ranges, counts, and clamping; no gaps or duplicates |
| Events | Preserve repeatable snapshot/watermark consistency and civil-date/timezone semantics |
| Assessments | Preserve immutable question IDs, private answer exclusion, grade revisions, practice lineage, latest-attempt selection, and historical attempts |
| Writes | Keep domain ownership, owner-first lock ordering, atomic delivery, receipts, and deduplication; optimize reads without weakening these contracts |
| Failures | Preserve required failures and optional partial-data behavior; batching does not make an unrelated section fail unnecessarily |

## 4. Phase A — make database cost visible

**Files:** `backend/app/db/database.py`, `backend/app/db/timing.py`, existing request/workflow timing, focused performance tests.

1. Add content-free request metrics for query count, checkout count, checkout wait, new connection/setup, pre-ping, transaction completion, fetch/materialization, and returned bytes/rows. Distinguish client elapsed time from PostgreSQL execution time.
2. Aggregate these metrics per request and page section. Emit sampled summaries or slow-operation events instead of logging every successful SQL statement at INFO. Do not log SQL parameters, tokens, profile text, memory text, or document contents.
3. Record baseline query shapes and EXPLAIN plans for page-list, search, context-filter, detail, and pagination paths.
4. Use deterministic small fixtures plus representative large fixtures: many contexts/concepts, multiple pages of assessments, maximum attempts per assessment, corrected grades, related practice lineage, long chat history, expiring memories, and mixed event statuses.
5. Add controlled concurrent navigation/chat/worker measurements. Measure thread wait and API pool wait independently; neither is currently proven to be the main cause of the long tail.

**Acceptance:** request metrics explain total database time without treating nested spans as additive; successful query logs do not become background noise; baseline records separate cold connection, warm connection, warm payload cache, and concurrent cases.

## 5. Phase B — one request-scoped read unit and one lightweight gate

### B1. Reuse a connection for related reads

Add an explicit read-unit API that creates a session plus request-scoped repository instances. Domain read facades accept this unit or build bound repository clones. Execute dependent queries sequentially on that session, then return detached typed results and release it promptly.

Do **not** set `_active_session` on the application-global learner repository. The audit did that only inside an isolated diagnostic process. Do not run simultaneous queries on one session or retain a connection while waiting for a model, cloud file, browser client, or unrelated external service.

For synchronous persistence, dispatch the complete read unit to one worker-thread operation. Independent external work can remain concurrent outside it. Use read-only transactions for paths that truly only read; select snapshot isolation deliberately where multiple projections need consistency.

First apply this to Progress, then page aggregate reads and chat context loading. Retain current public repository/service boundaries for writes.

### B2. Combine identity and onboarding projection

Build a narrow principal query joining the session/account with the profile onboarding phase. Select only identity, expiry/revocation checks, onboarding state, and useful revision metadata for normal page requests. Cache the result only within the current request using dependency reuse.

When chat needs the high-level profile too, reuse an already-loaded request projection or join/load it once; do not read the full profile again simply because prompt assembly is a second caller.

Preserve existing behavior for absent profiles through the explicit initialization path. Do not silently turn initialization into a read-only transaction or change onboarding errors. General authentication endpoints must continue to work before onboarding is complete.

### B3. Preserve read-triggered refresh semantics

Context dormancy and stale learner-policy recomputation can currently write during reads. Detect and perform a required refresh once in an explicit bounded write unit, then rebuild the read snapshot. Do not return old mastery or postpone a required refresh merely to make the read-only path fast. Prefer request-local reuse of the refreshed projection over repeated refresh checks.

**Acceptance:** ordinary requests use one read connection; no new owner locks on list reads; concurrent requests cannot see another request's transaction/cache; logout, revocation, onboarding, stale-policy, and dormancy checks retain their existing outcomes.

## 6. Phase C — remove redundant SQL and build page read projections

### C1. Progress

Create a typed Progress read projection containing contexts, overview, first understanding page/counts, recommendations, verification suggestions, and candidate concepts.

- Load owned contexts once per distinct selection policy.
- Batch concept/state/factor/prerequisite/misconception reads for the required IDs.
- Compute recommendations and verification from one shared ranking dataset, as the existing combined study-target path already does.
- Reuse canonical concept/state data between overview and understanding where their exact scopes match.
- Avoid an unnecessary keyword-search/fallback/reranking cycle for the fixed overview label when a directly equivalent existing selection can be reused. Prove equivalence before changing this query path.
- Do not reuse data across different query-based context selections, archived-context rules, bounds, policy versions, or supported-verification modes.
- Keep exact totals and offset clamping; optimize repeated count scans with one appropriate CTE/projection when EXPLAIN supports it.
- Fetch the first understanding page with the overview so the browser no longer waits to begin a second database request. Subsequent topic pages remain bounded independent requests.

### C2. Memories

Return the first memory page and memory preferences together through one authenticated read facade. Preserve search, status, limits, cursor ordering, stale flags, and detail/evidence endpoints. Preferences should not be reloaded on every search keystroke when their revision is unchanged.

### C3. Events

Return agenda and pending proposals together for the active Events view. Include preferences only when actually required, and detail only when a selected event is requested. Keep the page watermark and projections in one repeatable snapshot.

Configure isolation before the first query using supported connection/transaction configuration and reduce avoidable per-request SET traffic where equivalently safe. Retain statement/lock timeouts and prevent settings leaking through pooled connections. An event detail fetch should reuse the current list cache rather than refetching the entire agenda unnecessarily.

### C4. Assessments

Introduce a dedicated list DTO containing card fields: ID, title, purpose/tags, revision/date, question/part counts, and attempt-summary badges. Do not download question bodies, full paper JSON, source packets, answer material, or private keys for every list card.

Replace fetching every attempt's grades for summary construction with a bounded SQL projection: count attempts per assessment, select latest state, identify the latest graded attempt using the existing attempt-number/tie-break rules, and derive its summary. Use aggregate/window/lateral queries as appropriate; preserve skipped/ungraded-question behavior.

Load full questions/paper only on detail or imminent detail prefetch. Return detail plus required attempt history in one read unit. Continue excluding uploaded artifact bytes and grading checkpoints. Keep existing endpoints as compatible wrappers until all internal callers use the narrow list contract.

Only fetch data needed for the active assessment tab: entering Mistakes should not also fetch full assessment papers for the hidden Assessments tab; entering Create should not require them either.

### C5. Mistakes

Replace full Python-side history collection before pagination with a bounded database projection. Preserve the exact root-question lineage, latest cross-practice resolution, repeated-error counts, grade revision, severity ordering, and globally scoped filter facets.

First optimize source columns and SQL aggregation without adding a persisted derived table. Push filters only where they do not change global resolution/facet semantics. In particular, filtering source assessments too early can incorrectly mark a mistake unresolved when later practice elsewhere resolved it.

If measured history size still requires it, add an owner-scoped derived mistake projection updated transactionally after accepted grading/correction changes. Backfill from canonical assessments/attempts with a replayable version; compare old/new outputs before switching reads. Keep original grades, answers, attempts, and lineage intact. Projection failures must have a correct fallback.

### C6. Library, Notifications, profile and chat navigation

| View | Database optimization |
|---|---|
| Library | Combine material summaries and context choices; select list fields only; batch document-context associations; exclude extracted chunks/files from list reads |
| Notifications | Keep list/count/watermark in one snapshot; use a narrow unread-count projection for the bell instead of fetching a notification body solely to count |
| Profile settings | Load full profile once for the view; reuse current profile projection for dependent settings reads |
| Conversation sidebar | Reuse the existing local conversation cache; keep sync responses bounded; investigate replacing owner-write locking on unchanged sync with a correct read snapshot |
| Conversation detail | Batch ownership, recent message window, and summary reads; preserve completed-exchange filtering and retry sequence boundaries |

**Acceptance:** response parity for visible data; narrower list payloads; no hidden-tab database work; unchanged filters/cursors/date semantics; target budgets in section 2 met or any exception documented with evidence.

## 7. Phase D — safe reuse across chat prompts

### D1. Cache payloads by revisions, not by an assumed immutable session

Use a bounded owner-scoped process cache for high-level profile and summary payloads. At the beginning of a new prompt, obtain authoritative revision/freshness metadata in a compact batched SELECT. Equal revisions allow reuse of cached blobs; changed revisions reload only affected data. This still checks freshness every prompt but avoids retrieving and rebuilding unchanged content.

| Payload | Cache key / validity | Invalidating changes |
|---|---|---|
| High-level profile | Owner + profile/context revision + projection-policy version | Profile edits, calibration/evidence changes affecting that projection, account deletion |
| Memory summary | Owner + source revision + summary revision + prompt/projection version + support validity + nearest expiry | Save/edit/delete/pin/status/conflict/evidence revision changes, expiry, summary publication, preference changes |
| Conversation summary | Owner + conversation ID + summary revision + through-sequence + validity-policy version | Summary publication/repair, conversation deletion/reset, changed validity limits |
| Recent history window | Owner + conversation ID + message/change revision + turn boundary | Message/turn completion, stop/correction/deletion, metadata changes affecting eligibility, different retry sequence |
| Learner read datasets | Request-local first; cross-turn only after complete revision contract exists | Evidence/grade corrections, ontology redirects, context membership/status, policy changes, time-sensitive retention |

For memory hits, retain the same canonical support/revision/eligibility checks as today in the compact freshness query. `source_revision` alone is insufficient: revision-only support bookkeeping and clock-based expiration must also invalidate or refresh cached content. Never cache a dirty/repairing result as permanently ready.

Existing profile revisions must be audited against every write path before being used as freshness keys. Where a complete version does not exist, add a narrowly scoped additive revision updated transactionally. Do not invent a cache whose invalidation covers only API writes but misses workers, corrections, imports, or account cleanup.

Time-dependent learner projections should use a fixed request timestamp for consistency and remain fresh under existing retention behavior. Do not cache mastery/retention output indefinitely just because underlying evidence has not changed.

### D2. Keep invalidation correct across processes

- Authoritative revision probes make correctness independent of in-process eviction and BroadcastChannel delivery.
- Local mutation callbacks may eagerly evict entries after commit. Worker and other-process changes are detected by the next revision probe.
- Cache fills use single-flight per complete key. Canceling one waiter does not cancel other consumers; bounded cache fills cannot outlive their owner indefinitely.
- Keep unchanged profile, memory-summary, conversation-summary, and recent-history payloads without a time expiry. Bound cache entries/bytes; process restart or capacity eviction may require a cold load. Invalidate using authoritative revisions, ownership, eligibility, and existing fact expirations.
- Never cache authentication success for the entire browser session. Never bypass current ownership checks with a cached prompt packet.
- Preserve RAG's existing candidate-only caching and canonical hydration/authorization; do not add an orchestration cache of source content.

### D3. Make memory-summary context preparation a read fast path

Split canonical summary snapshot loading from initialization/maintenance. For valid existing state, read summary metadata, eligible supports, and required deltas in a consistent snapshot without `INSERT ... ON CONFLICT` or owner `FOR UPDATE`.

Create missing state during the existing initialization/canonical mutation path or an explicit bounded slow path. Queue required repair/expiry work idempotently while preserving existing immediate filtering of deleted/expired/changed facts. Keep the final publication freshness fence and required write locks on canonical mutations.

### D4. Repair incompatible stored summaries without repeated request writes

Provide a targeted repair/backfill for stored summaries that fail current size/token policy. Preserve originals and history; do not truncate text arbitrarily or increase prompt limits to make bad data pass.

Make repair scheduling idempotent for `(conversation, summary revision, validity-policy version)`. An unchanged invalid summary should not acquire an owner lock and reset/requeue the same repair on every prompt. Cache the validation outcome for that revision, retain the safe current fallback, and switch only after fenced publication of a valid replacement.

Actual repair can require the existing background summarizer; this plan changes database scheduling/reuse, not its model prompt or generation policy.

### D5. Reduce monitoring read overhead

Combine active-turn and memory-support freshness checks into one bounded snapshot query/session where possible. Preserve stop/delete detection, expiry, memory-change cancellation, retry fencing, and final publication checks. Do not remove monitoring or weaken correctness merely to reduce query count.

**Acceptance:** second unchanged prompt reuses profile/summary blobs; another process's update is visible on the next prompt; expiring/deleted facts never survive a hit; a concurrent change still prevents stale publication; repair queues remain single-flight; no extra paid/model calls are used for benchmarking.

## 8. Phase E — combine browser fetches and prefetch selectively

Add small domain-owned page-read endpoints or a tightly bounded internal composition layer. Proposed shapes are illustrative and should follow existing API conventions:

| Read | Included data | Excluded until needed |
|---|---|---|
| Memories view | List + preferences | Full evidence/detail |
| Progress view | Contexts + overview + first understanding page + candidates | Other topic pages/evidence details |
| Events view | Agenda + proposals | Unselected event detail/calendar export |
| Assessments view | Summary list + context choices | Full papers, answers, uploads |
| Assessment detail | Selected paper + required attempts | Other papers/attempt artifacts |
| Library view | Material summaries + context choices | File contents/chunks |

Do not build a universal fetch-everything endpoint. Authenticate once per aggregate request, pass a trusted owner to domain read facades, reuse the read unit, and explicitly represent optional section failures without changing required failures. Enforce normal section limits and total response-size bounds.

Prefetch into the same owner-scoped cache used by navigation:

1. On navigation intent such as pointer hover or keyboard focus, prefetch that destination's first summary page if missing/stale.
2. On strong assessment/detail intent, prefetch only the selected resource; reuse any list metadata already loaded.
3. Prefetch the next page only when a next cursor exists and there is strong paging intent. Preserve exact filters, cursor watermark, and date-range values.
4. Optionally prefetch one likely destination after authenticated idle time; disable unnecessary speculative work on constrained connections and while user-critical requests are waiting.
5. Limit speculative work to one outstanding request initially. A visible navigation joins the same pending request instead of launching a duplicate. A prefetch cannot bypass authorization, trigger repair-heavy write paths, or read unrelated private resources speculatively.

Replace global invalidation during ordinary refresh with affected-domain/key invalidation. Track cache generations so obsolete responses cannot repopulate invalidated entries or update a new owner's view. Abort obsolete underlying requests when no live consumer remains; avoid canceling a shared fetch still needed by another consumer. Backend queries remain bounded even when browser abort does not cancel a running database statement.

**Acceptance:** one initial fetch per composed view, no Progress waterfall, one network request for identical overlapping navigation/prefetch, no full-app prefetch burst, and same freshness as foreground reads.

## 9. Phase F — index inventory and evidence-based migrations

The measured basic queries already use indexes. Do not add duplicates or rebuild working indexes as a first fix. Compare live `pg_indexes`, Alembic history, predicates, column direction, uniqueness, and query plans; model declarations alone do not prove an index exists in the deployed database.

| Query family | Existing coverage | Candidate only if representative EXPLAIN proves benefit |
|---|---|---|
| Session/profile by owner | Unique token digest; profile primary key | No new index expected |
| Memory recent list | `(learner_id, updated_at, id)` | No duplicate DESC index; backward scans already support matching descending order |
| Memory search | FTS and trigram GIN | Reuse; assess selective status/owner filtering before adding another composite index |
| Event agenda | `(learner_id, status, sort_at, id)` and cutoff index | Additional all-status ordering index only if all-status requests are materially slow |
| Event substring title search | Agenda index; no title trigram coverage established in the inspected event index set | GIN trigram on title for measured large searchable agendas; preserve literal wildcard escaping |
| Assessment recent list | `(learner_id, created_at)` | `(learner_id, created_at DESC, id ASC)` if sorting/page depth justifies it; current incremental sort is already very cheap |
| Latest/count attempt summaries | `(learner_id, assessment_id)` | `(learner_id, assessment_id, attempt_number DESC, id ASC)`; optional graded partial index if the chosen query needs it |
| Graded mistake history | Owner/assessment and queue indexes | Owner + submitted/created/id ordering, partial `WHERE state='graded'`, based on final query shape |
| Context membership | Context/concept primary key and learner/concept index | `(learner_id, context_id, concept_id)` only if plans show existing indexes insufficient |
| Context paging/filter | Unique owner/id and owner/status/activity | Retain unless actual new projection plans require different ordering |
| Learner states | Primary key `(learner_id, concept_id)` | No new index for batched concept-state reads |
| Evidence/misconceptions | Owner/concept/time and existing decision indexes | Align accepted-decision/canonical-concept projection with measured plan; avoid indexing large JSON payloads blindly |
| Chat recent/history | Owner/update/id and owner/conversation/sequence | Consider live-conversation partial index if deleted-history scale justifies it |
| Summary/job lookup | Conversation/owner primary keys and claim indexes | No duplicate revision/owner index; verify new batched joins use existing keys |
| Worker queues | Existing state/time/claim indexes | Partial ready-state indexes only if claim plans and backlog scale justify them |
| Notifications/documents | Inventory complete live definitions before deciding | Owner/filter/order partial indexes only after concrete plan comparison |

Substring search implemented with `strpos()` does not automatically benefit from a trigram index. If a search rewrite is needed, establish exact parity using escaped substring matching on the same normalized values, including punctuation, wildcards, Unicode and multilingual input; do not change search semantics to force index use.

For each approved index: record before/after EXPLAIN, estimated/actual rows, buffers, sort/spill behavior, size, write overhead, and realistic owner cardinality. Use a migration strategy compatible with the current nonblocking migration-lock design and concurrent index builds. Detect/recover invalid interrupted indexes. Do not remove an existing constraint/index merely because a new one overlaps it.

**Acceptance:** each added index has a specific query and benchmark justification; no duplicate indexes, destructive data migration, or unexplained write/worker slowdown. A phase that adds no index is acceptable when the existing ones cover the optimized queries.

## 10. Phase G — reduce background contention and pool occupancy

- Keep API and worker connection budgets distinct. Current API pool is 5; each worker defaults to 1. Four assessment consumers sharing one connection can queue each other; measure rather than simply increasing every pool.
- Reduce repeated no-work sweep/claim queries where one bounded claim operation can preserve independent queue fairness. Apply bounded adaptive idle/error backoff with an agreed maximum job-start delay; do not delay already-ready user work beyond the existing observable contract without explicit review.
- Batch bounded maintenance reads/writes; keep owner transactions short and preserve owner-first ordering. Avoid per-token/per-item transactions when existing batching can safely carry them.
- Preserve immediate stop/freshness checks while combining their reads. Separate ordinary snapshot reads from owner-write locks.
- Evaluate replacing unchanged chat sync's write lock with a consistent read snapshot, preserving cursor/reset/deletion ordering. This is conditional on concurrency tests, not a blanket lock removal.
- Measure total connection demand across all processes, health probes, tools, migrations, and diagnostic jobs against the database/server pool limits before changing pool sizes. A larger pool is a capacity decision, not a fix for sequential round trips.
- Retain pre-ping initially. Session reuse amortizes its measured cost without sacrificing reconnect safety. Any later ping-policy change requires disconnect/restart evidence and must not introduce unsafe automatic write retries.

**Acceptance:** lower no-work query volume and checkout wait, no starvation of any queue, no duplicate delivery/claim, no regression in job readiness, and no lock held during a model/external-file call.

## 11. Verification and rollout

| Gate | Required evidence |
|---|---|
| Response equivalence | Differential comparison of old/new read projections: fields, ordering, counts, filters, statuses, evidence, private-field exclusions |
| Cache correctness | Warm hit, owner switch, logout/revocation, cross-process mutation, rollback, expiry boundary, grade correction, policy change, deletion, interrupted fill |
| Concurrency | Parallel owners; same-owner chat + memory edit + event change; simultaneous prefetch/navigation; multiple worker consumers; stop/delete during generation |
| Query budgets | Assert representative SQL/checkouts and fetched row/byte bounds, including large-history fixtures; count protocol/setup separately |
| Search/index | Exact multilingual/wildcard/search parity and before/after plans on realistic cardinalities |
| Summary repair | Invalid legacy revision schedules one repair; valid replacement invalidates cache; no loss of original conversation records |
| End-to-end reads | Cold/warm navigation for every affected route and direct deep link; first understanding page no longer waits behind overview |
| Failure handling | Database outage/reconnect, pool saturation, timed-out prefetch, stale cursor, optional section failure, interrupted migration |

Ship in small independently reversible groups:

| Group | Work | Exit condition |
|---|---|---|
| 1 | Baseline metrics + read-unit infrastructure + Progress reuse | Equivalent results and measured checkout reduction |
| 2 | Combined identity/onboarding + request-local profile reuse | Same auth/onboarding outcomes with fewer reads |
| 3 | Page projections, narrow assessment list, bounded mistakes | Query/payload budgets met and paging/facet parity |
| 4 | Revision-validated profile/summary cache + memory read fast path + repair dedupe | Cross-process/expiry/publication tests pass |
| 5 | Combined fetches + selective prefetch + invalidation hardening | No duplicate fetches or background request burst |
| 6 | Justified indexes + worker/sync contention optimization | Plans and concurrent latency improve without write regressions |

Groups may be subdivided further. Keep old read endpoints/strategies available until parity and performance are verified; use narrow switches where rollback is necessary. Additive cache revisions/indexes can remain while readers roll back. Do not roll back by deleting canonical history or evidence.

## 12. Expected outcome and explicit exclusions

The most defensible first gain is fewer connection checkouts: an isolated experiment already removed roughly two-thirds of the Progress overview business-read latency without changing the 18 queries. Projection reuse, one page fetch, and warm revision-validated context reuse should remove additional work; their exact gains must be measured during implementation.

This plan does not require a database replacement, Redis, an async-driver rewrite, a bigger server, relaxed freshness, removed safety locks, larger model-context limits, or a UI redesign. Those are not substitutes for eliminating the measured redundant database work.
