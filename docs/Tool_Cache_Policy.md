# Tool cache reuse and invalidation

Implemented 2026-10-13. The session is the ongoing chat, but reuse lifetime depends on the evidence. Writes never use read-result caching; existing domain idempotency still protects writes and unknown-outcome receipts.

| Read | Reuse | Freshness boundary |
| --- | --- | --- |
| History, memory recall, learner context, agenda, assessment reads | Equivalent validated calls within one response; duplicate calls in a batch share one invocation | Fresh scope for every response; related writes invalidate cached reads and lower-layer caches |
| Assessment status | Always live | Asynchronous grading may change without a tool write |
| RAG retrieval | Candidate rankings reused across responses for up to 120 seconds; 128 bounded process-local entries | Current owner, eligible documents, active generations, document revisions, contexts, concepts, embedding/index configuration and hybrid setting form the key |
| RAG source content | Hydrated and reauthorized on every search, including cache hits | Generic tool caches cannot bypass the RAG service; tokens are assigned within the current response |
| Web search/research | Existing owner-scoped durable cache, normally 120 seconds, plus response-local reuse | Query, website, owner, namespace and calendar date remain distinct; original search timestamp survives reuse; existing bypass and expiry remain effective |

RAG publication, replacement, reindexing, deletion, archive changes, renaming, retagging and context eligibility changes invalidate reuse naturally through database-derived signatures. Uploads become searchable when ingestion publishes a ready generation; pending uploads are not treated as available evidence. Each API process rechecks database state, so worker-side publication does not require an in-memory invalidation broadcast. Only candidate IDs/scores are cached; current metadata/content, per-request source limits and token budgets are still applied.

Keys use schema defaults and canonical values. Set-valued source/context/concept ID lists are ordered consistently. Ordinary prose spacing and Unicode canonical composition can match. Case, words, numbers, dates, negation, operators, quoted text, code layout and source filters remain significant. Empty scope and omitted scope remain distinct. There is no fuzzy semantic/synonym matching: a high similarity score is insufficient evidence that two requests require the same answer.

One shared key function is used for admission, batch duplicate suppression, successful-result caching and rollback. Invalid arguments still go through normal validation. Cached payloads are copied before delivery, preventing a caller or citation projection from altering later hits.

Related-write invalidation includes assessment-to-learner/profile and memory-to-profile dependencies. Failed read receipts/outage suppression are cleared for affected domains after a write; unknown-outcome write receipts are retained. Personal results are intentionally not reused across responses without domain revision validation, because profile edits, memory expiry, grading workers, agenda time boundaries and other devices can change them.

Equivalent simultaneous web requests in one API process share a cache-fill lock, then reread the durable cache. Only the leader dispatches when its result is cacheable; cancellation of a waiter does not cancel the leader. Locks have a bounded registry, and every caller retains its own deadline. Separate API processes may still dispatch simultaneous misses; this avoids introducing a distributed lease or changing quota semantics.

Observability: `tool.cache_hit` reports response-local hits, `web_search.cache_hit` reports durable web hits, and `rag.cache_hit` plus `diagnostics.candidate_cache_hit` reports ranking reuse. No cache keys or query text are logged. RAG hits continue to perform scope validation, hydration and usage recording, so they are faster reuse rather than zero-work responses.

Regression coverage includes key equivalence/separation, default arguments, empty scopes, duplicate coalescing, TTL/LRU bounds, copy isolation, dependent-write invalidation, new-response isolation, live RAG reauthorization, concurrent web fills and waiter cancellation, document publication/replacement, metadata refresh, deletion and owner isolation.

Validation: the full backend suite passed 576 tests; focused suites passed 110 and 42 tests, and both source/citation browser checks passed. Instrumented tests confirm two equivalent RAG searches issue one vector query while still hydrating twice, two equivalent tool reads execute once, and concurrent equivalent web requests make one provider call and one quota admission. These are verified work reductions, not a fixed end-to-end latency promise.
