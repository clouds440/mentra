# Backend Optimization, Bugs, and Gaps: Fix Plan

Audit date: 2026-10-14, Asia/Karachi. Repository: `C:/Users/Xclouds/Documents/mentra`. Reviewed revision: `9883ce7115837ddddc49554e4fe86dfc781dfbd5`.

Status: implementation and local regression verification completed in the workspace. The user authorized implementation and tests after each fix, and approved a 30-day absolute lifetime for new persistent sessions only. Application code and repository deployment configuration have changed; the application database, existing application volumes, and deployed application containers have not been modified. See the implementation ledger below for the current result, conservative optimization scope and remaining rollout prerequisites. The original audit and baseline evidence remain below as historical context.

Findings after verification: **36 actionable: 6 P1/high, 27 P2/medium, 3 P3/low**. Original F12 and F29 were withdrawn; F38 was added from actual test failures. IDs remain stable for traceability. Each active finding includes current risk, a targeted solution, cross-module impact, change risk, and acceptance checks.

## Implementation Ledger

Implementation proceeded through high-priority availability/correctness work, medium-priority recovery and resource work, then lower-priority runtime hardening. Focused tests were run after each fix; failures discovered by the wider suites were corrected and retested. Counts below describe individual focused runs and overlap; they must not be summed into a full-suite total.

| Finding | Applied Fix | Regression / Cross-Module Check | Remaining Change Risk |
| --- | --- | --- | --- |
| F01 / P1 | Normalize typed tool failures; retain partial event saves and propagate lifecycle failures through approval gates | Event capture, recovery and auto-approval: 27 passed in the latest focused group | Medium: event writes and chat error policy interact; uncertain writes still are not automatically replayed |
| F02 / P1 | Offload complete profile SQL transaction units, not individual statements | Async heartbeat/thread checks plus profile/calibration/evaluation regressions | Medium: model calls remain outside transactions; cancellation does not imply a committed write was undone |
| F03 / P1 | PostgreSQL admission leases and bounded hashed account/IP rate buckets before expensive authentication | Auth/admission/session group: 50 passed; rejection verified before hashing | Medium: intentional 429 responses; bucket collisions can conservatively reject unrelated clients during the 60-second window |
| F04 / P1 | Round-robin owner selection with durable reminder retry backoff | Events/notifications group: 30 passed; blocked inbox does not starve another owner | Medium: delivery eligibility and lifetime notification receipts preserved |
| F05 / P1 | Role-specific pool, checkout, connection, query and lock bounds; typed database-busy errors | Database/tool-recovery group: 47 passed; migration and architecture checks | High: size aggregate connections for the actual deployment; migrations use a separate unbounded-query engine |
| F06 / P1 | Durable model/parse/upload capacity, completed-replay bypass, lease release and disconnect-safe chat admission | Chat admission/recovery group: 41 passed, including disconnect during admission | High: accepted work remains durable; excess new work gets 429 instead of creating abandoned RUNNING state |
| F07 / P2 | Bound public MCQ explanation including the prefix without changing the stored answer | Boundary and retry grading tests | Low: assessment/evidence grading semantics remain unchanged |
| F08 / P2 | Public batch canonical-ID resolution for requested, document and hydrated chunk tags | Real merge plus warm-cache retrieval; later RAG group: 47 passed | Medium: current authorization and historical chunk/source identity retained |
| F09 / P2 | Bounded owner-fair scans and nonblocking existing-owner locks for grading/evidence claims | Busy-owner and competing-worker tests; narrow attempt projection excludes original BLOBs | High: retains owner-before-write coordination and claim fences; a busy owner is deferred, not bypassed |
| F10 / P2 | Terminal sweep for expired exhausted evidence claims | Four exhaustion/completion/restart tests passed | Medium: live or successfully completed claims are not overwritten |
| F11 / P2 | Explicit idempotent same-attempt grading retry, bounded to three manual cycles | MCQ/chat assessment group: 23 passed | Medium: preserves original answers, submission and evidence identity; new API operation, not a frontend retry redesign |
| F13 / P2 | Pre-parser JSON byte limits and bounded answer count/key/text | HTTP limits: 16 passed, including the largest valid escaped Unicode answers | Medium: oversized requests intentionally fail early; valid published assessment capacity remains supported |
| F14 / P2 | Existing profile read uses a single read-only projection; initialize only if absent | Profile/onboarding read and provisioning tests | Low: existing calibration gate and initialize-once behavior retained |
| F15 / P2 | Profile mutation and evidence projection share the established owner lock ordering | Profile/grading group: 39 passed | High: shared transaction coordination changed; version fences and user edits retained |
| F16 / P2 | Retry transient watcher errors; stop generation after repeated loss of monitoring | Watcher/stream/recovery group: 36 passed | Medium: prevents an unmonitored generation; activity-only outages remain distinct |
| F17 / P2 | Consistent read-only status snapshot; owner-locked recheck only for expired leases | Status/Stop/stream group: 40 passed | Medium: no cross-request personal-response cache; ordinary polls no longer take exclusive owner locks |
| F18 / P2 | Metadata projections omit original/extracted BLOBs; inspect only a 12-byte SQL header when required | Attachment/Library group: 42 passed | Low: original download bytes and extraction reuse retained |
| F19 / P2 | Scheduled bounded inactive-owner cleanup of old unbound attachments | Maintenance/attachment group: 19 passed | Medium: owner locks protect binding; bound originals are not swept |
| F20 / P2 | Revalidate Library replay against live document/context policy | Image/RAG group: 47 passed; orchestration fixture correction: 12 passed | Medium: deleted or changed receipts return explicit errors, never silently recreate material |
| F21 / P2 | Batch notification deletion and tombstones with one floor prune | Notification group: 11 passed; 100-item prune uses fewer than 25 SQL statements | Medium: contiguous sync revisions and lifetime delivery receipts retained |
| F22 / P2 | Independently degrade dense/lexical retrieval with truthful warnings | Five focused outage/cache/citation tests passed | Medium: neither partial candidates nor warnings are hidden by cache; both branches failing still returns 503 |
| F23 / P2 | Narrow scope projection, candidate-only final checks, bounded directory/key sweep and staged-upload file guard | Storage guard plus upload/replay/delete/shutdown: five passed on Windows | Medium: cleanup cannot remove an in-flight unpublished upload; initial exact retrieval scope remains proportional to eligible documents |
| F24 / P2 | Scope progress factors to requested concepts and paginate context rows in SQL | Learner/progress group: 17 passed | Medium: exact recommendation ranking intentionally still scans its full eligible collection; no approximate top-K cap |
| F25 / P2 | Batch concept names/relationships/context links; refresh stale state in bounded transactions | Learner/topic/progress group: 42 passed | Medium: public domain facades and evidence/mastery semantics retained |
| F26 / P2 | Resource deadlines, reaped document children, killable reusable embedding/reranking workers and bounded waits | Process timeout/restart tests; actual baked embedding numerical-equivalence and shutdown checks passed | High: cold initialization is separately bounded; no guarantee that arbitrary threaded work is forcibly cancelled |
| F27 / P3 | Separate document CPU/memory/wall budgets and report extraction capabilities | Documents/vision group: 50 passed; actual Linux OCR and CPU enforcement passed | Medium: English OCR capability is explicit; no multilingual accuracy claim or reader-policy revision change |
| F28 / P2 | Shared no-store policy for private API successes/errors/SSE | Header/stream group: nine passed; browser consumer regressions | Low: health endpoints are intentionally excluded |
| F30 / P2 | Approved 30-day absolute expiry for new persistent sessions; bounded dead-session cleanup | Auth group: 23 passed; browser expiry assertion updated | Medium: existing unlimited sessions remain untouched |
| F31 / P2 | Read-only database/Qdrant readiness and durable worker heartbeats | Readiness/Qdrant/database/architecture group: 16 passed | Medium: readiness detects stale workers; liveness remains a process check |
| F32 / P2 | Shared Compose model/runtime configuration across applicable roles | Deployment/model configuration: six passed | Medium: repository parity tested; deployed environment overrides were not changed |
| F33 / P3 | Lifecycle-owned HTTP transport pooling for research/MCP | Provider/quota/cancellation group: 29 passed | Low: fresh per-call MCP session retained for task ownership safety; remote cold/warm latency not benchmarked |
| F34 / P2 | Content-free exception/category/frame diagnostics and bounded validation metadata | Diagnostics group with database enabled: 30 passed | Medium: removes arbitrary exception text while retaining type/code/SQL state; operational detail is intentionally reduced |
| F35 / P2 | Byte-bounded logs, daily/retention caps, bounded close and scheduled candidate cleanup | Memory/logging/notification group: 55 passed | Medium: full log sinks may drop diagnostics; confirmed/pinned memory and scheduler receipt retention preserved |
| F36 / P2 | Revision-aware migration fixtures and checked-in full backend CI gate before migration workflow | Events/migration/configuration group: 37 passed | Medium: local migration regressions verified; GitHub workflow has not been executed remotely |
| F37 / P3 | Non-root UID/GID 10001 image, owned private writable paths and read-only baked models | Final image built; five actual runtime checks passed; synthetic legacy-volume ownership/hash rehearsal passed | High at rollout: existing root-owned volume permissions must be prepared before switching users |
| F38 / P2 | Canonical UTC policy timestamp serialization | Learner engine/persistence group: 32 passed under mixed-offset sessions | Low: numeric mastery, evidence and equal-instant interpretation unchanged |

### Final Verification

