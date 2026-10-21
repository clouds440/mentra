# Database fetch latency audit

**Date:** 21 October 2026 · **Scope:** read-only investigation of the local application, its configured remote PostgreSQL database, page-loading code, and per-prompt context reads.

This document records the **baseline before implementation**. Current changes and verification are recorded in the [implementation report](Database_Query_Optimization_Implementation_2026-10-21.md).

**Conclusion:** the dominant repeatable bottleneck is many small, sequential database transactions over a remote connection. PostgreSQL executes the sampled list/profile queries in less than 0.1 ms; the application spends hundreds of milliseconds obtaining the same results. Progress multiplies this overhead through repeated repository sessions and repeated retrieval work. Historical connection failures and lock waits explain additional risk and some variability, but their contribution to individual long requests is not fully attributable with existing instrumentation.

No application code, configuration, records, indexes, jobs, or running services were changed during this investigation. The separate [optimization plan](Database_Query_Optimization_Plan_2026-10-21.md) proposes implementation work.

## 1. Evidence and measurement boundaries

| Evidence | Method | Boundary |
|---|---|---|
| Running services | Container status and one resource snapshot | All seven services running; backend/frontend healthy; low CPU usage at observation time |
| Database connection | Read configured host/port without printing credentials | Backend connects to `aws-0-ap-south-1.pooler.supabase.com:5432`, rather than a local PostgreSQL service |
| Query costs | Bounded SELECTs, SQLAlchemy events, protocol timings | Diagnostic connections enforced `default_transaction_read_only=on` |
| PostgreSQL execution | `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on three SELECTs | Actual small dataset; not a large-data benchmark |
| Endpoint costs | Isolated FastAPI harness using real handlers/repositories and database | Identity dependency injected; actual authentication lookup retained against a stored session reference; no login/session creation; excludes live middleware, browser, and HTTP transport |
| Historical requests | Parsed all five available log files, 16–21 October | Mixed application versions; sample sizes below; not a controlled load test |
| Aggregate SQL statistics | `pg_stat_statements`, locks, table/index metadata | Cumulative statistics since 7 October; not current rates or proof of a specific request's cause |
| Session reuse experiment | Isolated learner service using one read session | Same query results/counts; temporary diagnostic process only; not a production implementation |
| Prompt-context behavior | Source trace plus repeated read-only profile/history/summary reads | No model invocation, paid call, user prompt, repair enqueue, or summary regeneration |

An early diagnostic JSON serializer could not serialize datetimes in the memory/event result dictionaries. Those were harness serialization errors, not application endpoint failures. The later real route harness returned HTTP 200 for both paths.

## 2. What is actually slow

### Network and transaction overhead

| Measurement | Observed result |
|---|---:|
| New engine's initial connection/setup | 1,177 ms |
| Repeated `SELECT 1` inside an existing transaction | Usually 64–65 ms; occasional 129 ms |
| Pool checkout + trivial SELECT + session rollback | 258–265 ms |
| Warm session authentication repository lookup | 271 ms |
| Warm full profile repository read | 269 ms |
| Warm memory list repository read | 269 ms |
| Connection pre-ping | Approximately 66 ms per reused checkout |
| Commit or effective rollback | Approximately 66 ms per transaction |

The engine enables `pool_pre_ping=True`. The ping is a legitimate reliability measure, but repeating it for every tiny repository session adds another network round trip. The first execute in a transaction also includes protocol/transaction work. Instrumented cursor duration is therefore not equivalent to PostgreSQL execution time. SQLAlchemy documents checkout pings in its [connection pooling guide](https://docs.sqlalchemy.org/en/20/core/pooling.html#disconnect-handling-pessimistic).

The configured Supabase endpoint uses session pooling. This is a valid connection mode for a persistent backend; changing to port 6543 is not an automatic latency fix and requires checking prepared statements and session-dependent behavior. See [Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres).

### Actual database work is small

| Query | PostgreSQL execution | Plan |
|---|---:|---|
| Full profile by learner | 0.035 ms | Index Scan |
| Memory list, newest first | 0.052 ms | Limit → Index Scan |
| Assessment list, newest first | 0.058 ms | Limit → Incremental Sort → Index Scan |

Exact table counts at inspection: **6 assessments, 9 attempts, 1 memory, 0 events, 24 learner states, 5 learning contexts**. Existing indexes cover authentication digest, profile ownership, memory ordering/full-text/trigram search, event agenda ordering, assessment ownership, and attempts by owner/assessment.

There were **zero waiting locks** in the sampled lock snapshot. Database `max_connections` was 60; the sampled activity had roughly 14 sessions, including the diagnostic connection. These observations do not establish peak capacity, but they do not support data volume, a missing basic owner index, or current connection exhaustion as the principal explanation.

### Endpoint and historical request timings

| GET endpoint | Isolated handler timing | SQL statements / checkouts | Historical median | Historical maximum | Historical n |
|---|---:|---:|---:|---:|---:|
| `/memories` | 823 ms | 3 / 3 | 869 ms | 909 ms | 4 |
| `/memories/preferences` | 806 ms | 3 / 3 | 866 ms | 903 ms | 4 |
| `/events` | 1,017 ms | 6 / 3 | 1,081 ms | 1,094 ms | 2 |
| `/assessments` | 1,081 ms | 4 / 3 | 1,314 ms | 17,356 ms | 54 |
| `/assessments/mistakes` | 1,289 ms | 5 / 3 | 1,553 ms | 38,491 ms | 14 |
| `/learning` | 4,817 ms business read only, before auth/profile | 18 / 17 business read only | 5,725 ms | 8,098 ms | 10 |
| `/learning/understanding` | 1,438 ms business read only, before auth/profile | 6 / 5 business read only | 2,086 ms | 3,189 ms | 7 |
| `/learning-contexts` | Not completed in the isolated route harness | Not recorded | 877 ms | 4,311 ms | 91 |
| `/student-profile` | Not measured as a full handler | Not recorded | 570 ms | 10,715 ms | 51 |

Paths above omit the shared `/api/v1` prefix. Historical values come from successful GET requests only. Small sample sizes and version differences limit comparisons. The context-list harness stopped because its deliberately minimal app omitted `rag_service`; this was not a running-application failure.

## 3. Findings, ranked by impact

| ID | Priority | Finding | Evidence / implication |
|---|---|---|---|
| F1 | P1 | Remote round trips are multiplied by per-method sessions | A one-row read costs about 270 ms despite sub-millisecond execution |
| F2 | P1 | Every onboarded request performs authentication and a full profile read in separate sessions | About 540 ms shared overhead before domain work; repeated independently for each page endpoint |
| F3 | P1 | Progress overview duplicates retrieval and transaction setup | Study targets: 5 statements/5 checkouts; relevant-context packet: 13 statements/12 checkouts; overview calls them sequentially |
| F4 | P1 | Progress creates an additional request waterfall | UnderstandingTable mounts only after the overview/context Promise resolves; its fetch starts afterward |
| F5 | P1 | Profile, history, and summaries are re-read for each chat turn | Persistent summaries reduce regeneration work, but do not eliminate repeated database loading |
| F6 | P1 | Memory-summary preparation takes an owner write lock even when serving unchanged context | `context()` calls `lock_owner()`, which inserts-if-missing and selects `chat_sync_state FOR UPDATE`; this shares serialization with chat/activity/domain writes |
| F7 | P2 | A stored chat summary is incompatible with current limits | Existing summary: 2,465 characters/639 tokens; current limits: 2,400/600; `valid_content()` returns false |
| F8 | P2 | List endpoints carry more data than their cards require | Six-assessment HTTP response approximately 50 KB; repository loads complete assessment JSON and grade histories for the page |
| F9 | P2 | Mistake pagination occurs after full history reconstruction | `collect()` loads all owned graded assessment sources/attempts, expands history, builds facets, sorts, then slices 30 items |
| F10 | P2 | Event/inbox reads spend separate round trips configuring snapshots and timeouts | Event list uses two SET statements before watermark/page queries; consistency is intentional and must remain |
| F11 | P2 | Active chat monitoring adds repeated database traffic | Each loop sleeps 0.5 seconds, then reads active-turn state and memory freshness in separate repository sessions; actual interval includes read time |
| F12 | P2 | Worker polling and a small shared worker pool can amplify waits | Assessment process has four consumer loops sharing a pool of one connection; cumulative statistics show large numbers of empty queue polls |
| F13 | P2 | Cache invalidation can leave obsolete network work running | Page cache removes pending entries without aborting their controllers; replacement loads can overlap obsolete work |
| F14 | P2 | Existing metrics cannot completely explain long-tail requests | Successful SQL timings are DEBUG-only; no complete checkout/pre-ping/connect/transaction/fetch timing breakdown in normal request logs |

### Controlled proof for F1/F3

| Operation | Current session pattern | One shared read session | Same SQL count | Reduction |
|---|---:|---:|---:|---:|
| Progress overview business read | 4,817 ms; 17 checkouts | 1,634 ms; 1 checkout | 18 | 66% |
| Understanding business read | 1,438 ms; 5 checkouts | 626 ms; 1 checkout | 6 | 56% |

These are single controlled comparisons, not promised production improvements. The diagnostic temporarily bound the repository in an isolated process. A production solution must use request-scoped repository instances, never mutate the application-global repository's active session.

### Long-tail evidence

On 20 October, assessment/mistake/profile requests clustered around 05:58 PKT with maximum durations of 17.36 s, 38.49 s, and 10.71 s. On 21 October, worker OperationalError events were recorded approximately **11:15–11:32 PKT**: 465 assessment workflow failures, 133 events workflow failures, and 40 RAG workflow failures. Multiple log events describe the same failure, so these are workflow counts, not distinct outage incidents.

Cumulative PostgreSQL statistics also show an advisory-lock statement averaging about 95 ms over 2,595 calls, with a 2.62 s maximum, and a `chat_sync_state` SELECT with a historical 27.77 s maximum. These establish that lock contention has occurred. They cannot prove that a specific affected page request waited on those locks. Ordinary memory/list/profile reads do not all acquire these locks.

## 4. Are profile, memories and summaries fetched once per session?

**No. The backend generally loads them again for every new user message.** There is durable reuse of generated summaries and some turn-local tool reuse, but no general revision-validated session cache for these prompt packets.

| Data | Current behavior | Existing reuse / invalidation |
|---|---|---|
| Authentication | Database session lookup for each protected HTTP request | No browser-session-wide bypass of revocation/expiry checks |
| Onboarding profile | Full profile read for each onboarded request | FastAPI dependency reuse applies within one request only |
| High-level prompt profile | `prompt_context()` → `get()` → `read_profile()` each turn | Planner always includes profile, including greetings; can duplicate the onboarding profile read |
| Recent conversation history | `context_rows()` each turn | Up to 256 rows fetched, then prompt budgeting trims selected context; browser chat cache does not serve backend reads |
| Conversation summary | `ConversationSummaries.load()` each turn when enabled | Stored generated prose reused; database ownership + summary reads still run every time |
| Memory summary | Orchestration prepares `summary_context()` every turn when enabled | Stored summary blocks reused; canonical supports/revisions/expiry checked again; dirty deltas can cause extra queries |
| Detailed memory recall | On demand when memory tool runs | Memory search plus another profile read; turn-local tool results can be reused |
| Learner context | Requested for learning/assessment intents | Re-read per relevant turn; query/policy/context dependent |
| Tool result cache | Stored on the turn's scope/budget | Invalidated by domain writes; does not survive as a general conversation-session cache |
| RAG | Embedding/candidate caches exist | Every hit still hydrates and authorizes canonical sources; preserve this behavior |
| Browser page cache | Owner-scoped in-memory GET cache with mutation invalidation | Protects page requests, not backend prompt preparation; served JS contains its cache marker |

Repeated read-only probes confirmed that an unchanged second call still executed SQL:

| Read | Second-call wall time | SQL statements |
|---|---:|---:|
| Recent chat context | 341 ms | 2 |
| Stored conversation summary | 336 ms | 2 |
| High-level prompt profile | 268 ms | 1 |

History loading and conversation-summary loading occur sequentially before orchestration's parallel preparation. Profile and memory-summary preparation overlap with other independent reads, but still use database capacity.

The invalid stored conversation summary is rejected by the higher-level load path, which calls the durable repair method and returns no summary. There were no chat-summary repair jobs in the inspection snapshot. Thus the next affected load can enqueue repair; the investigation did not trigger that write. Until repair succeeds, prompt assembly can retain a larger unsummarized suffix. The measured 336 ms above is the underlying repository load, excluding validation-triggered repair.

Database caching and model context are separate: reusing a cached profile/summary can avoid fetching it again, while the server still includes the required current context in each model request.

## 5. Source map

| Concern | Source |
|---|---|
| Pool and database budgets | [database.py](../backend/app/db/database.py), [Compose](../docker-compose.yml) |
| Authentication and onboarding | [auth dependencies](../backend/app/auth/dependencies.py), [identity repository](../backend/app/auth/repositories/postgres.py), [profile dependency](../backend/app/student_profile/dependencies.py), [profile repository](../backend/app/student_profile/repositories/postgres.py) |
| Progress composition and retrieval | [learning routes](../backend/app/api/routes/learning.py), [retrieval service](../backend/app/learner/retrieval.py), [repository session scope](../backend/app/learner/repositories/postgres_parts/base.py) |
| Browser fetch composition | [LearningProgress](../frontend/src/components/learning/LearningProgress.tsx), [MemoriesSettings](../frontend/src/components/memories/MemoriesSettings.tsx), [AssessmentWorkspace](../frontend/src/components/assessments/AssessmentWorkspace.tsx), [pageCache](../frontend/src/services/pageCache.ts) |
| Assessment payload/history | [assessment repository](../backend/app/assessments/repositories/postgres.py), [mistake reconstruction](../backend/app/assessments/repositories/revision_practice.py) |
| Event snapshots | [event repository](../backend/app/history_management/repositories/events/postgres.py) |
| Per-turn preparation | [chat service](../backend/app/chat/service.py), [orchestration](../backend/app/langchain/orchestration_service.py), [planning](../backend/app/langchain/planning.py) |
| Summary persistence/freshness | [chat summaries](../backend/app/chat/summaries.py), [summary repository](../backend/app/chat/repositories/summaries.py), [memory summary repository](../backend/app/history_management/repositories/memory_summaries.py) |
| Existing tool/RAG reuse | [tool executor](../backend/app/langchain/tool_execution.py), [RAG service](../backend/app/rag/service.py) |

## 6. Limits of the conclusions

The audit did not record an authenticated browser waterfall, run a multi-user load test, access Supabase infrastructure metrics, change region/connection mode, or attribute every historical spike. New index benefits at production scale remain unmeasured. Library and Notifications were traced at source level but not benchmarked as complete page handlers. The optimization plan distinguishes measured fixes from conditional changes requiring further evidence.
