# Assessment and learner implementation — 5 November 2026

Base: `f1b4ff7`. Branch: `assessment-learner-redesign-20261105`.

Implementation follows the audit's phase/gate register. Phase evidence is recorded before advancing. Real student data is not used by mutating tests. Existing canonical concepts, questions, grades, source receipts and evidence remain authoritative.

| Phase | State | Evidence / next gate |
| --- | --- | --- |
| 0: release blockers / observability | Local gate passed | 84 checks in 60.791 s: repository boundaries, downgrade/reupgrade, migration concurrency, checkpoint, RAG diagrams/source access, speech replay, memory reconciliation, pins, timeout classification and acquisition/hold metrics. Earlier refactor failures are preserved and superseded. Three stale RAG fixtures were independently reproduced on base and now select the intended tool by name. |
| 1: complete handoff / usable display | Local gate passed | 81 backend executions (including inherited cases) passed in 143.650 s; final three focused handoff checks passed in 6.507 s. Production browser suite 12/12 in 40.9 s; final four handoff/race checks 4/4 in 12.7 s. Completed → usable 423/346 ms, zero blocking history reads, versus audit delayed-read baseline 8,382 ms. Production build/TypeScript passed. Full repeated/throttled deployment percentile qualification remains a release gate. |
| 2: bounded context / database round trips | Local gate passed | 111 tests in 154.005 s, including 1,000 competing preparation/status operations at pool size one. Snapshot: seven queries, one checkout, zero commits/writes, supported-field parity; exact ownership and optional-failure fences retained. Remote read-only percentile qualification recorded separately. |
| 3: generation / retrieval | Local gate passed; provider qualification continuing | 142 loaded assessment/recovery/identity/migration checks passed in 196.695 s; one extra mistyped module produced a runner import error, then nine focused confirmation checks passed in 18.207 s. Earlier real failures were fixed, not waived. Three live-provider five-question jobs: 7.685/5.383/5.131 s, one content call each, versus matched baseline 18.648/12.506/15.401 s and 5/4/5 model calls. These are smoke samples, not percentile qualification. |
| 4: quality admission | Pending | G8/G9 fixtures and independently reviewed evaluation gate |
| 5: chat signals | Pending | G10/G11 cold unknown concept, provenance, assistance, outbox |
| 6: scale / lifecycle | Pending | G12/G13 bounded work and full-scan oracle |
| 7: integrated UI | Pending | Shared Lucide, Button/IconButton/Popover, semantic palette, all modes and accessibility |
| 8: prospective release validation | Pending | Empirical provider/canary/independent review and learning-gain gates cannot be replaced by mocked tests |

Each change must retain explicit rollback/Plan B. No phase is marked accepted merely because implementation exists.

Phase one repeated production-build delivery: 30/30 passed; median 358 ms, p95 429 ms, maximum 431 ms, zero blocking hydration requests. Mobile CPU and deployed-network qualification remain release gates.

Phase two replaces repeated whole-registry rankings with one bounded learner snapshot and one sequential read-only profile snapshot. Explicit topics do not rank unrelated history. Status reads project stopped-checkpoint expiry without committing. Stale policy projections return unknown until background replay; immutable evidence is retained. Rollback: revert this phase's facade callers and snapshot implementation; the original facade methods remain available. Pool contention is never hidden as an ownership/target success, and unexpected programming errors still fail visibly.

Remote PostgreSQL comparison (30 reads per revision, pool size one, server-enforced read-only transactions): baseline median 8,691 ms / p95 9,216 ms / max 10,233 ms; new median 793 ms / p95 825 ms / max 838 ms. Baseline 26 queries / 25 checkouts / 25 transaction commits; new seven queries / one checkout / zero commits. Same eight owned exact targets; no model calls, migrations or student-data mutations. These timings qualify preparation on the measured topology, not end-to-end provider generation.

Phase three: standard requests up to the existing 20-question limit use deterministic format/marks plans; custom structures retain the designer. Unspecified skills come from validated content, eliminating target planning and blocking organization. Accepted exact bindings win; otherwise scoped ungrouped IDs are preserved through durable after-publication organization. Publication and maintenance enqueue share one transaction. Jobs coalesce per owner/context; overlapping publication, claim recovery, stale completion and exhausted retries are fenced. Optional reranking caps cold/warm inference at two seconds without dropping grounding requirements. Existing private ordered-batch checkpoints remain the recovery contract; progressive answerability is not enabled. Rollback: revert generation routing and keep the additive maintenance table until pending work drains; prior code remains schema-compatible. No new quality or calibrated-mastery claim is inferred from faster generation.
