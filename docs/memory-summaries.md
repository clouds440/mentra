# Persistent memory summaries

Authenticated chat turns receive separate `conversation_summary` and `memories_summary` envelopes in system context. Conversation summaries belong to one chat. The memory overview belongs to the learner and persists across chats, devices and application restarts. Recent messages, the authoritative student profile, and response style remain separate.

Summaries are lossy context, not instructions, evidence or permission. The system prompt requires relevance in both retrieval and generation. An unrelated question must not cause personal mentions, topic steering or memory/history searches merely because the summaries are present. Full `user_memory` recall and keyword-based `history_lookup` across accessible chats remain available.

## Independent settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `CHAT_SUMMARY_MAX_TOKENS` | 600 | Chat-summary content cap |
| `CHAT_SUMMARY_MAX_CHARACTERS` | 2400 | Independent chat-summary character cap |
| `MEMORY_SUMMARY_ENABLED` | true | Enable background generation and context injection |
| `MEMORY_SUMMARY_MAX_TOKENS` | 800 | Rendered memory context cap |
| `MEMORY_SUMMARY_MAX_CHARACTERS` | 3200 | Independent memory context character cap |
| `MEMORY_SUMMARY_INPUT_TOKENS` | 6000 | Entire summary generation input, including instructions and schema |
| `SUMMARIZER_CONCURRENCY` | 2 | Shared execution slots across chat and memory summaries |
| `WORKER_DATABASE_POOL_SIZE` | 1 | Connections per worker process |
| `WORKER_DATABASE_POOL_OVERFLOW` | 0 | Worker connection overflow |

Both token and character limits are requested in generation prompts and enforced in code. There is no pooled summary quota or borrowing between summaries. The existing full-prompt admission check accounts for all context, tools, images and output reserve. Token counts use the existing centralized accounting and conservative fallback, not an exact provider tokenizer guarantee.

## Storage and processing

Migration `20261021_0029` adds `hm_memory_summary_state`, `hm_memory_summary_change` and `hm_memory_summary_job`. Existing eligible owners are queued for a bounded bootstrap. Original saved memories and chat history are preserved.

The canonical repository's revision hook captures eligible changes in the same owner-locked transaction. Manual and AI writes share it. Changes to pending/conflicting proposals do not become asserted facts. Confirmation, conflict resolution, pinning, expiry and deletion all respect eligibility. Revision-only evidence updates rebind support without another model call.

An AI save publishes its turn's updated memory fence only after the database commit. The stream watcher recognizes in-flight writes and replaced snapshots, so the save cannot cancel its own reply. Rollback retains the previous fence. Temporary pending context preserves pinned facts ahead of unpinned additions.

The worker uses the configured Mentra LLM. It coalesces writes for one second, with a maximum five-second postponement. Normal requests contain the previous supported summary plus changed records. It folds at most twelve facts per packet, shrinking batches when token accounting requires it. Bootstrap/reconciliation uses persisted page checkpoints, never a single unbounded collection request. Reconciliation runs after deletions, prompt-version changes, 100 effective revisions, or 30 days when next used. Unchanged idle accounts cause no daily generation.

Malformed derived blocks never prevent canonical memory edits. Malformed checkpoints, invalid cursors and checkpoints from an older prompt restart reconciliation from canonical facts. Chat compaction bounds large-message excerpts by tokens, including multilingual originals; an unrepresentable exchange remains retryable instead of silently dropping its job. Rejected chat summaries are queued for bounded repair even without new displaced history, and repair preserves their existing sequence coverage.

Publication is fenced by the owner source revision, summary revision and a 120-second lease. A model call has a 45-second timeout, at most one bounded compression repair, and five background attempts with backoff. New changes remain durable when an API/worker process exits. No database lock is held during provider calls.

Edits/deletions immediately remove affected stored prose and obsolete delta/checkpoint copies. Mixed-block survivors are recovered from canonical records. While the worker catches up, each turn receives a bounded safe view of valid blocks plus changed canonical facts. Expired support is filtered even if the worker is down. The stream watcher and completion transaction reject obsolete memory context; text already seen in an earlier response cannot be retroactively erased.