- Final Linux image: **680 backend tests passed, no failures/errors/skips, in 350.197 seconds**, against disposable PostgreSQL 17 using production Python 3.12 dependencies and pinned CPU Torch 2.6.0. Coverage includes domain boundaries, migrations, authentication, learner/evidence, assessment, events, notifications, RAG, chat, documents, speech, web-provider fixtures and observability.
- Browser regression run: **21 passed in 1.8 minutes** for authentication, profile/calibration and chat assessments; **57 passed in 4.0 minutes** for Library, Progress, notifications, chat history/cache/images/interactions and tool recovery. These are two separate non-overlapping selected runs, not the entire frontend suite. A fresh **four-test chat acceptance/recovery run passed in 50.6 seconds** after the final provenance fix; those four overlap the preceding browser coverage and are not additional unique checks.
- Final rebuilt image runtime acceptance: **5 passed in 20.702 seconds**, including real offline inference/OCR, numerical embedding equivalence, non-root private storage, speech startup/shutdown and CPU-limit termination; no leaked-semaphore warning on this run.
- Windows post-restart focused storage/upload/idempotency/shutdown checks: **5 passed in 10.255 seconds**. The interrupted predecessor could not connect to its stopped test database and is not counted as a successful run.
- Earlier broad runs identified stale fixture assumptions (masked disposable database URL, a missing live-document mock and an optional embedding-close facade). A subsequent 680-test run found one actual regression: disconnect-safe admission changed the persisted chat-origin workflow ID. The service now passes the captured request provenance through admission into both new/retried durable turns; **36 focused admission/chat/watcher/logging tests passed in 20.166 seconds** after the correction. Only the final full-suite result is the acceptance total.
- `git diff --check` passed. Evidence is retained in ignored `.cache/backend-audit/final-image-tests.log`, `runtime-hardening.log`, `browser-regressions.log`, `browser-cross-module.log`, `browser-final-chat.log` and `chat-origin-regressions.log`. The isolated test servers and synthetic legacy volume were cleaned up after verification; no application environment was deployed or migrated.

### Rollout and Residual Scope

1. Apply migrations `20261014_0019` through `20261014_0022` in order with the repository migration runner before starting code that uses admission, reminder retry, grading retry and worker heartbeat tables/columns. Tests use disposable schemas only; production migration has not been performed.
2. Prepare ownership/access for existing material/log volumes for UID/GID 10001 before deploying the non-root image. The rehearsal used a synthetic legacy volume and preserved its original-byte hash. Existing application volumes were deliberately not changed. A rollout without this step can break uploads or original-source reads.
3. Review pool budgets against total API replicas and workers. Defaults are five pooled plus five overflow connections per process, approximately 40 across one API and three worker processes, before migration/admin connections. They are configurable safeguards, not a universal optimal capacity setting.
4. New overload behavior is intentional: bounded waits, explicit 429/503 responses and durable retry/backoff replace unlimited queuing. Fixed hashed authentication buckets bound anonymous cardinality but can produce conservative collisions. Do not trust arbitrary forwarded-IP headers without a separately configured trusted proxy.
5. Existing persistent logins remain valid under their prior policy; only newly issued persistent sessions get the agreed 30-day absolute deadline. No existing user sessions were migrated or revoked.
6. Exact full-scope retrieval and recommendation semantics are preserved. F23/F24 reduce transferred payloads and unnecessary factor work, but do not make every full-scope request constant-time. F33 pools transport connections without sharing a task-owned MCP session. Further indexing/ranking/session changes need workload measurements and a separate safety decision.
7. Local tests reduce regression risk; they cannot prove zero cross-module effects. No paid provider calls, production concurrency benchmark, remote Qdrant payload-index benchmark, deployed-volume migration or remote CI run is claimed. Offline model results were compared numerically, and original bytes/evidence/citation identities were preserved by regression checks.

### Performance Interpretation

Users should see more responsive concurrent profile/chat work, fewer workflow crashes, recoverable grading and more reliable reminders. Under overload they receive an explicit retry response instead of waiting without a bound. New persistent logins require reauthentication after 30 days. Ordinary fast requests are not promised a particular percentage speedup, and provider generation time is not shortened by these changes.

The server should transfer fewer BLOB bytes, hold fewer exclusive status locks, batch pruning/identity work, reuse model/HTTP processes and avoid unlimited expensive-request admission. The measured 100-notification pruning check is fewer than 25 SQL statements; the existing-profile path is one read projection. Hard deadlines cap several runaway resource paths. Added leases, heartbeats and process IPC have small real overhead. Production CPU/RAM/latency percentages remain unmeasured; no numeric speedup estimate is presented as an observed result.

## Original Audit and Baseline

The findings and verification tables below describe the pre-implementation audit revision. Their proposed checks and "remaining before accepting" columns are historical, superseded by the implementation ledger above. In particular, Docker became available during implementation and was used for the isolated Linux checks. The original diagnostic script intentionally expects old defects and is not a post-fix acceptance suite.

## Findings and Evidence Limits

The most urgent problems are broken event-error recovery, synchronous profile database work on the API event loop, absent admission controls for expensive requests, unbounded database waits in several adapters, and reminder starvation across accounts.

Three defects were reproduced with focused local probes:

1. Passing `failure(...)` directly to `remember_failure(...)` raises `AttributeError: 'ToolFailure' object has no attribute 'get'`.
2. A valid MCQ with a 2,000-character model answer fails deterministic grading because adding `Correct. ` exceeds the feedback field's 2,000-character limit.
3. Searching for a merged concept against a document still tagged with the original concept returns `no_eligible_sources`, despite resolving the requested ID to the new canonical ID.

Other findings are marked **source-confirmed**, **operational gap**, or **conditional risk**. Source-confirmed means the relevant branch is present in the current code; it does not mean its frequency or production impact was measured. Conditional risks need the stated reproduction or benchmark before implementation. Operational gaps identify missing safeguards in the repository; an external proxy or deployment policy might supply some of them, but none was assumed.

The initial limitations were investigated and partly resolved. Windows asyncio stalled inside the filesystem sandbox but worked outside it; that was not an application defect. With no configured test database or local server, official portable PostgreSQL 17.11 binaries were downloaded into the ignored audit directory and a new loopback-only cluster was initialized on port 55439. Tests used only its `mentra_audit` database and temporary schemas. The application database was never used.

A fresh Python 3.12.14 environment installed `backend/requirements.txt`. The complete backend suite finished: **637 tests, 634 passed, 2 failures, 1 error, no skips**, in 327.106 seconds. The two failures were reproduced independently and traced to F38. The error is a stale pre-Events migration snapshot test, addressed under F36; it is not evidence that migrations destroy current chat data. **22 diagnostic probes passed**, including real database interleavings and the two withdrawn findings. These diagnostic probes confirm current defects/safeguards, not the safety of future fixes. Counts from overlapping earlier focused runs are not added to the full suite.

Docker remained unavailable and was not needed for the completed local checks. This is Windows/Python 3.12/PostgreSQL verification, not Linux container or deployment verification. Fresh transitive dependency resolution differs from the existing environment, and the verification environment's resolved Torch is not the Dockerfile's separately pinned 2.6.0. Baked model inference, actual remote Qdrant payload-index behavior, Linux resource limits, production load and browser integration are not covered by a local fixture passing. No paid model/search call was made.

No critical/P0 defect is asserted. The report does not claim that every possible backend defect has been found or that applying an untested fix guarantees zero regressions.

## Severity and Risk

| Severity | Meaning |
| --- | --- |
| P1 / High | Prioritize before increasing usage: shared availability, serious workflow failure, or missing abuse protection. |
| P2 / Medium | Correctness, recovery, privacy, or scaling issue with a narrower trigger or impact. |
| P3 / Low | Operational hardening or optimization that needs measurement or policy agreement. |

Each finding separates **current risk** from **change risk**. Change risk is the chance that the proposed fix alters another workflow. Low means local behavior with stable contracts; medium means shared callers or response behavior; high means shared transactions, lifecycle, deployment, or persistent-data changes.

## Module Coverage

The inventory contains 311 Python files under `backend/app`, 64 Python test files, and 18 Alembic revisions. Review followed public routes through services, adapters, workers, schemas, and tests. It was a module-level source audit, not a completed live penetration test or performance benchmark.

| Module | Areas Reviewed | Findings |
| --- | --- | --- |
| `api` | All registered feature route modules, dependencies, validation, upload middleware, SSE, pagination, health | F02, F03, F06, F13, F28, F31; F12/F29 withdrawn |
| `auth` | Password hashing, assertion trust, provisioning, token digests, cookie origin checks, session lookup/revocation | F03, F30 |
| `student_profile` | Factual edits, calibration snapshots, atomic completion, evaluation claims, projection adapter | F02, F14, F15 |
| `learner` | Identity/candidates, contexts, immutable evidence, corrections, state refresh, scoring, recommendations, ontology lifecycle, evaluation | F08, F15, F24, F25, F38 |
| `chat` | Durable turns, retries, Stop, deletion, summaries, attachment lifecycle, status and activity repositories | F06, F16-F20, F28 |
| `interactions` | Option validation, canonical answer mapping, card persistence and choice limits | F06, F13; no separate card-validation defect established |
| `langchain` | Planning, provider factory/invocation, budgets, discovery, staged reads, recovery, caches, domain tools, grading, evidence queue, checkpointer | F01, F06-F11, F16, F25, F26, F32 |
| `history_management` / memory | Admission, provenance, receipts, suppression, expiration, canonical history lookup, maintenance | F05, F17, F28, F35 |
| `history_management/events` | Temporal/DST rules, CRUD/replay, proposals, decision claims, reminders, sync | F01, F04, F09, F31 |
| `notifications` | Transactional publication, lifetime receipts, capacity, pruning, preferences, pagination, sync | F04, F21 |
| `assessments` | Generation claims, drafts/publication, typed/uploaded answers, transcription confirmation, grading, correction history, worker recovery | F07, F09, F11, F13, F15, F26, F32; F12 withdrawn |
| `rag` | Upload/versioning, quotas, extraction reuse, chunking, embeddings, vector identity/indexing, hybrid search, final authorization, caches, cleanup | F08, F18, F20, F22, F23, F26; F29 withdrawn |
| `documents` | Content detection, native readers, extraction isolation, output limits, embedded-image OCR | F06, F26, F27 |
| `vision` | Raster limits, Tesseract/Poppler, chat preparation, answer extraction/confirmation | F06, F26, F27, F32 |
| `speech` | Upload bounds, decoding, duration limits, worker reuse, busy rejection, deadline/kill behavior | F06, F31; existing single-worker and decoded-duration controls should be retained |
| `web_search` | Keyless MCP/research transports, URL normalization, dated results, durable quota reservations, cache-fill coordination | F33; preserve existing cross-worker quota and ambiguous-send accounting |
| `core` / observability | Settings, exception envelopes, tracing, payload shape capture, file logging, timing, shared read cache | F05, F26, F28, F34, F35 |
| `db`, schemas, migrations, deployment | Pools, owner transactions, migration lock/topology, error contracts, Docker/Compose, CI | F05, F13, F15, F30-F32, F36-F38 |

