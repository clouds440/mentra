# Database query optimization implementation

21 October 2026. Implements the measured portions of the [plan](Database_Query_Optimization_Plan_2026-10-21.md). The [audit](audits/Database_Fetch_Latency_Audit_2026-10-21.md) describes the original behavior.

## Prompt content reuse

Unchanged prompt payloads have **no time expiry**. They remain in bounded process caches until their validity key changes, capacity eviction occurs, or the process restarts. This avoids an unbounded session store or additional infrastructure. Caches isolate owners and return copies.

| Content | Reuse | Refresh/invalidation |
|---|---|---|
| High-level profile | Full profile reused after first read | Version plus creation timestamp detects updates and recreation; missing rows cannot hit |
| Memory summary | Ready summary and support fence reused | Source/summary revisions, prompt/budget settings, canonical support revisions/status, fact expiration and existing reconciliation policy |
| Conversation summary | Stored prose reused | Owner, conversation, revision and covered sequence; deletion/ownership checked before every hit; validation uses current limits |
| Recent history | Reuses prior eligible window; full content fetched only for missing or changed message IDs | Current eligible IDs and content/metadata fingerprints; turn state, stops, deletion, retry boundary and window limits remain authoritative |

Each prompt still performs small authoritative freshness checks. These are necessary to detect changes made by another process or worker without introducing a distributed invalidation system. It no longer downloads unchanged profile/summary/history content on every prompt. Invalid or changing memory state retains the existing safe fallback until a valid summary is published. Normal history growth fetches the new messages.

History and conversation summary preparation share one short connection. No connection is held through model generation. Stream cancellation still checks active turns and memory support freshness, using one shared session per check. Invalid-summary repair scheduling avoids repeatedly resetting an existing job.

## Page queries

| View | Implemented change |
|---|---|
| Progress | Request-local repository/service graph, one borrowed connection, reuse of repeated context/state/ranking reads; bootstrap includes the visible overview, context choices, candidates and initial understanding page |
| Memories | Its own list and preferences in one call; no Library data |
| Library | Its own bounded material list plus context choices required by that page |
| Assessments | Narrow card projection; selected detail and attempts only when requested; creation view reads context choices without fetching the assessment list; mistakes view skips unrelated parent reads |
| Mistakes | SQL filtering, ranking, facets and pagination; only the selected page's private answers/prompts returned; original collection retained for generation |
| Events | Agenda, optionally selected detail, and proposals for the initial page; proposal failure remains isolated; unchanged proposal reads avoid maintenance write locking |
| Notifications | Bell uses count/revision projection rather than notification bodies |
| Authentication | Onboarding phase joins the existing session lookup, avoiding an extra full-profile fetch; current session validity remains checked |

Old read endpoints remain available. Combined calls include only data needed together by that view. Learner projections remain request-local because retention and policy results can change with time.

Navigation intent prefetches the destination's first page using the same owner-scoped browser cache. It avoids competing page reads, hidden documents and constrained connections. No whole-workspace warmup. Browser page cache retains its separate short navigation freshness limit; this does not impose a time expiry on backend prompt payloads. Obsolete responses cannot repopulate invalidated entries, and canceling one consumer does not cancel a shared read needed by another.

## Measurements

Three samples per operation, read-only against the configured remote database. Values exclude HTTP authentication, browser rendering and multi-user load. Payload sizes are serialized application results, not wire traffic.

| Operation | Before | After | Interpretation |
|---|---:|---:|---|
| Progress overview median | 4732.9 ms, 18 SQL, 17 checkouts | 1197.8 ms, 14 SQL, 1 checkout | About 75% lower elapsed time |
| Assessment list payload | 50,231 bytes | 2,611 bytes | About 95% smaller; median 354.2 to 341.2 ms, so remote connection overhead still dominates |
| Profile cold / warm | 334.8 ms, 2 SQL | 267.0 ms, 1 SQL | Warm read transfers revision metadata only |
| Ready memory summary cold / warm | 469.4 ms, 2 SQL | 268.1 ms, 1 SQL | Warm read checks revisions and eligible supports without transferring summary blocks |

Database instrumentation now records query, checkout, connection, ping, commit and rollback counters/durations in the existing collector without logging SQL parameters or personal content.

## Verification and limits

- Focused backend run: 148 tests passed across tool cache, persistent chat, summaries, memories, student profile and revision practice. Additional focused cache tests verified no time expiry, cross-process updates and incremental history. Page/auth/proposal/notification/configuration run: 45 tests passed.
- Frontend production build passed. Final browser run: all 23 page-cache and assessment workflow tests passed, including Memories isolation, owner changes, shared cancellation, invalidation races, settled-page behavior, processing completion, mixed answers, saved work and grading feedback.
- Earlier full discovery ran 869 tests. It found three failures reproduced against the original source (event migration fixture, chat prompt expectation, and general-query mock), a missing Compose file caused by the initial test mount, and a new card comparison mismatch involving an existing string/UUID inconsistency. The mount was corrected and configuration test passed; the new parity comparison was corrected to compare serialized values and passed. The complete suite is not claimed green.
- Dedicated local PostgreSQL schemas were used for mutating tests. Remote benchmarks were read-only. No canonical remote records, indexes or configuration were changed, and running application services have not been rebuilt or restarted.
- No speculative indexes were added: the measured queries already use suitable indexes and execute in under 0.1 ms on the small current dataset. No pool-size, pooler-mode or database-region changes were made without evidence. Large-history mistake-query scale and production concurrency remain unmeasured.

Remaining latency includes the remote database round trip, session validity checks, canonical freshness probes and existing synchronous policy refreshes. A regional deployment or connection topology change needs separate measurement; these source changes do not remove network latency.

## Deployment handoff and cleanup

The source changes are ready for deployment with the existing test-suite limitations documented above. They introduce no migration, dependency, environment-variable or pool-budget change. Deploy the updated backend and workers before serving the updated frontend, because the frontend uses the new page endpoints. Existing endpoints remain available for older clients. Verify readiness and authenticated page/chat flows after rollout. Production latency and concurrency still need observation on the deployed system.

Removed the one-off remote benchmark script, temporary baseline checkout, generated browser results and diagnostic test logs. The disposable PostgreSQL container and its test volume were removed after regression testing. Retained the automated regression tests and these reports. Running application services were not restarted and no production data was removed.