Internal support IDs stay server-side. Only actual recall results create `M` citations. Logs capture shapes, counts, revisions and error codes, not personal text.

## Deployment and operations

Apply migrations before starting workers:

```sh
python -m app.db.migrate
python -m app.summarization.worker
```

Compose includes one `summarizer` using the backend image, one shared LLM instance, and one bounded execution pool for both summary types. It alternates queue priority to prevent starvation, including with one execution slot. Common code owns provider timeouts, independent background budgets, retry delays and lease duration. Each domain retains its own prompt, limits, source selection and fenced publication. It initializes PostgreSQL and the shared LLM only; the Events worker remains free of model initialization.

Migration `20261021_0030` adds the durable `chat_summary_job` queue and queues existing live chats for eligibility checks. Every successful chat completion queues compaction in the same transaction. The API no longer starts a summary task. The worker retains chat's displaced-history threshold, skips LLM calls for short/unchanged chats, and drains large backlogs in bounded batches. Failed jobs retry up to five times; expired leases recover after a crash. Chat deletion removes queued jobs and prevents publication. A completion arriving during processing updates the existing job and cannot be lost by an older acknowledgement.

```sh
docker compose exec summarizer python -m app.summarization.worker --diagnostics
docker compose exec summarizer python -m app.summarization.worker --retry-owner LEARNER_UUID
docker compose exec summarizer python -m app.summarization.worker --retry-owner LEARNER_UUID --chat CHAT_UUID
```

Diagnostics return pending/failed counts and oldest queue time separately for both domains. A failed job remains durable; an explicit retry or another effective mutation/completion reactivates it. Disabling `MEMORY_SUMMARY_ENABLED` stops memory generation/injection while canonical memories and existing retrieval remain intact; `CHAT_SUMMARY_ENABLED` controls chat compaction independently. Keep the schema during feature rollback.

Worker pools are independently bounded. With default Compose settings the API allows five connections without overflow and five worker processes allow one each, leaving headroom in a fifteen-session hosted pool. Review totals if changing pool settings, replicas or other clients; process count multiplies connection capacity.

## Verification

Use an explicit disposable PostgreSQL URL; tests never select the configured user database:

```sh
PYTHONPATH=backend TEST_DATABASE_URL=postgresql://... python -m unittest backend.tests.test_summarizer backend.tests.test_memory_summaries backend.tests.test_chat_summaries backend.tests.test_history_management backend.tests.test_orchestration backend.tests.test_prompt_efficiency backend.tests.test_deployment_config backend.tests.test_database_budgets
PYTHONPATH=backend TEST_DATABASE_URL=postgresql://... python -m testing.memory_summary_verification
```

The second command makes real provider calls using synthetic memories in an automatically removed test schema. It checks bootstrap, incremental correction, deletion, multilingual content, unrelated-query restraint, relevant personal context and original-history tool selection. It does not write fixtures into real user records.

See the [implementation plan](Persistent_Memory_Summary_Plan.md) for design and acceptance criteria.

### Verification recorded 2026-10-21

| Check | Result |
| --- | --- |
| Focused PostgreSQL, chat/history, orchestration, prompt, pool and deployment regression tests | 132 passed, including 32 memory-summary tests and 16 shared-worker/chat-queue tests |
| Live configured-model checks with synthetic records | Passed AI evidence-backed save, manual save, bootstrap, incremental preference correction, deletion, multilingual content, unrelated-query restraint, relevant personal context, original-history tool selection and chat compaction through the shared worker |
| PostgreSQL migration on the configured Mentra database | Applied through `20261021_0030`; canonical records preserved |
| Local image and startup | Backend code/migration image rebuilt using hash-verified unchanged dependency/model layers; API readiness returned `ready`; all five worker processes running, including `summarizer` |
| Both summary queues / idle state | Zero pending and zero failed jobs in both queues; no idle INFO output observed over the final 30-second check |
| Cleanup | Disposable PostgreSQL schemas/test container/volume and stopped obsolete memory-only worker container removed |

These checks verify the local deployment and tested cases; they do not establish production load capacity or guarantee model behavior on every input. Both chat and memory summary generation now run through the shared durable summarizer, with separate domain queues and limits.