## High-Priority Fixes

### F01 - Event-capture error recovery throws a second exception

**Severity:** P1. **Evidence:** reproduced; source-confirmed. **Current risk:** an optional event dependency failure can fail the entire chat response, including a response after an earlier event was saved.

- **Location:** `backend/app/langchain/orchestration_service.py:139`, `backend/app/history_management/events/proposal_service.py:85`, `backend/app/langchain/tool_execution.py:103`.
- **Cause:** `failure()` returns a Pydantic `ToolFailure`; both `remember_failure()` and the event-result consumer expect dictionaries and call `.get()`.
- **Fix:** normalize failure receipts at the boundary, using `model_dump()` or a narrowly typed normalization helper. Make `capture()` consistently return its declared result shape. Retain successful saved-event results when another candidate fails, and propagate intentional Stop/deletion/stale-attempt errors rather than degrading them.
- **Cross-module impact / change risk:** low to medium. Touches Events-to-orchestration receipts and warning projection, not event business persistence. Keep `effect_certainty`, public error text, saved IDs, and warning limits intact; do not convert an uncertain write into a successful or safely replayable write.
- **Acceptance:** capture-wide timeout, per-candidate exception, mixed saved/failed candidates, disabled capture, and stopped attempts must produce a valid reply or the intentional lifecycle error. Run event-capture, tool-recovery, persistent-chat, and workflow-tool tests.

### F02 - Async calibration/evaluation runs blocking SQL on the event loop

**Severity:** P1. **Evidence:** source-confirmed. **Current risk:** slow SQL or a profile advisory-lock wait blocks unrelated requests, SSE delivery, cancellation, and health handling in the same API process.

- **Location:** `backend/app/student_profile/calibration/service.py:70`, `:120`; `backend/app/student_profile/evidence_service.py:42`, `:69`, `:78`; async callers in `backend/app/api/routes/student_profile.py`.
- **Fix:** extract prepare/claim/apply/failure transactions into synchronous methods and await each through the existing threadpool helper. Keep provider work between transactions. Never open a session on one thread and resume using it on another.
- **Cross-module impact / change risk:** medium. Calibration, onboarding, profile estimates, and chat's onboarding gate consume these results. Preserve one atomic Finish submission, evidence identity, context-version fencing, apply-once claims, and existing response schemas.
- **Acceptance:** deliberately hold a profile lock while unrelated health/chat/SSE requests remain responsive. Race completion, context edits, cancellation, retry, and duplicate evaluation with real PostgreSQL. Run profile, onboarding/chat-gate, and evidence-projection tests.

### F03 - Authentication has no repository-backed abuse admission

**Severity:** P1. **Evidence:** operational gap. **Current risk:** repeated login/register requests can consume Argon2 CPU/memory and support password guessing; correct dummy-hash timing protection does not provide throttling.

- **Location:** `backend/app/api/routes/auth.py:12`, `:21`; `backend/app/auth/service.py:36`, `:44`; `backend/app/auth/passwords.py`.
- **Fix:** admit requests before expensive hashing/verifying, with bounded global capacity and account/IP-aware rate controls shared across API processes. Keep a bounded anonymous key space, trusted-proxy handling, expiry, and generic authentication failures.
- **Cross-module impact / change risk:** medium. Authentication is shared by every module. Preserve bearer/cookie transports, origin checks, legitimate retry behavior, and identity uniqueness. Avoid permanent account lockouts or attacker-controlled unbounded limiter records.
- **Acceptance:** parallel guessing/registration load receives controlled 429s while existing authenticated users remain responsive. Verify multi-process enforcement, valid login after cooldown, forged forwarding headers, and no username/credential leakage. See OWASP authentication guidance below.

### F04 - Full notification inboxes can starve other users' reminders

**Severity:** P1. **Evidence:** source-confirmed branch; database reproduction pending. **Current risk:** the oldest 50 due rows can repeatedly fill the reminder worker batch. Capacity failures leave those rows pending, so newer deliverable reminders are never selected until the blocked events expire or capacity recovers.

- **Location:** `backend/app/history_management/repositories/events/postgres.py:295`, especially selection at `:302` and capacity handling at `:331`.
- **Fix:** add bounded retry scheduling/backoff and fair admission across owners, so blocked rows leave the immediately eligible set. Continue processing independent owners after expected per-item transient failures. Keep capacity failures pending rather than falsely delivered.
- **Cross-module impact / change risk:** high. Events and Notifications share an owner transaction and a lifetime delivery ledger. Scheduling metadata must not create a second reminder or refund/rewrite a delivered receipt. Preserve preference disable/resume and cutoff semantics.
- **Acceptance:** 50 blocked old reminders plus deliverable reminders for another owner must make progress. Rehearse restart, competing workers, lock timeout, full inbox recovery, cancellation, event edit/delete, and deadline expiry; assert one lifetime delivery.

### F05 - Database capacity and wait bounds are inconsistent across adapters

**Severity:** P1. **Evidence:** operational gap. **Current risk:** chat, memory, profile and learner/RAG operations can hold threads or connections for long lock/query waits. Connection acquisition is also unbudgeted at the application layer.

- **Location:** `backend/app/db/database.py:14`; `backend/app/chat/repositories/postgres.py:119`, `:199`, `:274`; `backend/app/history_management/repositories/postgres.py:39`; `backend/app/student_profile/repositories/postgres.py:17`; `backend/app/learner/repositories/postgres_parts/base.py:50`; RAG write transactions.
- **Fix:** expose role-specific pool size, overflow, acquisition timeout and connection timeout. Establish short query/lock budgets per interactive operation, with separate longer worker/replay/migration policies. Map known busy/timeouts to recoverable domain errors. Measure aggregate API-plus-worker connection demand before choosing values.
- **Cross-module impact / change risk:** high. A global five-second timeout could break ingestion, ontology replay, grading or migrations. Preserve current owner-first ordering, learner ontology locks, migration advisory lock, and committed-write receipts; do not replay unknown-outcome mutations.
- **Acceptance:** lock contention and exhausted pools must release resources, return typed outcomes, and preserve committed operations. Run owner-lock/deletion races, migration concurrency, grading rollback, RAG publication/retry and profile tests. Benchmark pool checkout separately from SQL execution.

### F06 - Expensive workflows have no overall owner/deployment admission limit

**Severity:** P1. **Evidence:** operational gap. **Current risk:** one running turn per conversation still allows many simultaneous conversations per owner. Unique assessment request IDs and concurrent attachment/vision requests similarly bypass per-operation claims. Speech has one local worker, but a user can repeatedly monopolize it.

- **Location:** `backend/app/chat/service.py:26`; assessment generation claims in `backend/app/assessments/repositories/postgres.py:47`; document/vision upload routes; `backend/Dockerfile:48`.
- **Fix:** add bounded owner and deployment admission for model generation, parsing/vision, and sustained speech usage. For chat, reserve capacity before durable turn admission, or record an explicit queued/deferred state; never save a RUNNING turn and then silently abandon it. Use durable enforcement where multiple processes are supported.
- **Cross-module impact / change risk:** high. Chat Stop/retry, assessment receipts, uploads, worker throughput and onboarding compete for capacity. Preserve idempotent duplicate requests without charging them twice, useful recovery responses, and disconnect-surviving generation.
- **Acceptance:** many unique chats/assessments from one owner cannot exhaust service capacity for another. Test restart, reservation release, disconnect, Stop, duplicates, burst upload and provider outages. Load-test authenticated flows and verify bounded tasks, memory and connections.

## Correctness and Recovery Fixes

### F07 - Valid long MCQ explanations cannot be graded

**Severity:** P2. **Evidence:** reproduced. **Current risk:** deterministic grading fails and retries an input that can never fit the public feedback schema.

- **Location:** `backend/app/assessments/schemas.py:56`, `:81`; `backend/app/langchain/assessment_workflows.py:112`.
- **Fix:** deliberately bound the public MCQ feedback including its prefix, or define an explicit complete-explanation field with a compatible larger bound. Preserve the stored model answer and grading key.
- **Cross-module impact / change risk:** low to medium. Affects assessment worker output and frontend grade cards. Prefer a contract-preserving bounded projection; any response field/bound expansion requires frontend validation. Do not truncate student answers or change grades/evidence.
- **Acceptance:** correct and wrong MCQs at model-answer boundary lengths must grade once with bounded feedback. Verify mixed written/MCQ attempts, corrections, private-key exclusion and profile/evidence projection.

### F08 - Concept merges make existing RAG tags disappear from focused search

**Severity:** P2. **Evidence:** reproduced with a focused service probe; persistence race/backfill tests pending. **Current risk:** material tagged before an ontology merge no longer appears for the merged canonical concept.

- **Location:** `backend/app/rag/service.py:221`, `:226`, `:308`, `:327`; `backend/app/learner/repositories/postgres_parts/lifecycle.py:20`.
- **Fix:** normalize stored document/chunk tag IDs through a bounded public Learner canonical-resolution contract before comparison, or introduce a domain-owned tag projection update with a safe backfill. Normalize both sides, not only the request.
- **Cross-module impact / change risk:** high if persistence/backfill is chosen; medium for bounded read normalization. Learner owns redirects; RAG owns tags. Preserve immutable evidence, exact historical citations, cache freshness, and scope filtering before candidate selection. Never let RAG query learner tables directly.
- **Acceptance:** tag -> ingest -> merge -> search works with either old or new requested IDs, including warm candidate caches. Test redirected tag chains, mixed concepts, unrelated sources, reindexing, historical citations and concurrent merges.

