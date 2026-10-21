# History management and user memory

The standalone `app.history_management` module provides on-demand conversation retrieval and evidence-backed persistent user memory. Canonical transcripts remain in `app.chat`; there is no second transcript. Chat owns separate private rolling summaries for prompt compaction; these are not evidence-backed user memories.

Every authenticated chat turn also receives a bounded persistent memory overview, maintained incrementally by the shared LLM in a durable background worker. It is separate from the per-chat summary and does not replace full recall. System prompts require relevance for both retrieval and response generation. See [persistent memory summaries](memory-summaries.md) for independent limits, freshness guarantees, deployment and recovery.

It also composes Events as `HistoryManagement.events`. Events owns schedules/proposals and its PostgreSQL adapter; memory tools do not write events. The Progress UI provides Learning and Events tabs, and the Events worker publishes into independent Notifications. See [Events](events.md) and [Notifications](notifications.md).

## User interface

The sidebar's bottom account drawer contains Settings and a Memories shortcut. `/settings?tab=memories` opens the dedicated Settings tab. The profile panel and memory editor remain mounted when switching tabs, preserving drafts. Memory management and reference viewers load as separate JavaScript chunks; memory records are fetched only when the tab opens, not on login.

Users can add, edit, confirm, pin and delete memories; inspect supporting quotes and source dates; search/filter/paginate; and disable future AI writes. Disabling AI writes leaves saved memories available for recall. Manual mutations merge the affected row and invalidate pagination boundaries; other tabs receive account-scoped invalidations. Focus/refresh reconciliation updates the list and selected evidence. Logout or account switching unmounts and clears this component's state. Personal memory records are not written to IndexedDB.

Conflicting memories require an explicit native-dialog review. Choosing a current statement atomically activates it and marks the identified predecessor(s) conflicting, excluding them from recall. Concurrent revisions reject the entire resolution. Pinning controls retention and does not make an expired or inferred fact true.

History citations use `H` tokens, memory citations use `M` tokens, and Library citations retain `S` tokens. Only server-returned references resolve. User messages and code blocks do not turn these markers into citations. Viewers re-fetch owned content; deleted references show an unavailable state. Memory references show the current revision and disclose edits since the original answer.

## Tools and boundaries

`history_lookup` additionally supports exact current-chat `message_id` retrieval and `content_offset` continuation. Ownership, deletion and future-sequence fences apply; partially delivered originals remain recoverable. Summaries never authorize evidence writes. It accepts current/selected/all-chat scope, keywords, a maximum of three windows, optional timezone-aware date bounds, and current-chat sequence pagination. Cross-chat searches require keywords. Source messages retain roles, timestamps and exchange status, including failed questions. Candidates use PostgreSQL full-text search with indexed trigram fallback and a two-second per-statement database timeout for broad terms. Expansion takes one additional read query and avoids messages already available to the model.

`user_memory` supports keyword recall and evidence-backed remember/revise proposals. Recall returns at most five active, unexpired facts plus relevant current profile fields through the profile facade. The model cannot select the owner. Writes accept only exact spans from owned user messages visible to that session or returned by its history tool. Assistant messages, documents and arbitrary unseen IDs cannot become personal evidence.

Admission first checks provenance and credential patterns, then performs a bounded structured semantic validation. Explicit supported statements can become active; inferences remain pending until the user confirms them. Sensitive information requires a specific affirmative remember request. Unsupported/transient statements, profile duplicates and credentials are rejected. Verification outages save nothing, rather than persisting potentially sensitive candidates. This is a conservative safeguard, not a universal guarantee of model correctness.

Related-memory admission uses ranked OR keywords and previously recalled IDs, so a changed value need not match the old value literally. The verifier identifies actual conflicting IDs from that bounded set. Search remains lexical: arbitrary paraphrases are not guaranteed to match. Tool instructions ask the model to recall stable related keywords before proposing corrections. AI revision attempts require user review instead of silently overwriting independently saved records.

The public contracts import without SQLAlchemy or LangChain. The factory composes the canonical chat read facade, owned PostgreSQL memory repository, validator, optional profile facade and independent Events service with optional public learner context lookup. SQL lives under repositories. Learner mastery and evidence are not modified by this module.

