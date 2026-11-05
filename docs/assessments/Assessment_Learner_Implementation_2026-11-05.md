# Assessment and learner implementation — 5 November 2026

Base: `f1b4ff7`. Branch: `assessment-learner-redesign-20261105`.

Implementation follows the audit's phase/gate register. Phase evidence is recorded before advancing. Real student data is not used by mutating tests. Existing canonical concepts, questions, grades, source receipts and evidence remain authoritative.

| Phase | State | Evidence / next gate |
| --- | --- | --- |
| 0: release blockers / observability | Local gate passed | 84 checks in 60.791 s: repository boundaries, downgrade/reupgrade, migration concurrency, checkpoint, RAG diagrams/source access, speech replay, memory reconciliation, pins, timeout classification and acquisition/hold metrics. Earlier refactor failures are preserved and superseded. Three stale RAG fixtures were independently reproduced on base and now select the intended tool by name. |
| 1: complete handoff / usable display | Local gate passed | 81 backend executions (including inherited cases) passed in 143.650 s; final three focused handoff checks passed in 6.507 s. Production browser suite 12/12 in 40.9 s; final four handoff/race checks 4/4 in 12.7 s. Completed → usable 423/346 ms, zero blocking history reads, versus audit delayed-read baseline 8,382 ms. Production build/TypeScript passed. Full repeated/throttled deployment percentile qualification remains a release gate. |
| 2: bounded context / database round trips | Local gate passed | 111 tests in 154.005 s, including 1,000 competing preparation/status operations at pool size one. Snapshot: seven queries, one checkout, zero commits/writes, supported-field parity; exact ownership and optional-failure fences retained. Remote read-only percentile qualification recorded separately. |
| 3: generation / retrieval | Pending | G6/G7 call counts, failure/cancellation, bounded sources |
| 4: quality admission | Pending | G8/G9 fixtures and independently reviewed evaluation gate |
| 5: chat signals | Pending | G10/G11 cold unknown concept, provenance, assistance, outbox |
| 6: scale / lifecycle | Pending | G12/G13 bounded work and full-scan oracle |
| 7: integrated UI | Pending | Shared Lucide, Button/IconButton/Popover, semantic palette, all modes and accessibility |
| 8: prospective release validation | Pending | Empirical provider/canary/independent review and learning-gain gates cannot be replaced by mocked tests |

Each change must retain explicit rollback/Plan B. No phase is marked accepted merely because implementation exists.

Phase one repeated production-build delivery: 30/30 passed; median 358 ms, p95 429 ms, maximum 431 ms, zero blocking hydration requests. Mobile CPU and deployed-network qualification remain release gates.

Phase two replaces repeated whole-registry rankings with one bounded learner snapshot and one sequential read-only profile snapshot. Explicit topics do not rank unrelated history. Status reads project stopped-checkpoint expiry without committing. Stale policy projections return unknown until background replay; immutable evidence is retained. Rollback: revert this phase's facade callers and snapshot implementation; the original facade methods remain available. Pool contention is never hidden as an ownership/target success, and unexpected programming errors still fail visibly.
