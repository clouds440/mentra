# Persistent memory summaries for Mentra

Status: implementation plan only. Created 2026-10-21.

## 1. Intended behavior

Every authenticated chat turn receives two separately labelled context sections:

| Section | Scope | Contents |
| --- | --- | --- |
| `conversation_summary` | This conversation only | Requirements, decisions, corrections, and task state from older exchanges in this chat. Empty until enough history exists. |
| `memories_summary` | This learner across all chats | A compact overview of the learner's currently active saved memories. Independent of any conversation. Empty when there are no eligible memories. |

Both sections are present in the system context on every turn, including the first turn of a new chat. An empty section explicitly records its state; it does not trigger an unnecessary model call. Recent messages and the existing student profile remain separate context inputs.

Saved memory records remain canonical. Summaries are derived, lossy context that helps the model notice relevant facts and decide what to retrieve. Mentra retains `user_memory` for full matching memory records and `history_lookup` for original exchanges across the learner's accessible chats. Neither summary is evidence for writing a memory, grading an answer, or claiming an action succeeded.

This design supplies broad personal context automatically without reading and resending the entire memory collection after every change.

## 2. Verified starting point

| Existing behavior | Current code | Planned treatment |
| --- | --- | --- |
| Per-chat incremental summary, generated after completed replies when enough older history is displaced | `backend/app/chat/summaries.py`, `chat/repositories/summaries.py` | Preserve incremental compaction and recent-message retention. Add an explicit character bound and always-present context envelope. |
| Chat summary prompt requests at most 600 tokens; publication currently rejects above 650 counted tokens | `backend/app/langchain/prompts/chat_summary.py`, `chat/summaries.py` | Align requested and validated limits; reject truncated or oversized output. |
| Saved memory recall is optional, keyword based, active/unexpired only; up to five matches and 750 content characters per result packet | `backend/app/history_management/service.py`, `repositories/postgres.py` | Preserve this retrieval path and its authorization. The new summary does not replace it. |
| Manual memory writes go directly through the memory repository; LLM writes also end in that repository | `backend/app/api/routes/memories.py`, `history_management/service.py` | Capture changes centrally in repository transactions so neither caller can bypass scheduling. |
| Cross-chat lookup supports `current_chat`, `selected_chats`, and `all_chats`; broader scopes require keywords and enforce ownership/deletion rules | `backend/app/chat/repositories/history_reader.py`, `history_management/schemas.py` | Keep unchanged. Search can miss paraphrases because it is lexical; do not promise exhaustive recall. |
| Student profile and response style are prepared automatically | `backend/app/langchain/planning.py`, `orchestration_service.py`, `chat_service.py` | Preserve; manual profile values take precedence over conflicting summary wording. |
| Tool subsets are selected initially and expandable through discovery | `backend/app/langchain/tool_selection.py` | Keep full recall discoverable. A visible memory summary must also make the memory instructions and exact recall tool available initially. |
| Reminder worker deliberately avoids LLM initialization | `backend/app/history_management/events/worker.py` | Keep it lightweight; it may mark due expirations but must not summarize. |
| Chat completion validates referenced memory revisions | `backend/app/chat/repositories/postgres.py`, `history_management/repositories/postgres.py` | Extend the completion fence to summary-derived context too. |

## 3. Ownership and code organization

Keep the feature in History Management. Do not put summary construction in API routes, frontend components, or individual tools.

| Responsibility | Location / change |
| --- | --- |
| Eligible-memory policy, delta reduction, prompt packet, safe context loading | New `backend/app/history_management/memory/summaries.py` |
| Structured summary/result contracts and bounds | New `backend/app/history_management/memory/summary_schemas.py` |
| Summary state, queue/delta transactions, leases, publication fencing | New `backend/app/history_management/repositories/memory_summaries.py` |
| Transaction hooks for every effective memory change | Existing `history_management/repositories/postgres.py`; one shared helper accepting the existing transaction |
| Table registration | Existing `history_management/repositories/tables.py` and normal metadata registration |
| Durable background execution | New `backend/app/history_management/memory/worker.py`, one Compose service using the backend image |
| Summary prompt and token policy | New `langchain/prompts/memory_summary.py`; existing prompt registry/token policy |
| Public domain facade and construction | Existing `history_management/service.py`, `factory.py` |
| Turn context loading and prompt assembly | Existing `langchain/orchestration_service.py`, `chat_service.py`, `history_orchestration.py` |
| Chat-summary bounds and envelope | Existing `chat/summaries.py`, `langchain/prompts/chat_summary.py` |
| Migration and verification | One additive Alembic migration; focused repository, worker, prompt, and integration tests |

