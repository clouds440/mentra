# Response latency fixes

Implemented 2026-10-12. The objective is to shorten the response critical path while retaining evidence, source validation, write ordering, recovery and canonical publication.

## Changes

- Independent tool reads fetch concurrently, up to four at a time. History, memory recall, RAG and event reads stage their results; only the coordinator merges citations, references and result budgets, in model-call order. Existing learner reads remain concurrent. Writes, discovery and unsupported tools are ordering barriers.
- Identical reads in one batch share one physical invocation. Each tool-call ID still receives a response. Existing per-turn caches and failed-call suppression remain in place. Overlapping history results do not create duplicate provenance.
- Independent profile, learner, RAG, assessment and attachment preparation overlaps. Required-source failures, selection boundaries, image limits and context budgets remain enforced.
- Activity updates use one bounded background writer per attempt, batching up to 32 updates. Publication flushes before canonical completion. Optional activity failures cannot replace a valid answer; stale/deleted/stopped attempts and domain writes retain direct database fencing. Cancellation drains the writer. Queues have bounds and backpressure.
- File logs are formatted with their originating context, then written by a bounded background queue. Normal shutdown flushes pending records. Critical answer, evidence and domain writes remain awaited.
- Exact concept/alias reads and per-term concept searches use batched SQL with the same active filters, confidence rules and per-term limits. Concept mutation remains transactional and ordered.
- The frontend reconciles the canonical terminal SSE packet directly, avoiding a redundant status GET. Invalid packets fall back to status retrieval; revision and attempt guards remain. The answer and interactive cards still reveal together after validation.
- Tool guidance requests independent reads together and reuses already supplied context. No model downgrade, evidence truncation increase, extra synthesis call or speculative answer streaming was introduced.

## Timing coverage

Instantaneous events such as “started” do not have an elapsed duration. Completed operations now expose the following timings. Correlate by `trace_id`, `workflow_id`, `span_id`, tool-call ID and provider-call ID; do not add overlapping or nested durations together.

| Layer | Events / measurements |
| --- | --- |
| Preparation | `context.prepare` step duration |
| Tool dispatch | `tool.dispatch`, `tool.result`, `tool.failed`; existing cache-hit/skip events |
| Concurrency wait | `tool.queue.duration_ms` |
| Worker thread | `thread.started.queue_ms`, `thread.completed.duration_ms` |
| Database | `db.query.duration_ms`, operation kind and outcome; owner-lock operation spans |
| Model/provider | HTTP attempt and time to headers; `provider.first_chunk`, `provider.first_text`, `provider.completed` total and callback time |
| Activity | `activity.queue` delay/batch size and repository spans |
| Browser | `mentra.chat.acknowledged`, `mentra.chat.response_visible` performance measures for locally initiated sends |

Database timings omit statements and bound values. Provider timings omit prompts, responses and credentials. Browser visibility measures store publication, not exact screen paint. Query timings exclude connection acquisition; enclosing repository/thread spans include that wait. Nonstreaming model calls expose total duration, not first-token time.

## Measured improvement

Controlled benchmark: `backend/testing/latency_benchmark.py`, pinned baseline dispatcher from commit `db237d5397ce2b6f84b42641eb858a01a1d3c924`. It uses the real orchestration and web adapter, fixed model responses and injected delays: two searches at 250/300 ms, activity transactions at 75 ms, model calls at 50 ms. Both paths warm up before three measured samples.

| Measurement | Baseline | Optimized |
| --- | ---: | ---: |
| Median tool-cycle duration | 1.4973 s | 0.5328 s |
| Concurrent searches | 1 | 2 |
| Activity transactions | 10 | 4 |
| Activity events | 10 | 10 |
| Model calls / physical searches | 2 / 2 | 2 / 2 |

This is a **64.4% reduction in the controlled scenario**, with assertions for identical final text and W1/W2 evidence. It is not a claim that every live 20–30 second response will improve by that percentage. Live provider/search latency and workloads vary. Earlier trace samples showed substantial non-model time; the new timings allow attribution on future live requests.

Run from the repository root with `PYTHONPATH=backend`: `python -m testing.latency_benchmark`. It performs no external requests and writes no user records.

## Verification

Regression coverage includes concurrent execution and ordered citations, duplicate suppression, write barriers, cancellation, isolated failed reads, bounded fanout, overlapping history provenance, real activity capacity/Stop fencing, concept lookup equivalence, context preparation, provider timing, safe database logs, background log draining, and browser terminal packet validation.

Verification completed:

- Full backend suite: 561 passed. Final focused suite after the last refinements: 69 passed.
- Production Python 3.12 image: 33 concurrency, persistence, observability and web tests passed.
- Selected browser regressions: 38 passed, including terminal delivery, stale attempts, malformed packets, Stop, recovery, citation reload and atomic answer/card display.
- Backend/frontend Docker builds passed; local API and frontend returned HTTP 200 and their containers were healthy after recreation. All three workers were running on the rebuilt backend image.
- `git diff --check` passed.

Test databases used isolated schemas in a dedicated local PostgreSQL container; application records were not test fixtures. Test output and benchmark samples are under `logs/latency-*` (local, untracked). No live paid-provider before/after latency claim is made.

## Follow-up review

The second review found and fixed four edge cases:

- Preserve enriched failure metadata before warning publication and caching. A saved assessment whose answer preparation fails must remain `committed`, including on repeated calls; required operations must retain their task impact.
- Serialize file-handler shutdown with producers and ignore emission after close, preventing records from being queued behind the shutdown sentinel.
- Guard terminal cleanup after asynchronous browser persistence. If a newer send has claimed the conversation, the previous completion cannot clear its pending retry record or timer.
- Shield the shared activity writer from reporting-wait timeouts and skip repeat flushes after an optional reporting failure. A timed-out progress sink must not cancel canonical answer completion; shutdown still drains/cancels the owned writer.

Memory recall now fetches saved memories and the current profile concurrently. Both are independent reads; projection remains ordered and write admission is unchanged. A synchronization-barrier test verifies actual overlap.

The repeated controlled benchmark measured 1.4939 s versus 0.5447 s (63.5% reduction), consistent with the original result under host load. Provider/model choices, evidence limits, write fences and canonical validation remain unchanged. Further concurrency is intentionally limited to proven independent reads; reducing model-call count speculatively could remove necessary evidence or validation.

Follow-up verification: 567 full-suite backend tests passed; after the final timeout correction, 54 focused and 69 persistence/history checks passed. All 37 selected browser checks passed against the stable frontend, including delayed-persistence retry-state retention. The frontend production build passed. Docker images are rebuilt from the committed implementation.