## Durable execution and budgets

Persistent generation passes canonical user-message/turn IDs, attempt and visible message IDs. Complete AIMessage/ToolMessage groups are preserved; admission remains ordered while independent read tools can run concurrently. Default main-loop limits are six tool calls, two writes and five model invocations; the retrieval allowance is bounded separately. Conservative same-turn caching reuses equivalent reads without bypassing current authorization or source revisions.

Tool packets default to a shared 3,200-token/12,800-byte ceiling. RAG-planned turns allow eight calls and 4,800 tokens/19,200 bytes for targeted refinements; admission still reduces these allowances to fit the selected total input limit. RAG prefetch warms private cache entries and injects no passages unless retrieval is requested. Chat answering uses 8,192 input tokens, a bounded 12,288-token recovery allowance, 1,800 recent-history tokens and separate private summaries. Assessment workflows retain their 16k limit. The offline counter avoids request-time downloads, and output reserve is enforced as provider `max_tokens`. See [summary policy](../backend/app/chat/SUMMARIES.md) and [cache policy](Tool_Cache_Policy.md).

Writes hold no locks during model verification. Database mutations share chat's owner lock, fence running turn attempts and leases, and record content-free operation receipts. The receipt key derives from turn ID and normalized proposal, not provider call ID. A retry cannot duplicate a saved operation or re-run its verifier unnecessarily. Manual saves have a separate request UUID and payload fingerprint. Expected revisions fence manual edits and conflict resolution. Final assistant publication rechecks owned memory revisions and source-chat existence under the same lock; changed/deleted references produce a retry message instead of publishing obsolete tool-backed claims.

## Storage, deletion and maintenance

Chat, memory and Events now use the public `app.db.owner_transactions.lock_owner`
boundary backed by the existing `chat_sync_state` row. Memory adapters no longer
import the private chat lock method. Chat deletion detaches both memory and event
evidence in the same owner-locked transaction; saved events survive source deletion.
Memory maintenance retention does not apply to Events reminder ledgers or receipts.

Migration `20261008_0006` adds memory, evidence, revision metadata, preferences, suppression and operation-receipt tables. Composite owner FKs protect evidence and revisions. Source message/turn IDs are snapshots without FKs into destructible chat records. `pg_trgm` is installed in `public`; this requires the deployment database to permit that extension. Existing chat indexes build concurrently before the new tables transaction; cancelled invalid indexes are safely rebuilt on retry. Downgrade preserves canonical chat data and leaves shared extensions installed.

Deleting a chat happens transactionally with evidence detachment. Saved, previously confirmed, manually controlled or pinned memories retain minimum quoted evidence and dates, with `source_deleted=true`. Untouched unconfirmed AI candidates supported only by the deleted chat are removed. Deleting a memory purges its claim, evidence and revision metadata, removes copied conflict snapshots, and invalidates receipt targets. Non-plaintext claim/source fingerprints prevent automatic recreation from the same evidence. Original chat messages and already delivered answers remain; deleting memory is not retroactive transcript deletion. A new explicit manual entry may save the fact again.