### F09 - Assessment/evidence workers race for the same queue head

**Severity:** P2. **Evidence:** source-confirmed. **Current risk:** multiple workers select the same unclaimed oldest candidate before acquiring its owner lock. Losing workers return no work and wait two seconds even when other jobs are available.

- **Location:** `backend/app/assessments/repositories/postgres.py:258`; `backend/app/langchain/repositories/evidence.py:39`; `backend/app/assessments/worker.py:54`.
- **Fix:** use a bounded candidate batch and retry other candidates after a failed claim, or design owner-aware nonblocking claims. Acquire the shared owner boundary before feature locks. Do not copy RAG's `SKIP LOCKED` pattern without evaluating the different lock order.
- **Cross-module impact / change risk:** high. Claims fence grading, learner evidence, profile projection and deletion. Preserve lease-token checking, apply-once writes and owner-before-feature lock ordering.
- **Acceptance:** two or more workers process distinct ready jobs without duplicate model work; a busy owner does not stall another. Test deletion during selection, expired claims, rollback, capacity and restart. Benchmark productive claim rate.

### F10 - Third-attempt chat evidence jobs can remain running forever

**Severity:** P2. **Evidence:** source-confirmed. **Current risk:** if a worker crashes during attempt three, `attempts < 3` excludes the expired job from future claims, but no terminal sweep changes its RUNNING state.

- **Location:** `backend/app/langchain/repositories/evidence.py:42`, `:51`. Contrast assessment's terminal sweep at `backend/app/assessments/repositories/postgres.py:261`.
- **Fix:** terminalize exhausted expired claims in a bounded, owner-serialized recovery pass. Clear lease fields and record a diagnostic terminal outcome without applying evidence.
- **Cross-module impact / change risk:** medium. Touches operational job state only; original chat and accepted learner evidence remain authoritative. Do not rewrite applied/ignored jobs or create a fourth automatic attempt.
- **Acceptance:** crash on attempts one, two and three; restart and verify either recovery or terminal failure. Competing sweep/completion must not overwrite successful evidence. Add coverage to chat-evidence jobs.

### F11 - Failed grading has no explicit same-attempt retry operation

**Severity:** P2. **Evidence:** source-confirmed API gap. **Current risk:** after automatic retries are exhausted, the error asks the learner to retry, but submission replay returns the failed attempt and correction accepts only graded attempts. A new attempt changes provenance and forces a different workflow.

- **Location:** `backend/app/api/routes/assessments.py`; `backend/app/assessments/repositories/postgres.py:198`, `:233`, `:303`.
- **Fix:** provide an explicit idempotent retry for a terminal failed grading attempt, resetting only operational claim/retry state after ownership/state checks. Require a new operation receipt and preserve submitted answers, assistance, submission identity and grade revision.
- **Cross-module impact / change risk:** high. Worker, chat cards, attempt lists and evidence correction logic consume attempt state. Retry must never regrade a successfully completed attempt or double-count its evidence. Keep new-attempt and correction behavior distinct.
- **Acceptance:** failed -> retry -> graded without changing original answers/attempt number; duplicate retries, deletion, already-running/already-graded state and completion races produce canonical outcomes. Verify inline frontend retry behavior against the new endpoint.

### F13 - JSON request limits are applied after unbounded parsing/validation

**Severity:** P2. **Evidence:** operational gap and source-confirmed schema gaps. **Current risk:** oversized JSON bodies, unlimited `SubmitAnswers.answers`, long answer values and unconstrained concept-name strings consume resources before repository validation rejects them.

- **Location:** `backend/app/assessments/schemas.py:13`, `:103`; `backend/app/rag/schemas.py` ID arrays; multipart-only limits in `backend/app/rag/upload_limit.py`.
- **Fix:** add endpoint-appropriate JSON transport byte limits, dictionary entry limits, and per-item key/string bounds. Use typed schemas and reject before expensive domain work. Preserve the valid ten-question/eight-thousand-character answer envelope, including UTF-8 and protocol overhead.
- **Cross-module impact / change risk:** medium. Assessments, chat, Events, memory, and clients have different payload sizes; one tiny global limit would reject legitimate submissions. Include multibyte text and both chunked/content-length delivery.
- **Acceptance:** maximum legitimate requests pass; oversized or chunked bodies receive the standard 413/422 contract without provider calls, leaked bodies or temporary-file accumulation. Verify calibration Finish and large handwritten-answer confirmation.

### F14 - Ordinary profile reads take a lock and attempt profile initialization

**Severity:** P2. **Evidence:** source-confirmed optimization issue. **Current risk:** every onboarding-gated request uses the profile write-oriented transaction path, including an advisory lock and `INSERT ... ON CONFLICT DO NOTHING`. Polling and independent context preparation repeatedly pay this overhead.

- **Location:** `backend/app/student_profile/dependencies.py:16`; `backend/app/student_profile/service.py:18`; `backend/app/student_profile/repositories/postgres.py:17`; `backend/app/student_profile/repositories/store.py:19`.
- **Fix:** add a read-only owned profile/onboarding projection; provision missing profiles through the existing serialized write path. Reuse a request-local read where safe. Do not introduce cross-request personal-data caching without a validated revision.
- **Cross-module impact / change risk:** medium. All authenticated domain routes depend on onboarding state. Preserve initialize-once semantics, immediate recognition of completed onboarding, and current profile context/name handling.
- **Acceptance:** repeated profile/onboarding reads issue no insert or exclusive advisory lock for existing rows. Concurrent first access still creates one profile. Test profile edits, onboarding completion and chat gate transitions.

### F15 - Profile edits and grading projections coordinate with different locks

**Severity:** P2. **Evidence:** reproduced with a forced real PostgreSQL interleaving. **Current risk:** profile edits/evaluation use a profile advisory lock; grading/chat evidence projection runs under the chat owner boundary. A concurrent preferred-name edit causes projection to fail with `PROFILE_CONFLICT`. Optimistic versions correctly preserve the edit, but the producer transaction must roll back; unnecessary repeat provider work remains a workflow risk, not a measured provider-cost result.

- **Location:** `backend/app/student_profile/repositories/postgres.py:21`; `backend/app/student_profile/repositories/learning_projection.py:25`; CAS in `backend/app/student_profile/repositories/store.py:31`.
- **Fix:** use the reproduced edit/projection interleaving to make the profile persistence adapter join a consistent shared transaction/lock order, or retry the deterministic projection transaction without rerunning the provider. Preserve version checks as a second fence.
- **Cross-module impact / change risk:** high. Involves profile, owner transactions, learner ontology locks, grading and chat evidence. Document all lock acquisition edges before changing them. No locks across provider I/O; no partial grade/evidence/profile commits.
- **Acceptance:** context edit, estimate evaluation, grading and chat evidence races produce a valid serial result, no deadlock and no duplicate model work solely from projection conflict. Old-context evidence must not affect current estimates.

### F16 - An unexpected watcher error silently disables cross-process Stop monitoring

**Severity:** P2. **Evidence:** source-confirmed. **Current risk:** `_watch_active()` propagates non-lifecycle errors, but generation does not observe the watcher until final cleanup, where exceptions are collected and discarded. Generation continues without its durable cancellation monitor after that error.

- **Location:** `backend/app/chat/service.py:55`, `:97`, `:104`.
- **Fix:** supervise both generation and watcher outcomes. Use bounded retries for transient monitor reads and an explicit policy when activity cannot be verified. Report unexpected watcher failures. Keep durable mutation/publication fences as the final authority.
- **Cross-module impact / change risk:** medium to high. Affects Stop latency, provider cost, tool writes and answer publication. Do not make a reporting-only outage cancel already-committed work or turn a completed answer into failure.
- **Acceptance:** fail the first monitor read, then Stop from another process; verify bounded cancellation and no post-stop publication. Test monitor recovery, prolonged outage, deletion, stale attempts and successful finalization races.

## Optimization Fixes

### F17 - Polling adds repeated queries and exclusive owner-lock contention

**Severity:** P2. **Evidence:** source-confirmed; load impact unmeasured. **Current risk:** every active turn checks durable state every 0.5 seconds; every SSE connection polls each second; status polling takes the shared owner write lock even when no expiry transition is needed.

- **Location:** `backend/app/chat/service.py:59`; `backend/app/api/routes/conversations.py:67`; `backend/app/chat/repositories/activity.py:19`, `:76`; status at `backend/app/chat/repositories/postgres.py:274`.
- **Fix:** measure query/lock cost, deduplicate in-process reads and share activity wakeups where practical while retaining bounded durable checks for cross-process Stop. Use a consistent read projection for ordinary status and acquire the owner lock only for a rechecked expiry transition.
- **Cross-module impact / change risk:** high for status locking. Memory/Events/Notifications writers share this owner boundary. Preserve canonical watermarks, expiry races, SSE reconnect cursors, terminal delivery and deleted-chat isolation.
- **Acceptance:** benchmark multiple tabs/streams per turn and compare query count, lock wait and terminal delivery latency. Stop must remain prompt across processes; stale expiry reads must not fail a newly retried/successful turn.

### F18 - Attachment and Library metadata queries fetch large payloads

**Severity:** P2. **Evidence:** source-confirmed. **Current risk:** attachment bind/detail paths select full rows containing original bytes and extraction JSON. Four maximum-size attachments can transfer roughly 100 MiB during turn binding. Library's `recent(versions, 1)` also selects extraction snapshots before projecting only metadata.

- **Location:** `backend/app/chat/repositories/attachments.py:34`, `:50`, `:77`; `backend/app/rag/repositories/postgres.py:122`, `:137`.
- **Fix:** use explicit metadata projections. Persist the validated media kind needed by bind; load original bytes only for source/extraction/vision use. Select only version summary fields in Library listing.
- **Cross-module impact / change risk:** medium. Attachment ownership/image-count checks, public detail readiness, Library failed-replacement summaries and old citations must retain their behavior. An additive media-kind migration needs a bounded backfill and a safe legacy fallback.
- **Acceptance:** query projections exclude bytes/extracted blocks; metadata response shapes remain identical. Test malformed images, three-image cap, binding races, deleted chats, legacy rows and failed replacement summaries. Measure transferred bytes and peak memory.

