# Mentra History Management and User Memory Implementation Plan

**Status:** Implemented and verified on 2026-10-08; both Docker images rebuilt. Application database deployment was not performed.  
**Codebase inspection date:** 2026-10-08.  
**Scope:** A standalone history-management module, two LLM tool families, evidence-backed persistent user memory, Settings UI, complete chat integration, verification, and Docker image builds.

This document is the implementation tracker. Check off a task only after its acceptance conditions are verified. Record migrations, test commands/results, limitations, and deviations in the phase evidence table. A phase is not complete because its files exist.

## 1. Agreed policies and applied implementation decisions

| Policy | Agreed behavior |
| --- | --- |
| Automatic memory | Only explicit user statements may become active automatically. AI inferences remain pending. |
| Sensitive information | Save only when the user explicitly asks to remember the specific information. General automatic-memory permission is insufficient. |
| Chat deletion | Saved memories survive source-chat deletion until the user deletes those memories. |
| Manual control | Users can view, add, update, confirm, and delete memories. |
| Retrieval | Memory and additional history are tools. Never inject all memories into every prompt. |
| Ownership | The authenticated learner identity owns all reads and writes; the model never chooses an owner. |
| Module boundary | Reuse canonical chat storage through a facade; own retrieval, memory lifecycle, and tool contracts separately. |
| Frontend entry | Keep Settings in the existing bottom sidebar account drawer; expose Memories there as a Settings destination and as a dedicated Settings tab. |

**Applied promotion policy:** Inferred candidates require manual user confirmation. Later explicit evidence can strengthen a candidate but never silently promotes it. This conservatively resolves the unanswered promotion question under the user's subsequent authorization to implement end-to-end.

Automatic remembering defaults to enabled, with an explicit Settings control. Freshness and admission defaults are environment-configurable; bounded candidate/receipt maintenance currently uses a documented 90-day repository policy. See [operational documentation](docs/history-management.md) for the authoritative implemented contracts.

Memory is a supported, time-qualified account record, not proof that a statement is objectively true. A user's assertion, an AI inference, a profile field, and measured learner evidence must remain distinguishable.

## 2. Verified codebase baseline and compatibility constraints

| Existing component | Inspected behavior | Consequence for this plan |
| --- | --- | --- |
| `backend/app/chat/repositories/{tables,postgres}.py` | Canonical PostgreSQL conversations, sequenced individual messages, durable turns, owner-serialized sync changes. | Do not duplicate transcripts or replace chat's incremental protocol. Extend its public read facade for search/evidence lookup. |
| `ChatRepository.edit(..., remove=True)` | Deletes message and turn rows; retains a soft-deleted conversation. | Memory evidence cannot depend on a surviving message/turn FK. Tool receipts cannot block chat deletion. |
| `backend/app/chat/service.py` | Persists the current question before inference; tracks a shielded task; 150-second generation deadline and 180-second lease. | Bind current message/turn/attempt scope on the server. Tool execution must fit this deadline or deliberately revise deadline and lease together. |
| `backend/app/chat/context.py` | Converts role/content pairs; trims using approximate token counts; reserves system/RAG/output capacity. | It cannot safely trim a tool conversation as ordinary pairs. Add a BaseMessage-aware budget path and preserve tool-call/result groups. |
| `backend/app/chat/langchain_history.py` | Read-only canonical user/assistant message adapter. | Reuse the reader boundary. LLM-facing retrieval/adaptation belongs in the new module; preserve imports with a compatibility shim if moved. |
| `backend/app/api/routes/chat.py::generate_reply` | Performs Library retrieval and citation validation; deprecated `/chat` remains stateless. | Preserve existing grounded answers. New user-memory tools run on persistent turns with trusted provenance; legacy stateless calls do not gain automatic memory writes. |
| `backend/app/langchain/chat_service.py` and `llm.py` | A single model invocation, no bound-tool execution loop. | Tool definitions alone are insufficient. Implement invocation, dispatch, result pairing, limits, and final-answer integration. |
| `backend/app/langchain/{learner_tools,rag_tools}.py` | StructuredTool factories bind trusted owner/workflow scope. | Follow these factories and their injection pattern; never add `learner_id` to model-visible arguments. |
| Prompt registry | Server-selected `PromptSource` and versioned prompts. | Register history/memory instructions and versions explicitly; users/models cannot choose prompt sources. |
| Installed Python packages | `langchain-core 0.3.86`, `langchain-openai 0.3.35`, SQLAlchemy 2.0.54, Pydantic 2.13.5. | Use installed `StructuredTool`, `AIMessage`, `ToolMessage`, and compatible tool-binding APIs. Do not copy LangChain 1.x `create_agent`/`ToolRuntime` examples or require a framework migration. |
| Alembic | Current source head `20261008_0005`; shared metadata registered in `backend/alembic/env.py`; Docker runs `app.db.migrate`. | Allocate the next revision against the actual head at implementation time. Use a frozen migration snapshot with the exact naming convention. |
| Architecture test | SQLAlchemy/psycopg imports are allowed only in `repositories` or `db` paths. | New SQL tables/adapters go under `history_management/repositories`, not a root `repository.py`. |
| `frontend/src/pages/SettingsPage.tsx` | One page, ProfileSettings and preference/data sections; no Settings tabs. | Introduce tab navigation; keep `/settings` as the existing default. Preserve profile/calibration tests and drafts. |
| `AppSidebar.tsx` | Bottom account drawer contains Settings, theme selector, and logout. | Add the Memories Settings shortcut within this drawer; preserve collapsed/mobile dismissal and keyboard behavior. |
| `App.tsx` | `/settings` and `/chat/:conversationId` already exist behind auth/profile gates. | Use `/settings?tab=memories`; no separate top-level navigation or route guard. |
| Frontend rendering | Shared React Markdown/Prism and `S1` Library citations; Library-specific SourceViewer. | History/memory references need separate types and tokens. Do not send chat references into SourceViewer or let them resolve as Library citations. |
| Frontend caching | Existing external chat store and `idb 8.0.3`. | Reuse account-lifecycle conventions, not the same transcript store. Memory pages load on demand; never fetch all memories at login. |
| Shared UI | Button, Input, Textarea, Select, Spinner and semantic theme tokens exist. | Reuse these primitives. No new theme system or feature-specific loading framework. |