Automatic capacity defaults to 200 current active records and 50 pending/conflicting candidates. Expired active memories are excluded from recall and the current-active quota. There is a transparent 1000-record account cap, with no silent eviction of user-created or pinned records. Maintenance removes old untouched AI candidates and old content-free receipts in bounded owner batches; it does not re-read transcripts with an LLM. Suppression fingerprints remain until an account purge. Whole-account deletion must include these tables if that lifecycle is introduced.

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.history_management.maintenance --owner <learner-uuid> --limit 100
```

Current maintenance retention is 90 days for untouched candidates/receipts. No additional permanent worker is needed. Deployments needing a different maintenance retention can change the bounded repository policy; active-memory freshness and admission quotas are environment-configurable.

| Setting | Default |
| --- | --- |
| `MEMORY_ACTIVE_LIMIT` | 200 |
| `MEMORY_PENDING_LIMIT` | 50 |
| `MEMORY_GOAL_DAYS` | 30 |
| `MEMORY_FACT_DAYS` | 180 |
| `MEMORY_PREFERENCE_DAYS` | 365 |

Explicit evidence-backed deadlines can shorten automatic freshness; manual confirmation can clear an expiry. Access does not refresh confirmation. Chat input, recovery, recent history and summary controls are documented in [persistent chat](persistent-chat.md); assessment context remains separately bounded.

Automatic freshness is measured from the supporting user statement's timestamp, not the day an old statement is retrieved. Already expired AI proposals are rejected. A new explicit statement can reaffirm the same AI-origin fact, while inferred candidates still require manual confirmation. A manual correction refreshes applicability unless an explicit expiry is supplied, and retires the old claim/source hashes so an AI retry cannot recreate the outdated assertion. Manual entry of an existing pending statement confirms it as a user assertion; entry of a conflicting statement still requires review.

## Preference enforcement and shared switches

The **Let Mentra save useful memories** switch persists a revision-fenced account preference. Both the domain admission path and the owner-locked write transaction check it. Turning it off during semantic verification prevents the subsequent commit. It blocks AI remember/revise proposals, while manual management and recall of existing memories continue to work.

The frontend uses `components/ui/Toggle.tsx` for all four binary option controls: memory admission, activating a learning context on upload, archived-source selection and archived-source viewing. The native checkbox carries switch semantics, a labelled description, keyboard operation, disabled state, a 44-pixel interaction target, semantic theme colors and reduced-motion support. Markdown task-list checkboxes and multi-option theme radios retain their appropriate semantics.

Settings requests cancel/fence stale pagination and evidence responses. Preference conflicts reload the authoritative value, and delete conflicts display the current statement before another explicit confirmation. Conflict details load current predecessor revisions; resolution submits exactly the revisions the user reviewed. The editor can prepare a corrected conflicting statement and review/commit it atomically. Drafts survive a rejected save; changed create payloads receive a new idempotency key while identical retries keep their key. Provider receipts cannot report an obsolete successful save after a manual correction.

## Authenticated API

All endpoints are under `/api/v1/memories` and require onboarded identity. Cookie mutations inherit the existing origin checks. Fixed routes precede the UUID detail route. UUID, lengths, enum statuses, date zones, page sizes and revisions are validated server-side.

| Method/path | Purpose |
| --- | --- |
| `GET /` | Bounded keyword/status page with keyset cursor |
| `POST /` | Manual create with `client_request_id` |
| `GET /preferences` | Automatic-write policy and capacity limits |
| `PATCH /preferences` | Revision-fenced policy update |
| `GET /{id}` | Owned current memory and bounded evidence |
| `PATCH /{id}` | Content, pin, confirm, expiry or explicit conflict resolution |
| `DELETE /{id}?expected_revision=...` | Content/evidence purge and suppression |
| `GET /history/{conversation_id}?sequence=...` | Owned bounded reference window |

Legacy stateless `/chat` keeps its existing response contract and does not get automatic personal-memory writes. Unsupported tool providers can fall back to grounded ordinary chat without claiming memory/history operations succeeded.

## Verification

See [implementation tracker](../Mentra_History_Management_Implementation_Plan.md), [runtime evidence](history-runtime-verification.json) and [performance evidence](history-performance-verification.json). Verification uses dedicated test PostgreSQL resources, unique schemas/databases and a deterministic local provider. It verifies provider/tool plumbing, not real-model admission/retrieval quality across every phrase or language.

Reproduce backend checks with an explicitly dedicated `TEST_DATABASE_URL` (never the application `DATABASE_URL`):

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
.\.venv\Scripts\python.exe -m testing.history_performance
```

Build frontend assets with `VITE_API_URL=http://127.0.0.1:18003`, then run `FRONTEND_PREVIEW=1 npm run test:e2e` in `frontend` with the same dedicated test URL. The browser server uses real auth, PostgreSQL migrations, chat orchestration and memory services, with deterministic inference.

```powershell
docker compose build backend frontend
.\.venv\Scripts\python.exe -m testing.history_runtime
```

The runtime harness starts uniquely named disposable containers/databases, exercises actual ChatOpenAI tool and structured-output protocols, restarts the API, and drives the rebuilt Nginx UI through a test-only URL proxy to the isolated API. It removes its own resources afterwards. Image builds and isolated verification do not migrate the application database or restart application containers.