The worker uses the same configured Mentra LLM/model factory and credentials. Give the summary workflow its own prompt, finite input/output allowance, timeout, and background concurrency limit. Do not introduce another model provider or a generic job framework for this feature.

## 4. Durable storage

Use three small owner-scoped tables. Table names are proposed; all foreign keys, indexes, and cleanup rules must follow existing conventions.

| Table | Fields / purpose |
| --- | --- |
| `hm_memory_summary_state` | One row per learner: `source_revision`, `published_source_revision`, `summary_revision`, structured `blocks`, `prompt_version`, `updated_at`, `next_expiry_at`. The structured blocks render to one compact summary. |
| `hm_memory_summary_change` | Durable, ordered deltas keyed by `(learner_id, source_revision, memory_id)`: operation, before/after eligible projections, timestamp. Contains only fields needed for summarization, never source-message bodies. Multiple affected records may share one transaction revision. |
| `hm_memory_summary_job` | One coalescing job per learner: target revision, available time, lease token/deadline, attempts, last error code, and retry state. |

Each block contains compact text and a bounded list of supporting `{memory_id, revision}` pairs. Keep internal references outside the rendered prose; include their serialized cost in the total context allowance. Do not let a model invent support IDs or cite an unrelated record as support.

Use database constraints for nonnegative/monotonic revisions, lease consistency, and bounded stored payloads. Index claimable job times and owner/revision delta lookup. Add learner cleanup/cascade behavior explicitly, including existing account deletion paths. A normal chat needs one bounded domain context read, not a full-memory scan.

## 5. What changes the summary

Only active, unexpired saved memories are eligible. Pending and conflicting proposals must never become asserted personal facts. Manual and confirmed AI memories participate under the same eligibility rule.

| Mutation | Required action |
| --- | --- |
| Add an eligible memory | Record an `add` delta and queue refresh. |
| Edit content/category, confirm a proposal, revise a fact | Record before/after projections; queue refresh. |
| Resolve a conflict | Record all resulting eligibility/content changes atomically, including other records made conflicting. |
| Delete an eligible memory | Record a removal; immediately make its supported blocks unusable. Queue refresh. |
| Expire, change expiration, clear expiration, or restore applicability | Apply eligibility transition and recompute next expiry. Queue refresh when effective context changes. |
| Pin/unpin | Update priority through a delta; pinning never grants extra truth or unlimited prompt space. |
| Duplicate/idempotent write with unchanged effective context | No summary LLM call. Evidence-only bookkeeping does not require resummarization; refresh internal revision support safely if necessary. |
| Change automatic-memory preference | Preserve current meaning: disabling automatic saving does not disable existing saved-memory use. No summary call unless eligible context changes. |
| Delete a source chat | Preserve existing saved-memory retention policy. Summarize only if retained memory eligibility/content changes; source deletion alone does not invent a new fact. |
| Delete all eligible memories | Clear summary synchronously, cancel obsolete work, and avoid an LLM call. |

The mutation, source revision increment, delta insertion, and job upsert commit in the **same PostgreSQL transaction** under the existing owner lock. Rollback means no queued change. Do not rely on FastAPI background tasks or `asyncio.create_task` for delivery.

Natural expiration also matters when nobody edits anything. Store the earliest expiration as a scheduling deadline. The worker queues due expiration changes using a bounded indexed sweep, and the prompt read filters expired support immediately even if the worker is down.

## 6. Incremental update algorithm