This audit makes the plan compatible with the inspected checkout; it is not a guarantee against future code drift. Recheck the baseline and repository instructions before each phase.

## 3. Architecture and ownership

```text
Persistent chat orchestration / LangChain
    -> server-bound history-management tools
        -> HistoryRetrievalService -> canonical ChatReadFacade
        -> UserMemoryService -> memory repository + evidence validator
        -> RetrievalBudget / lifecycle policies

Settings Memories UI -> authenticated memory REST API -> same UserMemoryService

Profile and learner facts -> existing public facades, never direct table writes
```

Proposed module layout (split further only when responsibilities justify it):

```text
backend/app/history_management/
  __init__.py                 # public contracts/facade; no eager database/provider imports
  schemas.py                  # tool, API, evidence, reference and policy types
  service.py                  # composed public facade
  factory.py                  # pool, reader, policy and validator composition
  history/
    retrieval.py              # bounded search, exchange expansion, deduplication
    ranking.py                # deterministic relevance/ranking strategy
    reader.py                 # chat read adapter and evidence resolution
  memory/
    service.py                # user/AI admission, revisions and deletion
    validation.py             # provenance, explicitness, sensitivity and entailment
    lifecycle.py              # freshness, supersession, conflicts, suppression
    ranking.py                # bounded recall ranking
  repositories/
    tables.py
    postgres.py               # memory SQL only
    receipts.py               # tool receipts/job persistence when needed
  tools.py                    # two server-bound StructuredTool families
  budgets.py                  # shared lookup/write/cumulative token limits
  maintenance.py              # bounded maintenance service/CLI

backend/app/api/routes/memories.py
backend/app/langchain/history_orchestration.py  # model/tool loop adapter
```

History search SQL over chat tables stays behind a chat repository/read facade, so the new domain does not become a second owner of chat persistence. The new module owns its memory tables and optional search projections. Avoid circular imports between API routes and domain services: move reusable generation orchestration out of route functions when integrating the loop, keeping a thin compatibility wrapper.

The profile remains authoritative for its fields. Memory recall can expose relevant profile values through a typed facade with their origin, without duplicating them in memory rows. Learner mastery is never inferred or written by this module; observations, if later supported, use the existing immutable evidence contract.

## 4. Tool contracts

### 4.1 `history_lookup`

Model-visible arguments:

```json
{
  "scope": "current_chat",
  "query": "the Rust project we discussed",
  "chat_ids": [],
  "before_message_id": null,
  "after_message_id": null,
  "cursor": null,
  "limit": 3
}
```