### F19 - Unsent attachment cleanup depends on another upload by the same user

**Severity:** P2. **Evidence:** source-confirmed retention gap. **Current risk:** users who upload then abandon chat can leave original BLOBs stored indefinitely; cleanup runs only during a later `create()` for that owner.

- **Location:** `backend/app/chat/repositories/attachments.py:19`; expired binding rejection at `:44`.
- **Fix:** add a bounded scheduled cleanup of unbound expired attachments, with rechecked ownership/binding under the existing owner boundary. Keep the current one-day validity contract.
- **Cross-module impact / change risk:** medium. Composer uploads, quota accounting and first-send binding can race cleanup. Do not purge bound transcript sources or files retained by an assessment/Library workflow.
- **Acceptance:** inactive owners' expired unbound uploads are removed; a concurrently bound file survives. Test maximum-size blobs, quota release, retry, deletion and multiple cleanup workers.

### F20 - Attachment-to-Library replay can return a deleted or outdated result

**Severity:** P2. **Evidence:** source-confirmed. **Current risk:** `library_result` is returned without checking whether the document still exists or whether requested contexts match the original admission. A caller can receive stale success after deleting the Library document.

- **Location:** `backend/app/chat/attachments.py:77`; `backend/app/chat/repositories/attachments.py:71`; RAG replay in `backend/app/rag/repositories/postgres.py:60`.
- **Fix:** retain an admission fingerprint/receipt and revalidate the linked document outcome. Return a typed deleted/changed outcome; require an explicit new operation to recreate a deleted document. Recover the committed RAG receipt if attachment-link storage failed.
- **Cross-module impact / change risk:** high. Crosses two persistence boundaries, chat deletion, RAG quota/idempotency and Library UI. A failed link update must not create duplicate Library documents; retries must not resurrect deletions.
- **Acceptance:** admit -> lost response/link failure -> retry, changed contexts, document deletion, chat deletion and concurrent admissions all recover a truthful outcome with no duplicate or resurrected document.

### F21 - Notification pruning issues many statements while holding the owner lock

**Severity:** P2. **Evidence:** source-confirmed optimization issue. **Current risk:** pruning up to 100 old notifications calls delete and `_change()` per item; each change also updates state and may prune the change log. This lengthens the transaction used by reminder delivery and other owner writes.

- **Location:** `backend/app/notifications/repositories/postgres.py:70`, `:115`; compare Events' `_change_many()` at `backend/app/history_management/repositories/events/postgres.py:47`.
- **Fix:** batch deletion, reserve a contiguous revision range once, insert tombstone changes in a batch, and prune the log once. Keep bounded work and lifetime delivery receipts.
- **Cross-module impact / change risk:** medium to high. Notifications sync/inbox, Events deletion and reminder receipts rely on revision semantics. Preserve one logical deletion change per notification and never delete producer receipts during pruning.
- **Acceptance:** compare old/new sync results, floor/reset behavior and unread counts for 100 pruned items. Test target deletion, old cursors, capacity recovery and concurrent preference changes; assert bounded statement counts.

### F22 - Hybrid RAG cannot use lexical results when dense retrieval fails

**Severity:** P2. **Evidence:** source-confirmed availability gap. **Current risk:** embedding/Qdrant failure raises `RAG_UNAVAILABLE` before lexical retrieval executes, even when current authorized PostgreSQL chunks could answer the request.

- **Location:** `backend/app/rag/service.py:245`, `:261`, `:263`, `:272`.
- **Fix:** handle dense and lexical branch outcomes independently under a shared deadline. Permit explicitly degraded single-branch results when useful; preserve a typed failure if neither branch is available. Do not present fallback scores as dense similarity or cache a partial branch as a complete healthy result.
- **Cross-module impact / change risk:** medium. Chat and grounded assessments consume source packets. Retain final current-scope reauthorization, token limits, exact source provenance and warnings. Decide whether each grounding policy accepts disclosed lexical-only evidence.
- **Acceptance:** embedding failure, vector failure, lexical failure and both-failed cases produce correct result status, score type and citations. Test archive/delete/reassignment during fallback and cache recovery after dependencies return.

### F23 - RAG retrieval and cleanup contain deployment-size reads

**Severity:** P2. **Evidence:** source-confirmed; practical cost needs measurement. **Current risk:** retrieval loads all eligible owner documents, constructs large signatures and generation-ID filters twice. Every cleanup sweep loads every version storage key and scans the entire directory, regardless of its 100-row reconciliation batch.

- **Location:** `backend/app/rag/repositories/postgres.py:417`, `:506`; `backend/app/rag/service.py:217`, `:235`, `:325`; `backend/app/rag/worker.py:107`; `backend/app/rag/storage.py:54`.
- **Fix:** benchmark large collections. Push eligibility joins/projections into bounded queries, use a domain freshness revision where justified, and iterate cleanup in persistent bounded batches with batched existence checks. Never impose an arbitrary top-K document cap that silently omits legitimate sources.
- **Cross-module impact / change risk:** high. Affects RAG cache invalidation, archive/context semantics and private-source retention. Preserve full eligible scope and final authorization; cleanup must recheck before deletion and tolerate concurrent uploads.
- **Acceptance:** large owner/deployment fixtures show bounded memory and sweep duration. Search recall must remain equivalent; concurrent publication/deletion/rename/retag/reassignment invalidates reuse correctly. Pending uploads and immutable old citation sources survive cleanup.

### F24 - Small learner result pages still read/rank the full concept collection

**Severity:** P2. **Evidence:** source-confirmed optimization issue. **Current risk:** recommendation ranking loads all scoped concepts/states, and projecting a small progress page retrieves context factors for every link in its contexts. Bounded response size does not bound backend work.

- **Location:** `backend/app/learner/retrieval.py:23`, `:120`; `backend/app/learner/repositories/postgres_parts/retrieval.py:74`; `backend/app/api/routes/rag.py:48` also paginates contexts after a full read/sort.
- **Fix:** filter context-factor reads to requested concept IDs; move context pagination into its repository/facade. Benchmark recommendations before adding candidate projections or revision-aware reuse. Keep ranking policy in Learner and preserve eligibility-before-top-K.
- **Cross-module impact / change risk:** medium for projections; high for ranking changes. Progress UI, assessment target selection and chat personalization share these reads. Keep exact recommendations, context importance, difficulty support and dormant/archived rules.
- **Acceptance:** 10/50-row progress pages have bounded link projections; recommendations on a large fixture match a full reference calculation. Test unsupported/new concepts, verification eligibility, multicontext factors and changed evidence revisions.

### F25 - Related concepts, identity preparation and stale-state refresh still have N+1 work

**Severity:** P2. **Evidence:** source-confirmed. **Current risk:** related-concept expansion performs relationship and ownership queries per concept; generated assessment preparation fetches names one at a time; a policy change opens a separate replay transaction per stale state.

- **Location:** `backend/app/learner/retrieval.py:88`; `backend/app/learner/state.py:26`; `backend/app/langchain/assessment_workflows.py:35`, `:54`.
- **Fix:** add focused public batch read contracts and batch owned-context/related links. Refresh stale policies in bounded owner-locked batches with progress or a worker for large histories, retaining synchronous correctness for required reads.
- **Cross-module impact / change risk:** medium to high. Learner identity, ontology changes, assessment generation and cache freshness depend on canonical states. Do not parallelize repository mutations on the same session or return stale mastery while claiming current policy.
- **Acceptance:** assert bounded query counts and identical ordering/results, including redirected IDs and archived links. Race policy refresh with evidence ingestion/correction; verify atomic replay and no starvation during large backlogs.

### F26 - Async deadlines do not terminate underlying synchronous work

**Severity:** P2. **Evidence:** reproduced for an already-started synchronous worker; native inference/process variants remain source-confirmed risks. **Current risk:** an `asyncio.wait_for` timeout returns promptly in the tested runtime, but the underlying worker continues until its own operation ends. RAG's inference semaphore waits without a timeout; a hung reranker thread remains alive and future requests fall back indefinitely. The issue is continued resource use, not a claim that every async waiter exceeds its timeout.

- **Location:** `backend/app/core/observability/timing.py:17`; `backend/app/langchain/tool_execution.py:200`; `backend/app/rag/service.py:245`; `backend/app/rag/reranker.py:58`, `:74`; `backend/app/documents/isolation.py`.
- **Fix:** enforce limits at the actual resource boundary: SQL/network timeouts, timed inference admission, cooperative checks, and killable/restartable processes where hard native-inference deadlines are necessary. Drain/reap extraction children on cancellation as well as local timeout.
- **Cross-module impact / change risk:** high. Thread abandonment is not cancellation and is unsafe for writes with unknown outcomes. Preserve committed receipts and source data; do not change the shared threadpool to abandon every operation. Speech's killable worker is a useful existing pattern, not a reason to rewrite every service.
- **Acceptance:** stop/cancel during queued inference, active parse, vector I/O and grading completion; verify bounded CPU/process/thread lifetime and truthful receipts. Test native hangs, worker restart, semaphore release and graceful shutdown in Python 3.12.

### F27 - Document limits and extraction capabilities need a consistent contract

**Severity:** P3. **Evidence:** source-confirmed configuration/capability gap. **Current risk:** the configurable parser wall timeout allows 600 seconds, but the Linux child CPU limit is always 120 seconds. OCR is English-only and some DOCX/PPTX content is explicitly omitted, yet consumers must consistently preserve those limitations.