1. Coalesce rapid writes for a learner for about one second, with a maximum five-second postponement so sustained edits cannot defer work indefinitely. Every effective mutation is represented even when several share one model call.
2. Claim a due job with a durable lease and `SKIP LOCKED`, then release the database transaction before calling the LLM. Serialize generation per learner; allow bounded parallel work for different learners.
3. Read a consistent snapshot of the published summary and unapplied deltas through a fixed target source revision.
4. Reduce repeated operations on each memory: add followed by edit becomes its final add; repeated edits keep the required before state and final after state; add followed by deletion can cancel out. Apply removals before additions.
5. Remove or split invalidated summary blocks before sending the previous summary. Supply relevant unchanged supporting memory contents for any affected mixed block, so an edit does not silently erase unrelated facts in that block. This is a targeted support lookup, not a scan of all memories.
6. Send the previous safe summary, bounded delta batch, affected supports, exact limits, and prioritization rules to `MEMORY_SUMMARY`. Ask for the complete replacement compact summary with support references.
7. Validate schema, length, IDs/revisions, active/unexpired eligibility, nonempty text when facts remain, and provider finish reason. Validate fidelity against supplied facts in model-quality evaluation; structural validation alone cannot prove semantic correctness.
8. Publish only if the lease, base summary revision, and processed source revision still match. If more changes arrived, do not expose a result containing superseded facts: retain them as pending and immediately process the next batch. An expired lease or obsolete claimant cannot overwrite newer state.
9. Advance the processed watermark atomically with publication. Delete consumed delta content after commit; retain operational counts/watermarks rather than an indefinite second archive of personal text.

### Example generation packet

```json
{
  "previous_summary": {
    "blocks": [{"text": "Builds untoastify, a React toast package.", "supports": [{"id": "m1", "revision": 1}]}]
  },
  "changes": [
    {"operation": "update", "id": "m1", "before_revision": 1,
     "after": {"revision": 2, "content": "Maintains untoastify and prioritizes accessible toast controls.", "category": "fact", "pinned": true}}
  ],
  "limits": {"max_characters": 3200, "max_context_tokens": 800},
  "instruction": "Replace superseded facts, preserve useful unchanged facts, and return compact supported blocks."
}
```

Normal updates contain the old summary plus changed records and affected supports. They do not repeatedly send the entire collection.

## 7. Compaction, omissions, and recovery

A finite summary cannot retain every saved memory, and a summary plus only new changes cannot recover facts omitted earlier. Make this tradeoff explicit.

| Situation | Policy |
| --- | --- |
| Summary is full | Prioritize current pinned facts, stable preferences, durable identity/project facts, and active goals. Merge related facts; preserve names and qualifications. Omitted records remain searchable. |
| A previously omitted memory is edited or pinned | Its delta reintroduces it for consideration. |
| Deletion frees space or repeated incremental edits cause drift | Queue a bounded reconciliation, rather than pretending omitted facts can be reconstructed from prose. |
| Initial summary or existing learner without one | Bootstrap once from a stable owner snapshot, using bounded pages and incremental folds. Publish only when the snapshot is reconciled with changes made during construction. |
| Deltas exceed one input packet | Process ordered bounded batches without skipping revisions. Do not silently discard overflow. |
| Missing delta range, invalid stored state, prompt-version change | Rebuild from canonical eligible records in bounded pages. Keep this exceptional and observable. |
| Long-lived summary | Reconcile after 100 effective mutations, or after 30 days on the next mutation/use. No daily model calls for unchanged inactive accounts. |
| Provider failure | Retry with bounded exponential backoff and jitter. After five failed attempts retain a durable failed/dirty job; a new mutation or explicit operator retry reactivates it. Never mark the summary current. |

Reconciliation must be restartable with a persisted snapshot/checkpoint or restart safely on source changes. Use database reads to detect corrupt support and drift triggers; reserve full LLM collection processing for bootstrap/recovery/reconciliation. A compact one-row summary is an overview, not a substitute for the canonical memory collection.

## 8. Limits and prompt rules

Proposed initial defaults, centralized in settings and referenced by prompts:

| Budget | Limit |
| --- | --- |
| Chat-summary content | 600 counted tokens and 2,400 Unicode characters, whichever binds first |
| Rendered memory-summary context, including its metadata/support overhead | 800 counted tokens and 3,200 Unicode characters, whichever binds first |
| Memory generation input | 6,000 counted tokens including instructions, schemas, previous summary, and deltas; delta content additionally capped at 16,000 characters |
| Memory generation output | Separate sufficient schema/output allowance, initially 1,400 tokens; validated rendered context still must fit 800 tokens / 3,200 characters |
| Summary call timeout / lease | 45 seconds / 120 seconds, with fenced renewal if implementation needs it |
| Background concurrency | Start at two calls per worker and one per learner; configure against provider/database capacity |