- Scopes: `current_chat`, `selected_chats`, `all_chats` (always the current user's chats).
- Owner, current chat, current question, current turn/attempt, visible-message IDs and budget are runtime context, not tool arguments.
- `query` is required for multi-chat/all-chat searches. Current-chat browsing may omit it when an anchor/direction supplies a bounded window.
- Selected chat IDs and anchor IDs are individually ownership-checked. Reject ambiguous combinations, invalid cursors and excessive scope counts.
- Default current-chat search never includes messages after the accepted current-question sequence. Cross-chat hits carry observation dates and are not silently treated as facts known before their occurrence.
- Search includes both user and final assistant messages. Failed questions may be useful conversational evidence, but receive an explicit failed-turn label; hidden tool records are excluded.
- Find matching messages, expand to bounded neighboring exchanges, merge overlapping windows, then rank windows. Preserve roles, chronological order, source message IDs and timestamps.
- Prefer exact/phrase and lexical matching; use indexed trigram word matching for spelling variants. Reject empty/stopword-only cross-chat searches instead of scanning all history.
- Respect multilingual/code-heavy content. Select supported PostgreSQL text configurations explicitly; avoid assuming English-only stemming covers all users. Bound trigram fallback work and execution time.
- Exclude already-visible messages and previously returned spans. A merged window may explain omitted visible context without resending it.
- Return exact excerpts, match reasons, truncation/continuation information and opaque owner-bound cursors. Summaries, if added, are labelled derived text and resolve back to canonical messages.

Result shape:

```text
windows[]: reference_token, chat_id, chat_title, start/end sequence,
           messages[{message_id, role, occurred_at, content, truncated}], match_reason
next_cursor, exhausted, warnings[], tokens_used
```

Use bounded PostgreSQL full-text search first, with indexed trigram fallback. Do not start with `ILIKE '%query%'` scans, whole-transcript loading, or one query per hit. Batch exchange expansion. An optional semantic adapter is an independent projection, enabled only if measured paraphrase recall warrants it; reuse embedding infrastructure without mixing chat data into Library collections. Owner filtering occurs before candidate disclosure; canonical authorization is checked again before returning hits.

### 4.2 `user_memory`

One tool family with a discriminated action schema, keeping read/write permissions separate internally:

| Action | Model arguments | Behavior |
| --- | --- | --- |
| `recall` | Required query, optional categories/context, bounded limit | Return relevant active memories/profile values; no mutation or blanket dump. |
| `remember` | One claim, category/context, source message IDs, exact spans, direct/inferred classification | Propose admission; server validates and chooses status. |
| `revise` | Memory ID, expected revision, proposed claim, new supporting sources | Add a supported revision or mark a conflict; cannot replace user-confirmed content merely because the AI prefers a new wording. |

Manual confirmation/deletion are user REST actions. Do not give autonomous AI calls unrestricted hard-delete rights. A later chat-command UI can offer an authenticated confirmation action for “forget X”; that is optional, not required to complete this plan.

Write outcomes: `saved`, `already_known`, `pending`, `conflict`, `rejected`, or `unavailable`, with a safe reason, memory ID/revision when applicable, and evidence status. “I remembered that” is valid only after `saved`/`already_known`, never after an attempted or pending write.

Source IDs must belong to this user and be either the current persisted user question, visible user messages, or user evidence retrieved by this tool session. A model cannot nominate arbitrary unseen IDs. Assistant messages, retrieved documents, and tool output cannot establish a personal fact without user confirmation. Manual edits/additions are authenticated user assertions and do not need invented chat provenance.

## 5. Memory representation and PostgreSQL schema

Use normalized records, not one growing biography JSON document. Store one atomic claim per memory. All owned associations use composite ownership constraints where possible.

| Proposed table | Purpose and important fields |
| --- | --- |
| `hm_memory` | ID, owner, category, normalized subject/predicate/context key, atomic claim, origin, evidence type, status, sensitivity, pin, revision, stated/applicable/review/expiry timestamps, created/updated timestamps. |
| `hm_memory_evidence` | Owner, memory/revision, evidence kind, minimal exact supporting quote, source timestamp, message ID/sequence and source chat locator when available, explicit-consent evidence, validator/policy version. |
| `hm_memory_revision` | Supported revisions and supersession/conflict links; no overwriting of provenance. Payload-bearing revisions are purged on memory deletion. |
| `hm_memory_preferences` | Automatic remembering enabled/disabled; owner revision. Disabling writes does not secretly delete or disable recall of existing memories. |
| `hm_memory_suppression` | Minimal non-plaintext fingerprints/source-span identifiers preventing automatic recreation from unchanged forgotten evidence. No retained deleted claim or quote. |
| `hm_tool_receipt` | Owner, request/turn/attempt identifiers, operation fingerprint, result IDs/status and retry fencing. No permanent full transcript/tool-result copy. |

Use the next available Alembic migration after `20261008_0005`, not a hard-coded assumption that no intervening migration exists. Register runtime tables in shared metadata; freeze migration definitions and use the identical constraint naming convention. Verify upgrade, downgrade, and `alembic check` with existing identity/profile/chat/RAG records.

Index owner/status/category/context/time for memory lists and recall; add suitable text indexes; uniquely enforce idempotency and compatible single-valued fact keys. Do not impose one-memory-per-category: projects, goals and other multi-valued facts need separate scoped keys. Duplicate proposals attach genuinely new evidence rather than multiplying rows. Cap retained evidence/revision growth with an explicit policy that preserves meaningful corrections and necessary support.

Do not attach memory evidence to chat messages or turns with a restricting FK or `ON DELETE CASCADE`: current chat deletion physically removes those rows. Copy only the minimum supporting span after validating the live source. Source locators become unavailable when the original chat disappears, while the validated evidence snapshot remains owned by the saved memory. If a chat FK is used, ensure its lifecycle cannot block chat/account cleanup or null out a required owner.

## 6. Admission, stale facts, contradictions and deletion

### Admission

1. Validate shape, ownership, source visibility, exact span bounds, operation idempotency and budget.
2. Classify who the claim concerns and whether it is explicit, hypothetical, quoted, negated, temporary, third-party, or inferred.
3. Check sensitivity and specific user consent. Never store credentials, API tokens or authentication secrets, even when pasted inside a broader statement.
4. Check that the claim follows from its evidence. An exact quote match alone is not entailment. An AI confidence number is not proof.
5. Resolve duplicates, applicable scope and existing conflicts.
6. Commit the memory/evidence/revision atomically and return the actual outcome.

Use deterministic checks first. Where free-form paraphrase/explicitness cannot be established deterministically, use a bounded structured semantic verifier with versioned policy. Cache verification by evidence/claim/policy fingerprint; never repeat an expensive verifier for the same proposal. A verifier outage, timeout or ambiguity produces `unavailable` and persists nothing. A supported, non-sensitive inference may become pending. Run verification only on proposed writes, not a second extraction call after every ordinary chat turn. No claim that such verification eliminates every hallucination: adversarial and ambiguous cases must be tested and fail closed.

Inferred candidates are not injected as facts by recall and do not silently become active by accumulating model confidence or repeated assistant mentions. Sensitive pending claims must not be persisted without the required consent either.

### Freshness and conflict

- Keep `last_confirmed_at`, `last_accessed_at`, `valid_from/to`, and review dates distinct. Reading/repeating a fact never reconfirms it.
- Preferences: persist until contradicted, with category-specific review intervals.
- Current goals/projects/status: time-qualified, with shorter review horizons.
- Deadlines/schedules: expire based on their dates and timezone; elapsed deadlines become past events, not present instructions.
- Historical events: retain occurrence dates; do not describe them as current state.
- Profile fields: resolve through the profile facade, not stale copied rows.
- Explicit corrections may supersede an old claim in the same scope. Ambiguous or differently scoped statements coexist or become disputed, not last-write-wins replacements.
- User-authored/confirmed edits take precedence over inferred candidates. Later explicit contradictions still create a visible supported change/conflict rather than hiding relevant user evidence.
- Recall excludes stale/disputed/superseded candidates by default. If the user is asking about a historical fact, return applicable dated evidence with its status; do not silently promote it.
- Model-selected arbitrary expiry or importance cannot erase user-pinned memories. Pinning affects retention, not truth/freshness.

### Deletion and forgetting

- Deleting a chat removes it from history lookup and search projections. Active/manual-confirmed memories remain, with minimal supporting snapshots and “Source chat deleted.”
- Unsaved inferred candidates supported only by a deleted chat are not saved memories: remove them and their unsupported snapshots. Independent surviving evidence can retain a candidate.
- Deleting a memory removes claim text, evidence quotes, payload-bearing revisions, and search/vector payloads. Retain only minimum non-content deletion/suppression metadata.
- Forget suppression must prevent unchanged source evidence being mined again under a new wording. Source-span fingerprints support this without preserving deleted quote text. Manual re-add/explicit new permission has a controlled override; genuinely new direct evidence follows the reviewed policy.
- Manual deletion does not delete past chat messages. Explain this distinction where it helps the user make the deletion choice.
- All reads recheck canonical lifecycle. A stale search hit or delayed tool result cannot revive or disclose a deleted memory. Revalidate recalled references before final response construction if the memory revision changes during generation.
- Deleting a memory cannot retroactively remove text already sent to a model or stored in a prior assistant reply; do not promise that it can. Prevent future reuse and cache resurrection.
- Whole-account deletion, when the account lifecycle supports it, must also purge memory snapshots, suppressions and projections; surviving chat deletion is not permission to outlive the account.

## 7. Growth, latency and token budgets

Engineering defaults to validate, expose in configuration, and tune with fixtures:

| Limit | Draft starting point |
| --- | --- |
| History windows per lookup | 3, each expanded by bounded neighboring messages |
| Memory facts per recall | 5 |
| Memory claim length | 500 characters |
| Per-history-result token allowance | 1500 |
| Per-memory-result token allowance | 750 |
| Cumulative history/memory tool-result allowance per turn | 3000 |
| Total tool calls per turn | 6, including at most 2 memory writes |
| Active automatic memories / inferred candidates | 200 / 50 per user |

These are upper bounds, not a fixed number of history messages always sent to the LLM. Apply the smaller of each limit and the actual remaining prompt budget. The server controls caps; model arguments can request less, never override them.

- Preserve the current question, source-owned system instructions, current RAG evidence and output capacity. Count tool schemas, call arguments, ToolMessages and protocol overhead too.
- Support precise local tokenizer strategies where available, with conservative approximate fallback. Approximate counts are not exact context-window guarantees. Configure the real model capacity; the existing output reserve does not itself impose a completion limit.
- Build/serialize context once per invocation. Do not independently trim history in the chat service, route and module.
- Retain complete AI tool-call/result groups. Never orphan a ToolMessage or execute a truncated write argument.
- Cache lookups within the turn by normalized query/scope/revision; merge overlaps and deduplicate messages already supplied. Do not repeat unchanged RAG retrieval on every loop iteration.
- History lookup uses indexed candidates and batched context expansion. No whole-chat/all-chat materialization, N+1 fetching, or network token-count calls.
- Automatic capacity admission considers usefulness, evidence, freshness and scope. Archive/reject lower-value automatic entries deterministically; never silently discard user-created/pinned facts to make room. If manual capacity needs a limit, surface an actionable storage response instead of deleting data.
- Store ordinary questions and temporary details in history, not memory. Avoid a growing monolithic summary, recursive summaries becoming evidence, and embeddings of every unchanged turn.
- Expiry is enforced during recall even if maintenance has not run. Maintenance operates in owner-bounded batches with restart-safe cursors/leases, not a full-history LLM reread or untracked FastAPI background task.
- A separate permanent worker/service is not required just for lazy stale-state evaluation. Add a durable worker only if chosen semantic projections or deferred verification actually require it; define and verify deployment lifecycle in that phase.
- Log operational counts/timing/outcomes, not raw personal claims, source quotes, credentials or prompts.

## 8. Tool orchestration and persistent-chat integration

Implement a bounded model/tool loop compatible with installed LangChain versions:

1. `ConversationService` accepts/persists the user question and fences a generation attempt as it does now.
2. Bind immutable runtime scope: owner, conversation, current user message/sequence, turn, attempt, visible source IDs, settings and shared budget. Extend the job/read facade to supply the canonical current message ID; it is not currently passed to the generator callback.
3. Retrieve the existing Library packet once and select a bounded initial history packet. Register the two new tool families without prefetching all memories.
4. Invoke the provider with registered prompt sources and bound tools.
5. Validate/disallow unknown calls, enforce budgets and read/write permissions, dispatch through module facades, and append corresponding ToolMessages to in-flight model context.
6. Retry/recover safely using durable operation receipts. Provider call IDs alone are not stable across regenerated attempts; use a server operation fingerprint including source/claim/expected revision, plus attempt fencing. An already saved fact must not duplicate on retry.
7. Continue within a finite call/time budget; reserve capacity for a final answer. On limits/unavailability, produce a clear bounded result or recoverable failure rather than loop indefinitely.
8. Validate references, construct the final visible response, and let the canonical chat service append it exactly once.

Read tools may run concurrently when independent and within limits. Memory writes affecting the same fact are serialized and revision-checked. No transaction is open while a provider or verifier is called. A manual edit/delete racing AI work must win through revisions/suppression and canonical rechecks, not model confidence.

Keep internal tool-call events/receipts outside ordinary user-visible `chat_message` pages. Although the SQL role check accepts `tool`, current frontend types and history adapters only handle user/assistant and would misrender/exclude hidden records. Do not put tool rows there without a deliberate projection/migration. Internal receipts must not hold a restricting FK to physically deleted `chat_turn` rows or retain personal tool payloads after deletion.

The deprecated stateless `/chat` path can remain backward-compatible and read-only; it lacks trusted persistent evidence for autonomous writes. Preserve provider-configuration/failure semantics, conversation idempotency, source selections, current citations and recovery behavior. Tool-capability-unavailable providers must expose a clear unavailable mode, not claim a successful lookup or memory save.

## 9. Frontend: Settings Memories tab and drawer entry

### Navigation and tab behavior

- Existing drawer Settings link remains `/settings` and opens the current profile/preferences tab.
- Add a **Memories** shortcut in the same bottom drawer Settings area, linking to `/settings?tab=memories`; do not create another primary sidebar section or redesign the drawer.
- Add dedicated Settings tabs: **Profile & preferences** (default) and **Memories**. Preserve other query parameters; unknown `tab` values fall back safely. Refresh, browser back/forward and deep links retain the selected tab.
- Query-param links need query-aware active styling: React Router pathname-only `isActive` is insufficient to distinguish these two drawer destinations.
- Use keyboard-accessible tab controls with correct role/selection/panel relationships, arrow-key behavior and focus management. On mobile, keep tabs and actions inside the viewport.
- Preserve unsaved profile and memory editor drafts when switching tabs. Keep visited panels mounted but hidden, or provide explicit draft state outside conditional panels; do not silently unmount `ProfileForm` and discard local changes. Do not fetch memory pages until the Memories tab is first visited.

### Memories panel

Use a focused list/detail layout, not a dashboard of metric cards. Show:

- A short explanation of what memory does and that saved memories can survive chat deletion.
- Automatic remembering toggle, with existing-memory recall behavior explained.
- Search, status/category filters, and bounded cursor pagination.
- Atomic memory text with category, applicability, saved/confirmed date, status and pin indicator.
- Compact rows expanded into details: supporting evidence, origin, freshness/review information and source chat link or deleted-source label.
- **Add memory**, **Edit**, **Confirm candidate**, **Pin/unpin**, **Delete**. A candidate can be edited before confirming; there is no blanket “approve all” default.
- Explicit stale/disputed handling: confirm current applicability or correct the claim. Simply opening a row does not reconfirm it.
- Manual create/edit forms support category/context, optional validity date and sensitivity declaration. Authenticated user submissions count as user evidence; do not fabricate a chat source.
- Clear delete confirmation, then remove only the affected record after server acceptance. For conflicts, retain the draft and show the latest version; do not silently overwrite or discard user input.
- Loading, empty, unavailable, validation, quota, conflict and retry states using shared primitives and semantic Light/Dark/System tokens.
- No code execution or raw HTML from claims/quotes. Plain text is sufficient for memory rows; use shared Markdown/Prism only where an evidence preview genuinely benefits.

Suggested frontend files:

```text
frontend/src/components/memories/
  MemoriesSettings.tsx
  MemoryList.tsx
  MemoryEditor.tsx
  MemoryDetails.tsx
frontend/src/services/memories.ts
frontend/src/types/memories.ts
frontend/src/stores/memoryStore.ts       # only if shared/delta state is justified
frontend/src/components/chat/HistoryReferenceViewer.tsx
```

Memory management is fetched on tab visit, not included in chat/login bootstrap. Mutations update individual records; do not submit the entire memory collection. Use a single-flight account-scoped memory store/request layer with revision-aware merge and stale-request cancellation. Start with bounded in-memory pages; persist sensitive memory payloads in IndexedDB only if an actual offline requirement is agreed. Existing chat `idb` dependency is available but does not require caching all personal memory locally.

BroadcastChannel can invalidate/refetch changed loaded pages across tabs, and focus/reconnect can reconcile revisions. Avoid inventing a second full chat sync stream or permanent polling for this Settings page. Cached pages carry their fetch revision and are invalidated when membership/sort changes; resetting a filtered page on mutation is allowed to prevent keyset gaps, without downloading all memories. Logout/account switch clears memory payloads, editors and reference dialogs.

### Response references

- Introduce typed `history_references` and `memory_references` alongside existing Library `sources`; hydrate them through existing assistant-message metadata persistence.
- Use separate allowlisted token namespaces such as `H1` and `M1`; retain `S1` Library behavior.
- A history reference opens a bounded owned message window or navigates to the saved chat with a supported message anchor. Current ChatPage has no message-anchor feature; add it if navigation is selected, rather than relying on a nonexistent `#message` handler.
- A memory reference opens current owned memory details or the Settings Memories tab. Deleted references render unavailable text, not a resurrected snapshot.
- Extend the citation transformer/types deliberately. Unknown markers and markers in user messages remain ordinary text; existing citationPlugin only recognizes `S\d+`.
- Library SourceViewer remains specific to document sources. A separate history viewer may reuse shared dialog/rendering primitives, not fabricate document IDs for chat messages.

## 10. User-facing API contract

Use a single authenticated API family under `/api/v1/memories`, with thin routes calling the same service as the tools:

| Endpoint | Contract |
| --- | --- |
| `GET /memories` | Search/filter with keyset cursor and bounded limit; metadata summary only. |
| `POST /memories` | Manual creation; request idempotency key, atomic claim/category/context and explicit user source. |
| `GET /memories/{id}` | Current details/evidence and revision; do not return the entire source transcript. |
| `PATCH /memories/{id}` | Expected revision; explicit allowed edits, confirmation, pin or current-applicability assertion. |
| `DELETE /memories/{id}` | Expected revision; content purge, suppression and projection invalidation. |
| `GET /memories/preferences` | Current automatic-memory setting/revision. Register fixed paths before `/{id}`. |
| `PATCH /memories/preferences` | Expected revision; automatic remembering toggle. |

A bounded authenticated history-reference read endpoint may be added for the viewer; cross-chat free search is an internal tool capability unless a product history-search UI is separately requested. Routes enforce identity/profile access consistently with Settings, use existing cookie trusted-origin validation, and never accept an owner from request bodies. Define typed responses and stable error codes for unavailable, not found, revision conflict, unsupported evidence, consent required, capacity and budget exhaustion.

## 11. Phased implementation tracker

### Implementation reconciliation

The earlier sections preserve design rationale. The following choices supersede speculative fields/layouts above; they are deliberate implementations rather than missing engines:

- SQL history retrieval lives in `chat/repositories/history_reader.py`; `history_management/service.py` composes it with the memory repository and validator. No empty ranking/lifecycle engines or second transcript were introduced.
- Tool history anchors are `before_sequence` / `after_sequence` for the current chat, plus timezone-aware cross-chat date filters. Each call returns at most three windows; subsequent calls use these bounded anchors and exclude already surfaced messages. Opaque cursors are used for the Settings memory list, not the internal history tool.
- Memory stores atomic content, category, provenance, status, expiry and conflict/revision metadata. It does not invent normalized subject/predicate truth keys. The verifier checks relevant candidates; explicit conflict resolution is revision-fenced and manual. AI `revise` requests review instead of overwriting an existing memory.
- Manual forms expose content, category, pin and validity controls. Authenticated manual submission supplies consent and provenance; it needs no redundant sensitivity declaration or fabricated chat source. The list has keyword/status filters; category remains visible on records and selectable when adding them.
- Verifier failures save nothing, including sensitive candidate content. Pending admission requires a successfully verified, supported inference with any required consent.
- Tool dispatch is serialized for deterministic writes, references and cumulative budgets; reads batch SQL expansion and use a turn-local cache. No additional worker or semantic-vector projection was justified.
- Prompt accounting retains the codebase's approximate tokenizer with explicit schema/protocol/output reserves; result budgets use conservative UTF-8 bytes. This is not an exact arbitrary-provider tokenizer guarantee.
- Evidence is capped at five quotes per memory, with source hashes retained for suppression when old quotes are pruned. Revisions and receipts keep metadata rather than historical personal payloads.
- Native reference dialogs re-fetch current owned data; separate H/M tokens preserve Library S citations. Memory Settings and reference viewers are lazy bundles and have no IndexedDB personal-memory cache.

These decisions preserve the requested user policies and complete frontend/tool/persistence behavior. Lexical retrieval and semantic admission are not universal paraphrase or hallucination guarantees; live-model quality evaluation remains an operational activity, not claimed by deterministic protocol tests.


### Phase 0 — Review and contract freeze

- [x] Inspect current chat storage, generation, adapters, versions, Settings/drawer and citation paths.
- [x] Record the three agreed memory policies and the requested Settings frontend scope.
- [x] Apply conservative manual-only inferred-candidate promotion policy.
- [x] Review draft quotas, freshness categories, consent UX, citation UX and automatic-memory default.
- [x] Record subsequent user authorization to implement the plan end-to-end.
- [x] Recheck AGENTS instructions, git state, migration head and dependency APIs; preserve unrelated work.

**Exit:** Agreed policy/contract document, concrete phase ownership and no hidden framework upgrade or UI assumptions.

### Phase 1 — Module contracts and canonical read facade

- [x] Add provider-independent typed facade/protocols and factory boundaries.
- [x] Extend canonical chat read contracts for owned evidence lookup and batch window expansion.
- [x] Implement tool schemas and injected runtime scope, including current canonical user-message ID.
- [x] Preserve/move the existing LangChain history reader with a compatibility shim if necessary.
- [x] Register history/memory prompt sources and versions.
- [x] Verify public contracts import without eager database/model dependencies and satisfy architecture tests.

**Exit:** Callable typed interfaces with owner/budget/provenance enforcement; no memory feature marked complete yet.

### Phase 2 — PostgreSQL memory persistence and migration

- [x] Implement owned memory/evidence/revision/preferences/suppression/receipt tables and repositories.
- [x] Add a frozen additive migration at the actual next head with consistent constraint names.
- [x] Implement transactional manual create/edit/confirm/delete and idempotency.
- [x] Prove that chat message/turn deletion cannot cascade away saved memories or be blocked by receipts.
- [x] Verify migration rehearsal, no drift, rollback and preservation of existing records in an isolated database.

**Exit:** Durable user-managed memory with complete ownership and revision guarantees.

### Phase 3 — History retrieval engine

- [x] Add indexed lexical search and bounded spelling fallback behind the chat read facade.
- [x] Backfill/index existing live messages without changing canonical content or blocking deployments unnecessarily.
- [x] Implement current/selected/all-chat scope validation, dates/anchors, batch expansion and overlap merging.
- [x] Add visible-message/result deduplication, deterministic ranking, current-chat sequence continuation and owned memory-list cursors.
- [x] Exclude deleted chats and hidden execution records; label failed questions/assistant evidence appropriately.
- [x] Evaluate exact names, typos, paraphrases, code, multilingual inputs, unrelated queries and long conversations.

**Exit:** Relevant exact conversation windows returned within query/token limits; no all-history scan or N+1 expansion.

### Phase 4 — Memory admission, recall and lifecycle

- [x] Implement evidence-span validation, explicitness/subject checks and consent rules.
- [x] Add bounded semantic validation where required; ambiguity/provider failures save nothing.
- [x] Implement duplicate resolution, scope-aware conflicts, revisions and the reviewed candidate-promotion policy.
- [x] Implement relevance/freshness recall and current profile facade values without profile duplication.
- [x] Add deterministic retention/admission, candidate limits and bounded maintenance.
- [x] Implement chat-deletion evidence detachment, memory-content purge, suppression and cache/index fencing.
- [x] Make memory-disable and manual-edit/delete races authoritative across AI retries.

**Exit:** Explicit active facts are supported; inferred/sensitive/stale/conflicting cases cannot silently become current facts.

### Phase 5 — Real model/tool execution and persistent-turn integration

- [x] Bind and dispatch both tool families using installed LangChain APIs and trusted persistent-turn context.
- [x] Add a BaseMessage-aware bounded tool loop through MentraLLM and registered prompts.
- [x] Account for schemas, tool arguments/results, current RAG/system/current-question and output budgets.
- [x] Add durable operation receipts and attempt fencing without a second transcript or blocking chat-deletion FK.
- [x] Preserve model failures, turn retries, cancellation/shutdown, lease bounds and exactly-once final persistence.
- [x] Preserve grounded Library citations; verify unavailable/unsupported tool providers and legacy stateless compatibility.
- [x] Persist typed history/memory reference metadata in final assistant messages.

**Exit:** Real agent calls can retrieve and remember, using bounded context and truthful save outcomes across retry/restart.

### Phase 6 — REST endpoints and Settings frontend

- [x] Expose bounded authenticated manual memory/preferences/detail APIs.
- [x] Add the Memories shortcut in the existing bottom drawer Settings area.
- [x] Add deep-linkable accessible Settings tabs while preserving the default profile/preferences page and unsaved drafts.
- [x] Build memory list/search/filter/pagination and evidence details.
- [x] Build manual add/edit/confirm/pin/delete and automatic-memory controls with server revisions.
- [x] Implement account-scoped single-flight requests, targeted mutation merges, cross-tab invalidation and logout clearing.
- [x] Verify implemented loading/error/conflict/empty flows, server quota enforcement, keyboard focus and theme/mobile regressions.

**Exit:** A user can fully manage memories from the intended Settings location without breaking profile/calibration workflows.

### Phase 7 — Chat references and lifecycle reconciliation

- [x] Extend chat types/citation allowlists for distinct history/memory references without changing Library S-tokens.
- [x] Build owned history-window viewing or verified anchored chat navigation, and memory-detail linking.
- [x] Add explicit deleted-source/deleted-memory UI and prohibit stale payload resurrection.
- [x] Wire deletion/maintenance receipts to canonical chat lifecycle transactions or a durable transactional event contract; no best-effort-only cleanup.
- [x] Recheck returned source/memory revisions before final answer publication, handling concurrent edits/deletion safely.

**Exit:** Tool-backed responses are explainable and navigable; deletion semantics remain consistent across backend/UI/indexes.

### Phase 8 — Adversarial, integration and performance verification

- [x] PostgreSQL: ownership/composite constraints, idempotency, competing writes, manual-vs-AI edits, forget suppression, delete-vs-generation, detached evidence and rollback.
- [x] Memory fixtures: explicit/inferred admission, sensitive consent, secrets, conflicts, evidence visibility, expiry/pins, profile facade and fail-closed verifier behavior. Free-form semantics depend on the configured model and are not universally certified by fixtures.
- [x] Tool loop: actual AIMessage calls and paired ToolMessages, unknown tools/arguments, repeated calls, verifier/provider outage, budget exhaustion, cached/batched reads, serialized tool dispatch and competing transactional writers, lost HTTP response and process restart.
- [x] Retrieval: multi-chat keywords required, owner filtering before disclosure, empty/stopword queries, typo fallback bounds, overlapping windows, visible-context exclusion, multilingual/code inputs and deleted records.
- [x] Browser: drawer entry, deep links, tab keyboard/back/refresh, profile/memory draft retention, manual CRUD, candidate confirmation, conflicts, filters/pages, cross-tab changes, logout/account switching, unavailable references and existing Markdown/Prism/RAG behavior.
- [x] Measure query counts/index plans and cold/warm latency on 10,000 messages/500 memories; verify bounded results, quotas, tool budgets and cache lifecycle.
- [x] Run appropriate existing auth/profile/chat/RAG/architecture regressions and final new tests against production-built assets; record actual counts, not expected counts.

**Exit:** Reported evidence proves behaviors and budgets; remaining limitations are explicit. Do not claim a universal hallucination guarantee.

### Phase 9 — Docker images, runtime rehearsal and documentation

- [x] Run frontend TypeScript/Vite build, theme checks, relevant backend checks and `git diff --check`.
- [x] Rebuild backend and frontend Docker images with new migrations/configuration/prompt sources.
- [x] Smoke-test isolated rebuilt images with an actual tool-capable provider stub, persistence across restart, manual memory UI/API, deletion retention/purge, and owner isolation.
- [x] Confirm no additional worker/semantic projection was needed; existing runtime lifecycle remains sufficient.
- [x] Document configuration, quotas, maintenance/backfill, source retention, model compatibility, API/tool contracts and verification artifacts.
- [x] Report whether the application database was migrated and application containers restarted separately from image builds. Do not imply deployment from a successful build.

**Exit:** End-to-end verified images and a reproducible operational handoff. No unapproved deployment or application database experiment.

## 12. Phase evidence log

| Phase | Status | Files/migrations | Verification evidence | Open gaps/deviations |
| --- | --- | --- | --- | --- |
| 0 | Complete | This tracker; installed APIs and baseline checked | User authorized end-to-end implementation; conservative promotion applied | Engineering choices reconciled above |
| 1 | Complete | `history_management/{contracts,schemas,factory,tools}.py`; canonical history reader; prompt registry | Lightweight imports, architecture checks, trusted scope tests | Existing public history adapter retained |
| 2 | Complete | Owned repository tables; Alembic `20261008_0006` | Upgrade/downgrade/no-drift rehearsal; revision/idempotency/deletion tests | Rehearsed only on dedicated databases |
| 3 | Complete | `chat/repositories/history_reader.py`; concurrent FTS/trigram indexes | Scope/date/Unicode/code/dedup tests; two read SELECTs; indexed performance fixture | Lexical retrieval; 2-second SQL deadline; no semantic projection |
| 4 | Complete | Memory validator/repository/service/maintenance | 42 focused history-management tests cover admission, suppression, conflicts, lifecycle and ownership | Verifier failure saves nothing; manual promotion; documented retention |
| 5 | Complete | LangChain orchestration, domain generation, persistent-turn scope | Actual ChatOpenAI protocol in rebuilt API; paired tool messages, references, receipts and restart | Serialized dispatch; approximate prompt accounting |
| 6 | Complete | Memory REST API; Settings tabs/drawer; memory components/client | Eight final dedicated memory browser scenarios plus full 44-test browser regression | On-demand bounded in-memory pages; no offline memory cache |
| 7 | Complete | H/M citation types/viewer; transactional detach and final reference fences | Browser citations, owned detail APIs, concurrent revision tests and Docker deletion/purge checks | Deleted references show unavailable; transcript deletion remains separate |
| 8 | Complete | Backend/browser suites and performance harness | Full backend suite 292 tests; final focused suite 68 tests; full production-browser suite 44 tests | Counts overlap; local model fixture verifies plumbing, not general model quality |
| 9 | Complete | Both rebuilt Docker images; runtime harness; operational docs | Nine final image/runtime checks, including actual Nginx browser CRUD and API restart | Application database not migrated; application containers not deployed |

## 13. Definition of done and review checklist

- [x] Both actual tool capabilities work in persistent chat; schemas alone do not satisfy delivery.
- [x] Extra history is retrieved on demand from canonical owned messages and remains bounded.
- [x] Memories are independently persistent, evidence-backed and time-qualified; not always injected.
- [x] Explicit-only automatic saves, consent-only sensitive saves and pending inferences follow the reviewed policies.
- [x] Saved memories survive chat deletion, while deleted memory content does not survive in audit/search/cache copies.
- [x] User management works from the bottom drawer's Settings destination and dedicated Memories tab.
- [x] Profile/learner authority, current chat sync/recovery, Library retrieval and citations remain intact.
- [x] Model retries, concurrent manual edits and deletion cannot duplicate or resurrect memory.
- [x] Token, latency, capacity and ownership limits are enforced server-side and verified.
- [x] Migration rehearsal, production-browser checks and isolated Docker runtime verification are recorded.
- [x] Required end-to-end scope is complete; applied engineering choices and verification limits are documented.

## 14. Reference documentation

- [LangChain long-term memory](https://docs.langchain.com/oss/python/langchain/long-term-memory): conceptual guidance only; current examples use newer APIs than this checkout's 0.3 stack.
- [PostgreSQL 17 full-text search](https://www.postgresql.org/docs/17/textsearch-controls.html).
- [PostgreSQL 17 pg_trgm](https://www.postgresql.org/docs/17/pgtrgm.html).
- [Existing persistent-chat design and verification](docs/persistent-chat.md).
- [Existing code rendering](docs/code-rendering.md).

**Re-pass completed:** Shared frontend switches, memory preference enforcement, stale-request/revision recovery, atomic conflict corrections, suppression, source-based freshness and corrected-save retry receipts were verified. See the verification report for actual test counts and final image IDs.

**Implementation handoff:** See [verification report](docs/history-management-verification.md) and [operational documentation](docs/history-management.md). All implementation phases are complete. Image deployment and application-database migration remain separate operational actions.