- **Location:** `backend/app/documents/worker.py:13`; `backend/app/documents/service.py:92`; `backend/app/vision/providers/local.py:37`; DOCX/PPTX reader warnings; `backend/app/rag/service.py:92`.
- **Fix:** define wall-time, CPU and memory budgets separately and pass intended values to the child. Make supported OCR languages/content limitations explicit in the shared capability contract; add multilingual support only where required and evaluated. Preserve extraction warnings in every consuming packet.
- **Cross-module impact / change risk:** medium. Documents feeds RAG, chat OCR fallback and assessment transcription. Changing reader behavior/revisions affects extraction reuse and reindexing. Never let better OCR bypass explicit assessment answer confirmation.
- **Acceptance:** configured resource budgets behave as documented; scanned/mixed PDFs, images, code/HTML and office documents retain warnings and source spans. Verify extraction revision changes, fallback, offline assets and confirmation gates.

## API, Operations, and Security Gaps

### F28 - Personal-response cache protection is inconsistent

**Severity:** P2. **Evidence:** source-confirmed header gap. **Current risk:** ordinary conversation/history/memory/Library JSON and several profile mutation responses lack explicit `Cache-Control: no-store`. Cookie authentication alone does not establish the same cache policy as the protected routes.

- **Location:** `backend/app/api/routes/conversations.py`, `memories.py`, `rag.py`, `student_profile.py`; compare router protection in `assessments.py`, `events.py`, `learning.py`.
- **Fix:** apply a shared authenticated-response cache policy, including error responses and streaming/source responses, without changing intentionally public health routes. Route dependencies alone may not cover exception responses; verify the actual ASGI response headers.
- **Cross-module impact / change risk:** low to medium. Touches HTTP caching, not authorization or the frontend's deliberate account-scoped local data store. Do not accidentally strip SSE headers, downloadable file headers or request IDs.
- **Acceptance:** authenticated success/validation/not-found/error responses consistently carry the intended policy. Test cookie and bearer sessions, streamed terminals, attachments, RAG files, and browser reload/back navigation.

### F30 - Persistent sessions never expire server-side, and old sessions are not cleaned up

**Severity:** P2. **Evidence:** source-confirmed policy/retention gap, not an accidental deviation from current persistence behavior. **Current risk:** cookie-session creation sets `expires_at=None`; a copied token remains usable until explicit logout/revocation, even after browser expiry. Expired/revoked sessions also accumulate.

- **Location:** `backend/app/auth/service.py:41`, `:53`; `backend/app/auth/cookies.py:12`; `backend/app/auth/repositories/postgres.py:69`, `:82`.
- **Fix:** define a product-compatible absolute lifetime and renewal/revocation policy, preserving persistent-login UX. Add bounded cleanup of expired/revoked sessions and, if required, session listing/revoke-other-devices. This policy change needs explicit agreement before implementation; cleanup of clearly dead sessions can be scoped separately.
- **Cross-module impact / change risk:** high. Every module depends on session validity. Avoid unexpectedly logging out existing users; migrate existing persistent sessions conservatively, retain external assertion expiry, and clear expired cookies consistently.
- **Acceptance:** stolen/expired token behavior, renewal, concurrent devices, logout, external sessions and old persistent-session migration are covered. Reauthentication must not alter learner identity or delete domain records. See OWASP session guidance below.

### F31 - Readiness omits database/worker health and can mutate Qdrant

**Severity:** P2. **Evidence:** source-confirmed operational gap. **Current risk:** Compose tests only `/health`, which always returns OK. `/health/ready` checks AI configuration/local embeddings/Qdrant but not a live database or durable worker progress; it invokes collection creation logic from a public diagnostic endpoint.

- **Location:** `backend/app/api/routes/health.py:17`, `:67`; `backend/app/rag/qdrant_store.py:54`; Compose backend healthcheck.
- **Fix:** retain lightweight liveness; make readiness bounded and read-only with core DB connectivity/schema compatibility. Separate optional capability and worker queue-lag/heartbeat diagnostics from core readiness. Move collection creation to controlled startup/operator/worker initialization.
- **Cross-module impact / change risk:** medium to high. Deployment startup, optional-feature availability and worker dependencies change. Do not make disabled web/speech or temporary optional outages block every core route; avoid expensive inference/network initialization in liveness.
- **Acceptance:** unavailable DB, stalled grading/reminder/ingestion worker, disabled optional features and missing Qdrant collection report meaningful states. Repeated unauthenticated health requests cannot create a collection or trigger model loading.

### F32 - Compose gives API and assessment worker different relevant settings

**Severity:** P2. **Evidence:** source-confirmed for nondefault overrides. **Current risk:** the API receives settings such as `AI_TEMPERATURE`, while the assessment worker omits it and uses defaults. Assessment-specific output/vision/model options are not comprehensively passed through either service.

- **Location:** `docker-compose.yml:60`, `:176`; fields in `backend/app/core/config.py`; source-specific budgets in `backend/app/langchain/token_policy.py`.
- **Fix:** define shared reviewed environment groups for the API and relevant workers, plus explicit role-only settings. Pass supported vision/output-budget/recovery settings where consumed. Avoid copying all credentials into workers that do not need them.
- **Cross-module impact / change risk:** medium. Provider behavior, vision uploads, grading budgets and cached model instances change. Distinguish build-time baked model identity from runtime selection; incompatible changes require rebuild/reindex, not just environment edits.
- **Acceptance:** nondefault configuration produces matching intended model/budget behavior across roles, without printing secrets. Test defaults, omitted optional values, model identity, image rebuild and force-recreation in the actual Python 3.12 image.

### F33 - Web provider requests recreate HTTP clients and MCP initialization

**Severity:** P3. **Evidence:** source-confirmed overhead; benchmark needed. **Current risk:** every paid research request creates a new HTTP client. Keyless searches create a client/session and initialize MCP each time; tool schema caching avoids some discovery but not handshakes. Cache-fill deduplication is only in-process, so identical misses across processes can still consume separate quota reservations.

- **Location:** `backend/app/web_search/you_research.py:25`; `backend/app/web_search/you_mcp.py:89`, `:92`; `backend/app/web_search/service.py:48`.
- **Fix:** reuse a lifecycle-owned research HTTP client and measure connection savings. Evaluate transport reuse for MCP with task-owned session enter/exit; do not blindly share an SDK task-group session. Add cross-process cache-fill coordination only if duplicate usage is measured, with leases and truthful unsent/sent outcomes.
- **Cross-module impact / change risk:** medium to high. Search citations, paid research, cancellation and global quota depend on transport certainty. Keep the selected keyless You.com route, fixed-host/credential stripping, byte limits, source/retrieval dates and ambiguous-send charging.
- **Acceptance:** compare cold/warm handshake latency, cancelled waiters, simultaneous misses and shutdown. Cross-process coordination must not release a possibly sent reservation or replay another user's result.

### F34 - Exception string/cause logging can escape content-free diagnostics

**Severity:** P2. **Evidence:** source-confirmed sanitization gap; actual sensitive-data leakage not established. **Current risk:** shape-only payload logging is careful, but `error_metadata()` includes arbitrary exception strings and stringified causes. Pattern redaction cannot guarantee omission of personal answers/source text, especially nested database/provider exceptions.

- **Location:** `backend/app/core/observability/sanitization.py:36`, `:58`; central handlers and tool failure reporting.
- **Fix:** use category-specific safe reason codes/type/frame/SQLSTATE metadata. Apply the same sanitization rules recursively to causes; avoid arbitrary domain-content exception messages and unknown provider/parser bodies. Preserve actionable operational diagnostics without logging learner content.
- **Cross-module impact / change risk:** medium. Support diagnostics and all module error handlers depend on these fields. Keep safe public `AppError` contracts separate from private logs and retain request/workflow correlation.
- **Acceptance:** seed arbitrary personal text and secrets into nested exceptions, validation errors and database causes; assert logs omit content but retain useful category, frames and status. Run observability/parameter-diagnostics tests.

### F35 - Logs and operational retention lack bounded lifecycle behavior

**Severity:** P2. **Evidence:** source-confirmed operational gap. **Current risk:** daily files are never aged/size-pruned; a 4,096-record queue can hold substantial serialized data. `flush()`/`close()` use unbounded joins, so a blocked filesystem lock/write can stall shutdown. Memory maintenance is an operator-only per-owner command, with no repository-provided recurring invocation.

- **Location:** `backend/app/core/observability/files.py:51`, `:108`, `:112`; `backend/app/history_management/maintenance.py`; log bind mount in Compose.
- **Fix:** establish disk/age quotas and bounded shutdown drain with dropped/backlogged-record metrics. Size the logging queue by realistic byte budgets, not only record count. Define bounded scheduling for existing operational maintenance without erasing evidence, suppression or live receipts.
- **Cross-module impact / change risk:** medium. Logging cannot block canonical domain success; retention touches operational history and retry guarantees. Keep live files/receipts safe, preserve multi-process writer integrity, and explicitly define minimum recovery/audit retention before pruning.
- **Acceptance:** full disk, blocked writer, queue overflow, shutdown, midnight and concurrent processes remain bounded. Maintenance cannot resurrect rejected/deleted memories or prune receipts inside their promised replay window.

### F36 - Backend regressions have no checked-in CI gate before live migrations

**Severity:** P2. **Evidence:** source-confirmed CI gap plus one reproduced stale migration-test error. **Current risk:** the only checked-in workflow applies Supabase migrations on `main`, then runs metadata drift checking; no backend test/build/race gate is present. Drift is detected after database mutation, and domain-table changes outside the path filter can miss this workflow. The Events downgrade rehearsal queries `chat_summary` at revision `20261008_0006`, although it was added in revision `20261013_0018`, causing `UndefinedTable` instead of checking historical preservation.

- **Location:** `.github/workflows/supabase-migrations.yml`; `backend/tests/test_events.py:433`, `:444`; `backend/alembic/versions/20261013_0018_chat_summary.py`.
- **Fix:** repair the downgrade test using an explicit reviewed snapshot of the tables/columns present at the historical revision, rather than growing exclusions against mutable current metadata. Then add a Python 3.12 backend validation job with a disposable PostgreSQL database, migration up/down/up rehearsal where appropriate, metadata comparison, focused race tests and production image compatibility. Run validation before the separately authorized deployment/migration step. Review path coverage for every domain table module.
- **Cross-module impact / change risk:** medium. Deployment timing and migration checks change, not application behavior. Test credentials must never target Supabase/application data; do not run destructive downgrade rehearsal against the live database.
- **Acceptance:** corrected historical snapshots pass downgrade/re-upgrade while preserving actual pre-Events memory/chat rows; intentional row loss fails that test. Broken migration/model drift fails before deployment; all domain table changes trigger validation; test failures block the dependent migration job. Verify no secrets/content are printed and migration lock concurrency remains tested.