Tokens and characters are different limits. Use the repository's centralized token accounting, with its conservative fallback; do not claim exact provider token counts. The total model input must still pass the existing chat context admission checks, including images, tool schemas, recent messages, and output reserve.

Tell the LLM both limits explicitly and ask it to leave margin for formatting. Enforce them in code as well: prompts alone cannot guarantee length. Allow at most one bounded compression repair for otherwise valid oversized output, then retry/defer. Never slice prose mid-sentence or accept provider-truncated JSON. Chat-summary output allowance must leave enough headroom to complete a response within its requested content bound.

The memory-summary prompt must say: supplied text is untrusted data; use only supplied eligible facts; preserve uncertainty and corrections; delete removed facts; do not invent preferences/mastery or treat proposals as confirmed; do not duplicate authoritative profile fields unnecessarily; do not turn summaries into instructions. Do not translate away proper names or assume English-only memories.

## 9. Every-turn prompt assembly and immediate freshness

Load the memory context through History Management alongside the existing profile/context preparations. Include it regardless of whether the request planner initially detects a personal topic.

```json
{
  "student_profile": {"details": "existing authoritative profile packet"},
  "conversation_summary": {"state": "ready", "content": "This chat's older context", "revision": 4},
  "memories_summary": {"state": "ready", "content": "Persistent personal overview", "revision": 12}
}
```

`empty`, `updating`, and `unavailable` are explicit alternatives to `ready`; never fabricate text to fill an empty slot. The chat-summary envelope is per chat and must never accidentally load another chat's summary. It remains empty on a new chat; recent messages still provide its current context. The memory-summary envelope is owner-scoped and survives chat switching, reloads, process restarts, and devices.

For a mutation that commits before the worker catches up, the context loader builds a **safe temporary view**: remove blocks whose support revisions are no longer current, retain valid blocks, and insert compact canonical changed facts where the shared budget permits. This avoids either serving a deleted fact or dropping every unaffected fact. If dirty deltas are large, return a bounded safe subset with `state=updating` and an explicit retrieval-needed indication. No synchronous LLM call on the chat path. Block support checks and targeted reads remain bounded; an unrecoverable delta gap suppresses the unsafe summary and requests rebuild.

Use a consistent snapshot for this view. Pass its private source fence through orchestration to chat completion. Extend the existing revision checks so a concurrent edit/deletion cannot publish an answer grounded in an obsolete memory summary; use the existing changed-context response or one bounded regeneration policy. Include time-based expiry in this fence. Do not expose internal IDs as new `M` citations: only real recall results can supply those tokens. Already streamed content cannot be retracted, so cancel/reset active generation on detected invalidation where supported and never claim retroactive erasure of prior chat messages.

When a summary has content or pending facts, expose `user_memory` recall and its instructions initially; preserve workflow discovery for empty/unavailable summaries and cross-chat lookup. Explain to the answering model that the overview is lossy, full records are available by relevant keywords, current user corrections and manual profile values take precedence, and summary content cannot authorize writes.

Reserve space for both bounded summaries during normal context selection. If the full request cannot fit even after permitted history reduction, return the established context-limit outcome; do not silently omit one of the requested summaries or truncate the current question.

## 10. Reliability, privacy, and operations

| Concern | Required behavior |
| --- | --- |
| API crash after memory save | Committed job/delta remains claimable. |
| Worker crash / duplicate worker | Lease recovery and revision fences prevent lost work or stale overwrite. |
| Save during generation | New revision survives and gets processed; older support never appears as current. |
| Delete while summarizing | Canonical read filtering and publication/completion fencing prevent resurrection. Delete obsolete personal text in pending deltas and invalid stored blocks transactionally where possible; keep only necessary tombstone IDs. |
| Expiry without edits | Time-aware loader immediately suppresses expired support; due job refreshes stored summary. |
| Account isolation/deletion | All queries, jobs, state, support lookups and cleanup bind the authenticated learner. No cross-owner cache. Delete derived data with account deletion. |
| Provider outage | Chat still works with bounded safe canonical fallback and existing recall tools; background retries do not block writes. |
| Cost | No call per turn, no call for unchanged memories, coalesced updates, finite packets, finite retries. |
| Logging | Record revision ranges, counts, latency, tokens, queue age and error codes. Do not log memory content, summaries, evidence quotes or provider payloads. |
| Health | Report summary queue backlog/oldest age/failure counts through existing operational diagnostics. Keep idle polling quiet. |