### F37 - All parsing/API/worker containers run as root

**Severity:** P3. **Evidence:** source-confirmed hardening gap. **Current risk:** the Dockerfile has no non-root runtime user, increasing the impact of a compromised parser/native dependency and complicating shared-volume ownership.

- **Location:** `backend/Dockerfile`; private storage permission changes in `backend/app/rag/storage.py:25`.
- **Fix:** use a dedicated runtime UID/GID after package/model installation and explicitly prepare model, temp, material and log permissions. Add resource limits for roles where appropriate, aligned with parser/inference budgets.
- **Cross-module impact / change risk:** high during rollout. Existing volumes may be root-owned, and all workers share them. Rehearse access/ownership adjustment with preserved data; do not apply recursive destructive permission changes to unrelated host paths.
- **Acceptance:** API, all workers, OCR, Poppler, speech spawn, tokenizer/model loading, migrations, logs and cleanup work as the chosen UID on both fresh and existing-volume fixtures. Verify backup/restore and graceful shutdown.

### F38 - Learner replay changes policy timestamp strings in a non-UTC database session

**Severity:** P2. **Evidence:** reproduced in two existing tests and a focused persistence probe. **Current risk:** stored state and full replay differ solely in policy timestamp representations when PostgreSQL returns aware instants in its session timezone. This breaks replay-equality guarantees and leaves state representation dependent on database session configuration. Numeric mastery and actual instants were unchanged in the reproduced case; this is not an assertion of inaccurate grades.

- **Location:** `backend/app/learner/scoring/mastery.py:66`, `:98`; `backend/tests/learner/test_realistic_learning.py:340`, `:364`.
- **Fix:** canonicalize policy timestamp strings to UTC at the scoring/projection boundary, and decide how existing state projections gain canonical strings. Optionally set application database sessions to UTC as an additional consistency measure, not the sole defense; supplied evidence may legitimately carry another offset.
- **Cross-module impact / change risk:** medium to high. Corrections, out-of-order ingestion, restart/replay, confidence/retention, policy refresh and profile projection depend on Learner state. Preserve immutable evidence timestamps and instant comparisons. Do not change numeric scoring or use a new policy version without considering its replay workload and F25.
- **Acceptance:** both failing tests pass under UTC and Asia/Karachi database sessions; mixed-offset observations replay identically apart from the intentional state version. Verify timestamp consumers, retention, corrections, merges, evidence batches and unchanged numeric outputs.

## Cross-Module Safety Evaluation

The fixes cannot honestly be declared harmless before implementation and regression testing. The source review identifies where to preserve behavior and where changes require broader proof.

| Shared Boundary | Fixes | Contracts That Must Survive | Required Evidence |
| --- | --- | --- | --- |
| Owner transactions / lock order | F04-F06, F09, F10, F15, F17, F19-F21 | Owner before feature lock; no lock across provider I/O; atomic domain receipts | Real PostgreSQL interleavings, bounded waits, rollback, deletion and multi-worker races |
| Canonical learner evidence / identity | F07-F11, F15, F24-F25, F38 | Immutable provenance, effective correction, no invented mastery, redirect resolution, policy freshness, canonical timestamps | Evidence snapshots before/after, duplicate/correction tests, replay equality across database timezones and old-context rejection |
| RAG authorization / private originals | F08, F18-F20, F22-F23, F26-F27 | Current scope check before delivery, candidate-only caching, retained exact citation generations | Warm-cache races, archive/delete/reassignment, retry/cleanup and old citation access |
| Chat transport / lifecycle | F01-F02, F05-F06, F16-F18, F26, F28 | Disconnect survives; Stop fences publication; SSE cursor recovery; truthful committed/unknown outcomes | API/browser Stop/retry/reconnect/deletion tests and multi-process cancellation |
| Browser/API contracts | F07, F11, F13-F14, F20, F27-F28, F30-F31 | Existing response shapes, opaque ownership, one atomic calibration Finish, inline assessment workflow | Schema compatibility, old-client fixtures and targeted browser smoke tests |
| Events / Notifications | F01, F04, F09, F21, F31 | One lifetime reminder, disable/resume cutoffs, delivered outcome immutability, receipt recovery | Temporal/DST, reminder fairness/capacity, preference and delivery races |
| Authentication | F03, F06, F28, F30 | Same learner identity, cookie origin enforcement, bearer compatibility, persistent-login expectation | Auth/onboarding gates, cooldown, expiry migration and session revocation tests |
| Deployment / maintenance | F05, F19, F27, F31-F32, F35-F37 | Production runtime, preserved volumes/history, offline models, serialized migrations | Python 3.12 image tests, disposable migration rehearsal, backup/restore and permission checks |

### Implementation Rules

1. Land local reproduced defects first. Do not combine receipt normalization, locking changes, pagination changes and deployment changes into one patch.
2. Before each patch, inventory all public callers, response consumers, transaction participants and persisted records named in its cross-module impact section. Confirm the relevant baseline tests in Python 3.12.
3. Keep public contracts compatible when possible. Use additive/versioned contracts for pagination, retry and capability changes that existing consumers cannot absorb unchanged.
4. Add migrations only for necessary metadata. Do not rewrite original assessments, student answers, historical grades, immutable evidence or citation generations to make an optimization easier.
5. For lock/queue changes, write the acquisition-order diagram and force the problematic interleaving in real PostgreSQL before accepting the fix. A passing mocked service test is insufficient.
6. Separate reads from writes when cancelling or timing out work. Retry transient reads within their budget; recover durable writes through their receipt/operation ID. Never replay an unknown-outcome mutation automatically.
7. Measure optimization targets before and after: transferred bytes, SQL count, pool/lock wait, CPU/memory, useful queue throughput and user-visible completion time. Keep provider latency separate from orchestration/storage overhead.
8. Deploy one shared-boundary change at a time with an application rollback path. For additive migrations, prefer reverting application behavior while retaining harmless schema additions; never use a destructive downgrade as a generic rollback.

## Fix Order and Release Gates

### Batch 1: Local Correctness

F01, F07, F08, F10 and F38. Establish focused failing tests, apply narrow fixes, then run their direct consumers. F08 may require a separately reviewed public Learner batch contract. Gate: valid chat recovery, MCQ grading, redirected retrieval, deterministic replay and exhausted-job states, with no evidence/source-history changes.

### Batch 2: Availability and Shared Transactions

F02-F06, F09, F14-F17 and F26. Establish connection/worker budgets before changing global policies. F15 now has a reproduced persistence conflict; measure avoidable provider retries before choosing its final recovery strategy. Gate: unrelated owners remain responsive under load, Stop/deletion work across processes, and no committed grade/evidence/event is duplicated or lost.

### Batch 3: History and Resource Efficiency

F11, F13, F18-F25, F27-F28 and F33. Separate compatible metadata optimizations from new API workflows and optional degraded retrieval policy. Gate: existing complete history remains reachable, equivalent ranking/scope, truthful Library replay, fair reminders and lower measured work without lost recall/content.

### Batch 4: Operations and Session Policy

F30-F32 and F34-F37. Agree persistent-session policy before changing it. Add CI checks early enough to validate the previous batches; retain this batch's deployment/runtime verification before rollout. Gate: secrets-safe diagnostics, disposable migration rehearsal, current configuration parity, bounded shutdown/retention and working existing-volume permissions.

### Required Regression Groups

- Authentication and onboarding: `backend/tests/auth`, `backend/tests/student_profile`, chat endpoint/gating tests.
- Chat and orchestration: persistent chat, Stop/interactions, streaming, generation recovery, tool recovery/cache, response latency, titles/summaries and activity tests.
- Learning integrity: `backend/tests/learner`, learning progress, chat evidence, assessment grading/corrections, handwritten confirmation and profile projection.
- Sources: `backend/tests/rag`, embeddings/Qdrant, RAG refinements/prefetch, Documents, Vision, chat images/attachments and source deletion.
- Events/Notifications: Events API/domain/proposals/capture, reminder/notification capacity, sync revisions and temporal behavior.
- Infrastructure: migration concurrency/drift, logging/files/parameter diagnostics, model configuration, speech process lifecycle, web quota/cache/provider cancellation, and the production Python 3.12 image.
- Browser consumers: calibration Finish, persistent chat Stop/retry/SSE reconnect, inline assessment answer/grade/correction/history, Library version/citation/admission, Progress, notification inbox and persistent-login expiry UX for affected changes.

The full dedicated-database suite and image checks must pass before claiming the shared-boundary fixes are safe. Browser checks are required for changed API consumers; performance claims require reproducible benchmark results, not just a passing unit test.

## Verification Results

### Completed Runs

| Run | Environment / Isolation | Result | What It Establishes |
| --- | --- | --- | --- |
| Complete existing backend suite | Windows, Python 3.12.14, fresh declared requirements, disposable PostgreSQL 17.11, Asia/Karachi session timezone | 637 run; 634 passed; 2 failures; 1 error; no skips | Current regression baseline is not green; results include authentication, learner, RAG, assessments, events, notifications, orchestration, speech, documents, logging and migration tests |
| Diagnostic audit probes | Same local runtime, synthetic data, real temporary PostgreSQL schemas, in-memory Qdrant/model fixtures | 22 passed; no skips | Targeted defects, concurrency interleavings, and two false findings tested directly |
| Learner replay failures repeated independently | Dedicated database, Asia/Karachi sessions | Both failed again | Failures are reproducible, not contamination from another suite |
| Same two learner tests with database sessions set to UTC | Only the disposable database's setting changed | Both passed | Supports the offset-string root cause; does not replace the mixed-offset application fix |
| Explicit historical projection downgrade/re-upgrade | Synthetic memory, chat and message rows; target `20261008_0006`, then head | Passed in the diagnostic probes | Those selected pre-Events records survive; original stale test still needs repair and full historical preservation coverage |