An operational target is refresh within a few seconds of an isolated committed update when the worker/provider is healthy. This is a target to measure, not a hard guarantee. Correctness must not depend on this delay.

## 11. Migration and rollout

1. Add tables/indexes and settings in a new additive Alembic revision after the actual repository head at implementation time. Do not edit old applied migrations or drop original memories/history.
2. Implement transactional change capture, safe context loading, and worker claim/publication contracts behind `memory_summary_enabled`, initially disabled for prompt injection.
3. Implement bounded generation and tests. Register table imports and prompt versions explicitly. Add the worker to Compose and deployment documentation without initializing embeddings/document processing.
4. Start the worker after applying the migration. Bootstrap existing eligible owners in bounded batches; users with no memories need no generation. Do not repeat the file migration's earlier no-backfill assumption for memory records.
5. Enable the feature locally/staging and verify cross-chat continuity, all mutation paths, expiry, restart recovery, and actual prompt packets with nonsensitive fixtures.
6. Enable prompt injection after checks pass. Monitor queue lag, token overhead, generation failures, and recall behavior. Roll back by disabling injection/worker; canonical saved memories, chat summaries and recall remain intact.

No public summary endpoint or frontend redesign is required for the first implementation. The persistent summary is internal context; the existing Memories interface continues to edit canonical records.

## 12. Implementation sequence and acceptance checks

| Phase | Deliverable | Acceptance evidence |
| --- | --- | --- |
| 1. Contracts and persistence | Shared limits, structured blocks, migration, transaction hooks and coalescing queue | Real PostgreSQL tests prove rollback, idempotency, conflict-resolution fanout, ordering, owner isolation and account cleanup. |
| 2. Incremental worker | Claim/retry/recovery, delta reduction, generation and fenced publication | Crash/restart and two-worker tests; edit/delete during model call cannot publish stale facts; unchanged saves cause no paid call. |
| 3. Safe context | Every-turn envelopes, temporary canonical delta view, expiry filtering and completion fence | First turn in chat B sees memories from chat A; chat B never receives chat A's conversation summary; deletion is effective before worker completion. |
| 4. Prompt integration | Memory instructions/tool availability, separate bounds and total input accounting | Inspect captured model packets for normal/greeting/direct/tool paths, oversized inputs, multilingual fixtures and no secret payload logging. |
| 5. Summarization quality | Real same-model calls using nonsensitive fixtures | Explicit facts stay accurate; changed preferences replace old ones; deleted/expired/pending/conflicting facts disappear; unrelated facts survive edits; prompt injection in a memory stays data. |
| 6. Retrieval compatibility | Existing memory/history tools retained | Full-memory lookup and `all_chats` keyword search still retrieve originals with existing ownership/deletion/sequence rules; only retrieval returns valid citations/evidence. |
| 7. Deployment | Migrated PostgreSQL, built backend image and durable worker | Container startup, worker restart, API readiness and a complete manual-save → summary → new-chat test, plus an AI-save equivalent. |

Also test pinned-priority overflow, removing a mixed-support block, omitted-fact reintroduction, bootstrap across multiple pages, compaction limits in non-Latin scripts, bounded compression retry, disabled automatic saving with existing recall, queue exhaustion/operator retry, and summary changes during streamed replies. Static checks and mocked tests are necessary but do not establish summarization quality; real provider calls are part of completion evidence.

## 13. Completion criteria

- Every authenticated turn has separate, bounded chat and memory context envelopes.
- Memory context persists across chats and devices; conversation context stays scoped to its chat.
- Every effective canonical memory update schedules durable incremental work centrally.
- Ordinary updates send the previous summary and bounded changes/supports, not the full memory collection.
- Edited, deleted, expired, pending or conflicting facts are not presented as current merely because a worker is delayed.
- Full memory recall and cross-chat original-history retrieval retain their current behavior.
- No summary model call blocks a normal chat turn or memory write.
- Live summarization, real database concurrency, prompt-budget, restart and deployment checks have documented results.

Approval of this plan authorizes a later implementation; this document itself does not change memory behavior.