Earlier Python 3.14 and overlapping Python 3.12 focused runs passed 124 non-database checks each, and a Documents-only run passed 20. These are supporting environment checks, not extra tests to add to 637. Initial database-missing runs and interrupted sandbox runs are not successes.

### Finding-by-Finding Verification

| Finding | Current Evidence After Verification | Remaining Before Accepting the Fix |
| --- | --- | --- |
| F01 | Failure receipt shape error reproduced | End-to-end partial event success, lifecycle propagation and post-fix chat regressions |
| F02 | Injected 150 ms synchronous transaction delayed an event-loop heartbeat to about 171 ms | Real lock-wait responsiveness and cancellation after offloading |
| F03 | Auth/provider assertion regressions pass; no throttle/admission component exists in reviewed source | Abuse load, external proxy policy and multi-process limiter tests |
| F04 | Two batches of 50 blocked reminders prevented a second owner from receiving a due reminder | Backoff/fairness fix, competing workers and exactly-once ledger tests |
| F05 | Existing migration/owner-race tests exercised real PostgreSQL; interactive adapters still omit consistent resource budgets | Pool/lock saturation benchmarks, typed timeout mapping and per-role budget choices |
| F06 | Per-conversation/operation claims are verified; no overall expensive-workflow admission was found | Owner/deployment saturation, durable admission receipts and capacity release |
| F07 | A schema-valid 2,000-character MCQ answer fails feedback projection | Boundary-compatible fix, grading/evidence/card regressions |
| F08 | Real tag -> ingest -> merge -> focused search changed from one chunk to `no_eligible_sources` | Redirected public batch contract, cache and historical citation regressions |
| F09 | Forced two-worker queue-head selection produced one useful claim for two ready jobs | Nonblocking owner-safe claims and productive throughput measurement |
| F10 | Expired attempt-three evidence job remained running and unclaimable | Terminal sweep, completion race and restart tests |
| F11 | Replay of a terminal failed submission returned the failed attempt without requeueing | Same-attempt retry API and evidence/idempotency regressions |
| F12 | **Withdrawn:** created/listed all 200 permitted assessments and all 20 permitted attempts; extra creation rejected | No pagination expansion planned under current capacity contracts |
| F13 | Request schema accepted 100 answers with 9,000 characters each | Transport byte/item limits and maximum-valid UTF-8 payload checks |
| F14 | Existing profile read issued three statements including advisory lock and initialization insert attempt | Read-only projection, concurrent initial provisioning and onboarding-gate checks |
| F15 | Forced profile edit/projection race raised `PROFILE_CONFLICT`; version fence preserved the user's edit | Producer transaction retry strategy and measured avoidable provider work |
| F16 | Unexpected watcher read failure ended watcher while generation stayed running | Supervision policy, cross-process Stop and reporting-only outage regressions |
| F17 | Existing activity/stream/Stop tests run; repeated polling and status owner-lock paths remain in source | Multi-tab query/lock/terminal-latency benchmark and snapshot-safe read path |
| F18 | Metadata-only attachment detail selected a 1 MiB original BLOB column | Narrow projections, legacy media backfill and transferred-byte measurement |
| F19 | Cleanup remains owner-upload-triggered; attachment/deletion regressions run | Inactive-owner sweep, binding race and retention checks |
| F20 | Stored Library result returned without any RAG call or new-context validation | Lost-link recovery, document deletion and explicit recreation semantics |
| F21 | Lifetime notification receipt/sync tests pass; pruning still changes one item at a time | Batched tombstone equivalence and transaction statement-count benchmark |
| F22 | Dense outage aborted before lexical retrieval despite ready PostgreSQL chunks | Degraded result/citation/cache semantics and grounded assessment policy |
| F23 | Full eligible-document/key reads and directory sweep are source-confirmed | Deployment-size memory/sweep measurements and full-scope recall comparison |
| F24 | Ranking/progress contracts exercised; full-scope factor/ranking reads remain | Large-context query counts and exact ranking/eligibility equivalence |
| F25 | Relevant batch/identity/state tests exercised; remaining N+1 paths source-confirmed | Query-count bounds and policy-refresh/evidence/ontology interleavings |
| F26 | Already-running thread remained alive after the async timeout until explicitly released | Native inference hangs, subprocess reaping, write-outcome certainty and shutdown |
| F27 | Document/Vision fixture tests pass; resource/language limits confirmed in source | Actual Linux CPU/memory behavior and measured OCR language/content support |
| F28 | Actual successful conversation route response lacked `no-store` | Shared success/error/source/SSE header enforcement and browser checks |
| F29 | **Withdrawn:** RAG persistence IDs are `Text`; an unknown non-UUID string returned owned 404 | Preserve text-ID compatibility; no blanket UUID conversion |
| F30 | Existing cookie/bearer/external session tests pass; persistent `expires_at=None` is intentional current behavior | Agreed persistent-session policy, cleanup/revocation and old-session compatibility |
| F31 | Readiness/liveness omissions and collection initialization call source-confirmed | Read-only bounded readiness and worker lag/capability checks |
| F32 | API/worker environment lists compared; missing nondefault configuration paths remain | Role configuration parity in actual deployment/image runtime |
| F33 | Quota/cache/cancellation tests pass; per-call HTTP/MCP setup remains | Cold/warm transport timing and cross-process cache-fill measurement |
| F34 | Arbitrary learner-content marker survived exception-string logging | Category/cause sanitization with retained operational diagnostics |
| F35 | Log queue/shutdown tests run; unbounded sink waits and retention scheduling gaps remain | Blocked/filesystem shutdown, byte budget and receipt-retention policy |
| F36 | One existing downgrade snapshot test errored on absent `chat_summary`; explicit historical core projections survived rehearsal | Repair revision-specific snapshot test, preserve full fixture rows, add CI gating |
| F37 | Dockerfile lacks a runtime `USER`; no container was run | Non-root existing-volume, OCR/model/temp/log/migration verification |
| F38 | Two replay tests failed with non-UTC sessions and passed with UTC; focused differences were two equal-instant timestamp strings, mastery unchanged | Canonical UTC strings, mixed-offset replay and unchanged numeric/evidence semantics |

### Withdrawn Findings

F12 was overstated in the initial audit: capacity limits in `backend/app/assessments/repositories/postgres.py:87` and `:115` make every permitted row accessible through existing listing limits. Introducing new pagination to fix that claimed defect would have changed working API contracts without solving a current problem.

F29 used the wrong persistence-type assumption: generated UUID-shaped strings do not mean UUID-typed PostgreSQL columns. `backend/app/rag/repositories/tables.py:18` declares document IDs as `Text`, as it does for the related RAG entities. The real unknown-ID query returned 404, not a database type error. A blanket UUID boundary change would risk existing text-ID compatibility.

Both IDs are retained only in this verification history and are excluded from the actionable finding/severity counts.

### Reproduction and Artifacts

The historical diagnostic script intentionally asserted pre-fix failures/safeguards at audit revision `9883ce7`; a passing diagnostic run did not mean those failures were fixed. The F38 probe used a non-UTC test connection. The final diagnostic rerun completed all 22 probes in 19.928 seconds with no failures/errors/skips.

The obsolete probe script and ignored audit artifacts were removed during repository cleanup on 2026-10-15. These artifacts included logs, a temporary Python environment, and a stopped disposable PostgreSQL installation containing audit-generated data only, not application backups. The findings and verification history remain in this document.

For current regression acceptance, use `backend/tests` with an explicit disposable `TEST_DATABASE_URL` and `backend/scripts/verify_runtime_hardening.py` for image capabilities. Never substitute an application/Supabase database for the dedicated test target. Historical baseline checks do not replace post-fix acceptance tests.

## Research References

External references support the proposed safeguards and concurrency reasoning, not proof that a production incident has occurred. Repository branches and the probes above establish the local findings.

- Starlette shares a bounded threadpool across synchronous endpoints/dependencies and other framework work; increasing that pool alone does not solve CPU/database overload. [Starlette threadpool documentation](https://starlette.dev/threadpool/).
- Cancellation of an async waiter does not terminate Python work already running in a thread; resource-level deadlines and cooperative/process cancellation are needed. [AnyIO working with threads](https://anyio.readthedocs.io/en/stable/threads.html), [Python 3.12 task cancellation](https://docs.python.org/3.12/library/asyncio-task.html).
- SQLAlchemy pools are configured per engine/process; their sizing and acquisition timeout need to be budgeted with deployment-wide demand. [SQLAlchemy 2.0 pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html).
- PostgreSQL query and lock timeouts serve different purposes, and overly broad settings can interrupt legitimate longer operations. [PostgreSQL 17 client connection defaults](https://www.postgresql.org/docs/17/runtime-config-client.html).
- Login throttling and server-enforced session lifetimes address different risks. [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- Reusing HTTP clients can preserve connection pooling, with explicit lifecycle ownership and closure. [HTTPX async support](https://www.python-httpx.org/async/).
- A dedicated runtime user and reproducible/runtime-aware builds are established container hardening practices. [Docker build best practices](https://docs.docker.com/build/building/best-practices/).

## Findings Not Claimed

The review did not establish a cross-owner data leak, JWT algorithm/key trust bypass, unsafe automatic replay of uncertain writes, duplicate delivered reminders, missing RAG final reauthorization, destructive schema migration, or student-evidence overwrite. Existing source includes safeguards for those areas; the plan explicitly requires retaining them.

The RAG path rechecks eligibility immediately before returning content (`backend/app/rag/service.py:325`). Its candidate cache does not retain content as authorization. No fix should remove that final check merely to reduce a query. The migration runner's nonblocking advisory-lock probes are also intentional; do not replace them with a blocking wait that can deadlock concurrent index builds.

Empirical learner accuracy, multilingual OCR quality, actual production pool pressure, dependency vulnerability status, deployment proxy controls and provider latency were not measured in this turn. They must not be presented as confirmed defects or completed validation.
