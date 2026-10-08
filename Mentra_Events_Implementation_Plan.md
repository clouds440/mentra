# Mentra Events Implementation Plan

**Status:** Implementation started on 2026-10-09. The first Events backend increment (manual CRUD/lifecycle, preferences, temporal preview, owned persistence, receipts and sync) is implemented and verified in isolation. Full delivery is incomplete: safe graph dependency selection, automatic capture/confirmation, Notifications/worker and the Progress frontend remain open. See section 12 and `docs/events.md` for actual evidence and limits.

**Scope:** A reusable events submodule inside history management, separate event storage and tools, automatic capture, durable LangGraph human confirmation, manual management in Progress, a standalone reusable Notifications module with in-app delivery, strictly one reminder per event, and a learner-backed Learning tab. This plan supplements the implemented memory module; it does not merge the two domains.

## 1. Decisions and boundaries

| Decision | Policy |
| --- | --- |
| Module ownership | `history_management.events` is a dedicated domain submodule composed by the existing history-management facade. No separate microservice or replacement memory module. |
| Data separation | Events, proposals, preferences, evidence, receipts and reminder delivery have their own tables. Never store event dates or pending event proposals in `hm_memory`. |
| Tool separation | Event lookup and event management are separate tools from `user_memory` and `history_lookup`. |
| Automatic capture | Separate **Let Mentra add events** switch, enabled by default. The memory switch does not control events, and the events switch does not control memory. |
| Source deletion | Saved events survive chat deletion until the user deletes them. Minimum evidence is retained with a deleted-source label. |
| Uncertainty | Ask the user to review unclear intent, dates, conflicting changes or duplicate matches. Pending proposals are not saved events and cannot trigger reminders. |
| Manual management | Users can add, edit, complete, cancel, reopen and delete events, manage reminder settings and resolve proposals. |
| Reminder limit | At most one durable reminder per event lifetime, including retries, date edits, reopen, read/dismiss and inbox retention. This is an invariant, not a configurable maximum. |
| Notifications ownership | Separate `app.notifications` module implemented in this delivery; Events is its first producer. Own inbox, delivery receipts, unread state, preferences, sync and shared UI independently of history management. |
| Reminders | Include durable in-app reminders in this implementation. External email, browser push, OS notifications and calendar integrations are separate future capabilities. |
| Frontend location | Progress gains Events and Learning progress tabs. Events is the default; Learning receives real bounded read models from the learner engine, with truthful empty/unsupported states. |
| Learner authority | Recording or completing an event never changes mastery or counts as assessment evidence. Grades/results use the existing learner contracts. |

Engineering defaults proposed for review: one-off events first; date-only events allowed; pending proposals expire after seven days or when their proposed date becomes unusable; date-only reminders default to 09:00 on the previous day; timed events default to one reminder 24 hours before. These defaults must be visible and editable, not disguised as details supplied by the student. Late-created events receive one immediate reminder if still upcoming rather than a burst of missed reminders. Users can disable reminders or choose a single delivery time/offset per event. Rescheduling can move an undelivered reminder; after delivery it cannot create another reminder for that event.

The stated request for an automatic addition authorizes ordinary academic event capture, not invented dates, secrets, third-party personal calendars or sensitive details. Reuse admission/provenance protections while keeping event-specific semantics independent.

## 2. What Progress currently contains

`frontend/src/pages/ProgressPage.tsx` currently renders only `WorkspacePlaceholder`. Its copy describes future strengths, explored concepts and areas for study; there is no live progress dashboard, event calendar, reminder inbox or Progress data-fetching integration.

The implemented learner engine exposes public context, study-recommendation, evidence/state and prediction services that could support a later learning-progress view. Its existence does not mean the Progress frontend is implemented. Older learner/LangGraph plan documents contain historical implementation claims and stale integration notes; executable code and current dependency metadata take precedence.

Use `/progress?tab=events` and `/progress?tab=learning`, with the existing sidebar Progress entry unchanged. Include the learner-backed Learning frontend and its authenticated read adapter in this delivery. Full historical mastery charts, generated assessments and grading remain separate capabilities unless the inspected learner contract actually supplies their data. Avoid presenting fabricated percentages, empty performance charts or scheduled events as measured learning progress.

## 3. Verified compatibility baseline

| Inspected component | Current behavior | Required integration |
| --- | --- | --- |
| `history_management` | Composed facade, evidence validator, owner-bound tools, memory SQL adapter and Settings UI | Add a separate events facade; share narrow contracts and infrastructure rather than importing memory lifecycle rules. |
| `langchain/history_orchestration.py` | Bounded serial tool loop; six calls/two writes; generic tool-error handling | Register event tools within the existing shared budget. Translate a graph suspension into a typed pending-action result, never an ordinary tool failure. |
| `chat/service.py` | 150-second generation deadline and 180-second lease | Never hold a chat HTTP request or turn lease while waiting for human input. Event workflow lifetime must be independent. |
| `chat_turn` and `TurnStatus` | Only RUNNING/SUCCEEDED/FAILED | Keep a chat answer completed while its event proposal awaits confirmation. No unplanned WAITING state or blocked subsequent chat turns. |
| Chat metadata/cache | Final assistant messages persist Library, H and M references; account-scoped cache and incremental sync | Add typed event references and pending-action IDs without a second transcript or stripping metadata during hydration/recovery. |
| Installed packages | `langchain-core 0.3.86`, `langchain-openai 0.3.35`; LangGraph and its PostgreSQL saver are absent | Dependency compatibility is an explicit Phase 0 gate. Select and pin a compatible graph/saver combination; do not assume latest examples work or silently upgrade the framework. |
| `student_profile` / `SendTurn` | No account timezone or trusted relative-date context | Add event preferences with an IANA timezone and pass a validated request timezone where needed. Never use execution-host timezone implicitly. |
| Database | Source Alembic head `20261008_0006`; shared owned metadata | Allocate the actual next revision at implementation time. Frozen migrations, owned composite FKs and isolated rehearsal remain required. |
| Notifications / scheduler | No in-app notification system exists; RAG has a dedicated ingestion worker | Build a reusable Notifications module and a lightweight event reminder worker. Do not run reminders inside RAG's heavy embedding/parser worker. |
| Frontend primitives | Accessible shared Toggle and semantic theme controls | Reuse these, native dialogs and bounded stores. No new theme, loading framework or calendar library without demonstrated need. |

No repository AGENTS.md was discovered in the inspected workspace. Recheck instructions, git state and dependency/migration heads before implementation; preserve existing work.

## 4. Architecture and reusable contracts

```text
Persistent chat -> existing bounded tool dispatcher
                   -> event_lookup -> EventsService -> EventsRepository
                   -> event_manage -> admission/date validation
                                     -> clear proposal: transactional save
                                     -> uncertain proposal: EventConfirmationGraph

Progress Events UI -> authenticated event/proposal APIs -> same EventsService
Reminder worker -> EventsService due candidate validation
                -> NotificationsService transactional producer API -> shared inbox
Other future producers -> same NotificationsService; no event-domain dependency
History-management facade -> memory service + events service + canonical history reader
```

Suggested layout, split further only for actual responsibilities:

```text
backend/app/history_management/events/
  contracts.py, schemas.py, service.py, factory.py
  admission.py, temporal.py, tools.py
  confirmation.py          # graph adapter; no domain reliance on graph internals
  reminders.py, worker.py  # event scheduling/eligibility only
backend/app/history_management/repositories/events/
  tables.py, postgres.py, reminders.py, proposals.py
backend/app/langchain/workflows/event_confirmation.py
backend/app/api/routes/events.py
backend/app/notifications/
  contracts.py, schemas.py, service.py, factory.py
  repositories/tables.py, repositories/postgres.py
backend/app/api/routes/notifications.py
backend/app/db/owner_transactions.py  # shared public transaction/locking boundary
frontend/src/components/events/
  EventsPanel.tsx, EventEditor.tsx, EventDetails.tsx
  EventProposalCard.tsx, EventPreferences.tsx
frontend/src/components/notifications/
  NotificationBell.tsx, NotificationInbox.tsx, NotificationPreferences.tsx
frontend/src/services/notifications.ts
frontend/src/types/notifications.ts
frontend/src/stores/notificationStore.ts
frontend/src/services/events.ts
frontend/src/types/events.ts
frontend/src/stores/eventStore.ts
```

Expose provider-independent create/list/detail/update/lifecycle/proposal/reminder contracts. Caller identity, clock, timezone policy, canonical evidence reader and repositories are injected. SQL imports stay under repositories/db paths. LangGraph is an adapter for confirmation, not the event database, date engine or public API. Other features can create events through this public facade without going through an LLM.

## 5. Canonical schema and transaction rules

| Table | Purpose |
| --- | --- |
| `hm_event` | Owner, UUID, title, bounded description, kind (quiz/exam/assignment/deadline/study/other), optional owned learning-context locator, status (scheduled/completed/cancelled), temporal fields, timezone, origin, revision, created/updated/completed timestamps. |
| `hm_event_evidence` | Minimum exact quote, source timestamp/message/chat snapshots, consent/admission policy version, deleted-source flag. Owned event FK; no restricting FK into physically deleted chat messages or turns. |
| `hm_event_revision` | Actor, revision and changed-field metadata. Avoid retaining every old personal title/description indefinitely. |
| `hm_event_preferences` | Separate automatic-event capture, reminders enabled, account timezone and one default reminder timing policy with expected revision. |
| `hm_event_proposal` | Bounded draft, uncertainty reasons, operation fingerprint, source scope, event target/expected revision if applicable, graph thread ID, proposal revision, expiry and decision state. |
| `hm_event_receipt` | Content-free idempotency and retry fencing for AI/manual writes and proposal decisions. No FK that blocks chat deletion. |
| `hm_event_suppression` | Event-domain claim/source/action hashes preventing dismissed/deleted evidence from silently recreating an event. Memory suppression is a different namespace. |
| `hm_event_reminder` | One lifetime delivery ledger per owned event (unique owner/event), current due instant/schedule version, pending/skipped/cancelled/delivered state and immutable delivered timestamp/receipt locator. Rescheduling never creates another ledger. |
| Notifications-owned tables | Generic inbox, content-free producer receipts, preferences and sync/change tables specified in section 17. No event-owned notification table. |
| `hm_event_sync` / `hm_event_change` | Owner revision and bounded ID/tombstone change log for loaded events and proposals. Expired cursor returns reset rather than inconsistent deltas. |
| LangGraph checkpoint tables | Minimal operational graph state in an isolated namespace; never canonical event/chat storage. Include every saver payload/write/blob table in cleanup policies. |

Date-only events use a local DATE plus IANA timezone. Timed events use aware UTC instants plus their original IANA timezone; optional end must follow start. Enforce exactly one temporal mode and valid status/revision/length/reminder bounds with database constraints. Unknown dates stay proposals, not arbitrary midnight timestamps. An uncompleted assignment/deadline can become overdue after its cutoff. An exam/quiz/study occurrence becomes past or in progress, not an overdue assignment. Neither passage of time nor reminder delivery implies completion.

All associated rows enforce owner relationships. Index owner/status/date and owner/reminder-due, proposal state/expiry, Notifications-owned unread/delivery indexes and each module's change revision. Use keyset pages with bounded filters and query deadlines. Do not make title alone unique: two quizzes with the same title on different dates can be legitimate.

Reuse the established owner serialization boundary for writes that race chat deletion/final publication; preserve a consistent lock order across API, graph and scheduler. Manual updates require expected revisions. Event changes, reminder rescheduling/cancellation and sync records commit together. Permanent deletion purges evidence, personal proposal/checkpoint copies and notification snapshots; content-free suppression/receipts must not resurrect the record.

Saved events survive chat deletion. Unconfirmed proposals originating only from that chat are cancelled and their personal graph payloads cleaned. Event completion/cancellation retains the event but stops future reminders. Account deletion must eventually purge all event and graph resources as well.

## 6. Admission, dates and duplication

- Capture only durable actionable academic events supported by current/visible/retrieved owned user evidence. “I have a quiz…” differs from a hypothetical quiz, someone else's exam or an assistant's suggestion.
- Event extraction is a tool proposal during ordinary generation. Do not run an additional extraction model on every turn or rescan all chats. A compound statement may produce a preference memory and an event, each from its own supported span; never duplicate the deadline itself as a high-level memory.
- Validate exact evidence and deterministic bounds first. Use one bounded structured admission/date interpretation call when necessary; cache by evidence/proposal/policy. Unavailable verification saves nothing and cannot claim success.
- Resolve relative dates using the source-message timestamp and the student's validated IANA timezone. Resuming next week must not reinterpret “next Monday” relative to resume time. Unknown timezone goes to confirmation.
- Preserve original date wording. “Next Monday,” “this Friday,” “tomorrow night,” missing year, ambiguous numeric dates and vague times need an explicit deterministic policy or a clarification. Show the exact resolved date before acceptance when multiple reasonable readings exist. Do not infer an exam time from a date-only statement.
- Detect DST folds/gaps and unsupported zones using the timezone database. Return possible choices; do not silently choose a UTC offset. Date-only classification/reminder boundaries follow the event timezone even when the device travels. Missing historical timezone evidence must not be reconstructed from today's device zone without confirmation.
- Deduplicate exact retry fingerprints transactionally. Use bounded matching by kind/context/title tokens and date; fuzzy title alone cannot collapse unrelated events. Uncertain duplicates or rescheduling require review of both existing and proposed versions.
- Keep sensitive details minimal and consent-gated. Scheduling requests are not authorization to copy a whole personal message into descriptions or checkpoints.
- Separate event auto-capture checks occur both before model validation and at the final transaction. Disabling it blocks new AI event writes and proposals, including in-flight attempts. Existing pending proposals remain visible; explicitly approving one is a manual user action and remains allowed. Manual creation/edits and event lookup are independent of this switch.
- Past events may be manually recorded as history, but cannot create already missed reminder storms. Distinguish an exam occurrence from an assignment submission deadline.

## 7. Event tools and bounded AI access

`event_lookup`: optional keywords, kind/status, aware date range and bounded limit (default five, max ten). Default scope is upcoming owned events with an explicit short horizon; a historical search must request a bounded period. Return exact date/time/timezone, status, origin, current revision and reference tokens. Never dump all events or inject the entire calendar into every prompt.

`event_manage`: propose_create, propose_update or propose_status. Arguments include supported event fields, exact source quote/visible message ID, target ID and expected revision for updates. Owner and confirmation-workflow identity remain server-bound. Clear first-party statements can save automatically. Ambiguous intent/temporal details and changes that conflict with manually controlled events return `awaiting_confirmation` with a proposal ID. No autonomous hard-delete tool.

Manual deletion, reminder configuration and proposal decisions use authenticated APIs. AI results distinguish saved, already_known, awaiting_confirmation, rejected, expired and unavailable. “Added your quiz” is valid only after a committed event. A dismissed proposal never counts as saved.

All event tools share the current cumulative chat budgets and write counter; do not add a second unrestricted six-call allowance. Include event schemas in initial context accounting and keep paired tool results. Repeated lookups reuse bounded turn-local results. Register event prompt/admission sources and versions separately. Unsupported providers keep ordinary chat functional and cannot pretend to add events.

## 8. LangGraph confirmation without blocking chat

Use a narrow durable `EventConfirmationGraph`, not an immediate rewrite of the whole tutoring/chat graph. The graph receives a server-created proposal ID and minimal typed state, validates readiness, interrupts for a decision when needed, validates accepted edits and commits through EventsService.

The ordinary chat tool receives a typed suspension result and finishes its assistant answer with a proposal card. No live Python task waits for the student, no lease is extended overnight, and no new chat-turn state is necessary. A user can continue chatting while the independent event workflow awaits a decision.

The card shows title/kind, exact local date/time/timezone, uncertainty reason, reminder defaults and **Add event**, **Edit details**, **Dismiss**. Incomplete required fields must be filled before acceptance. The same pending proposal appears in Progress after refresh/login/restart.

An authenticated decision endpoint verifies owner/proposal revision/expiry and maps the proposal to its server-owned graph thread. It resumes with `Command(resume=...)` using validated accepted edits; the client/model cannot supply arbitrary thread IDs or graph commands. Check current target/proposal revisions and evidence lifecycle again before committing. Automatic-capture permission gates autonomous writes; an explicit authenticated approval is a manual save and may proceed with capture disabled. Reminder delivery still obeys its separate preference. Concurrent decisions are owner-locked and idempotent; approve-vs-dismiss has one winner.

Treat graph checkpointing and event mutations as separate persistence transactions. A durable proposal/receipt is the reconciliation authority: if event commit succeeds but checkpoint advancement fails, replay finds the receipt and advances without a second event or reminder. If proposal creation succeeds before a graph checkpoint is available, retry initializes the same workflow from the durable proposal. Typed processing claims/leases expire and are recoverable; no permanent “processing” flag. API responses hydrate current proposal/event state, not stale checkpoint copies.

Keep interrupt nodes free of non-idempotent side effects before suspension; resumed nodes may replay. Do not swallow graph interrupts in the existing dispatcher's generic `except Exception`. Prefer interpreting the selected version's graph invocation result through the workflow adapter, returning a normal tool payload to chat. Validate resume bodies in Mentra's Pydantic schemas rather than assuming newer LangGraph typed-interrupt APIs exist.

Checkpoint content must be minimal, owned, retention-bounded and purged after terminal workflows once reconciliation receipts are durable. Rejection/deletion/chat cleanup must cover checkpoint state, pending writes and blobs, not only the proposal row. If the selected saver cannot provide required owner-safe deletion, implementation must supply a tested adapter or choose a compatible saver; this is a release gate.

Official guidance establishes durable checkpoint/thread identity, resume and node replay semantics: [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) and [persistence](https://docs.langchain.com/oss/python/langgraph/persistence). Current documentation includes APIs newer than this checkout; dependency/API rehearsal precedes implementation.

## 9. Single-reminder delivery through Notifications

Create a lightweight `events-worker` Compose process using the backend image and database only. It must not initialize embedding models, Qdrant, document engines or the chat provider. Start after migration/readiness; support clean shutdown, bounded batches, transient retry/backoff and a worker heartbeat/readiness indicator. Generic notification reads and writes do not depend on this worker: it is an Events producer adapter, not the Notifications module itself.

**Hard rule: at most one reminder per event lifetime.** Create one unique owned event reminder ledger. Before delivery, edits can move its due instant or cancel it. After delivery, rescheduling, reopening, rule changes, worker restarts, read/dismiss, archival and retention cannot rearm it. The editor displays “Reminder already sent” and disables scheduling another. Creating a deliberately new event yields a new event identity; silently cloning one to evade this rule is prohibited.

Read indexed candidate IDs without holding row locks, then acquire the shared owner write boundary and recheck the event, ledger version, due instant, both preferences and lifetime receipt in a short transaction. Call the public Notifications transactional producer API with `producer=events` and immutable key `reminder:<event UUID>`; it creates/reuses one delivery receipt/inbox row. Mark the event ledger delivered and append each module's changes in that same transaction. Either all commit or none do. Multiple workers and lost responses cannot create duplicate inbox entries. Do not claim exactly-once browser display.

Completion, cancellation or deletion prevents undelivered reminders; rescheduling replaces the pending time, never adds a rule. A disabled event/global preference blocks delivery. Re-enable permits future due times only; times missed during disable are skipped. A new event whose configured reminder time has passed may receive one immediate reminder only if still upcoming and the configured preferences permit it; show this in save/approval outcomes. During outage recovery, a previously eligible undelivered reminder may deliver once only while the event remains upcoming. Past events produce no catch-up notification. Section 14.4 defines date-only cutoff and disable-window rules.

Notifications owns the shared header bell, paged inbox, unread summary, read/dismiss, independent global preference and sync. Progress's Reminders view filters this same inbox to the Events producer; it is not a second inbox or store. Many distinct events may legitimately become due together: persist each one's single reminder in bounded worker batches, present one aggregate badge and a paged quiet inbox. No per-item toast, sound, popup, automatic panel opening or badge animation storm. Group display without dropping or combining distinct delivery receipts.

No Socket.IO is required initially. One Notifications coordinator fetches a small summary after authenticated bootstrap, pages on demand, reconciles focus/reconnect and polls bounded deltas about once per minute only while authenticated/visible/online. Events polling excludes notification state. Delivery target is roughly 15–30 seconds under normal load, configurable and not guaranteed during outages. Stop owner-scoped polling and clear personal state on logout. Durable inbox delivery while the browser is closed appears on return; OS/browser push and email remain future adapters.

## 10. Progress frontend and API contracts

Progress Events uses a focused agenda grouped by local date, with upcoming, overdue deadlines, past occurrences, completed/cancelled and needs-confirmation filters; bounded date/search/type filters; cursor pagination; and an Add event button. A full draggable calendar is optional later. Show exact date-only versus timed semantics, timezone and event kind without invented precision.

Manual forms expose title, kind, optional subject/context/description, date-only or timed fields, timezone and one visible reminder timing. Reopening/completing/cancelling/deleting have clear consequences. Show source evidence, deleted-chat labels, AI/manual origin, stale revision recovery and pending proposal decisions. Preserve drafts across tab changes; query-aware tabs support keyboard/deep-link/back/refresh behavior. Reuse the shared Toggle for auto-capture and reminders, independently of memory settings.

Chat adds allowlisted `E1` event references and typed pending-action IDs. H/M/S behavior is unchanged. Event references open current owned details; cards refresh live proposal state when opened and after decisions. A completed decision updates a bounded live action projection; persisted assistant metadata keeps only its proposal/event IDs. Historical assistant text is immutable. Reload those projections rather than rewriting the transcript. No repeated LLM call is required merely to display “Event added.” Model continuation after confirmation is a future choice, not necessary to save an event correctly.

| Authenticated endpoint | Contract |
| --- | --- |
| `GET/POST /events` | Bounded date/status/type/keyword list or manual idempotent create |
| `GET/PATCH/DELETE /events/{id}` | Owned detail, expected-revision edit/lifecycle or permanent purge |
| `GET/PATCH /events/preferences` | Separate capture/reminder defaults/timezone, expected revision |
| `GET /events/proposals` | Bounded owned pending queue |
| `GET /events/proposals/{id}` | Current draft/reasons/revision, never arbitrary checkpoint access |
| `POST /events/proposals/{id}/decision` | Approve with edits or dismiss; expected revision and client decision UUID |
| `GET /notifications` and `/notifications/summary` | Generic bounded inbox and unread summary; optional allowlisted producer filter |
| `PATCH /notifications/{id}` | Notifications-owned read/dismiss API using revision/receipt contract |
| `GET /events/sync` | Bounded owner revision deltas; explicit reset beyond retained change floor |

Register fixed paths before UUID routes. All routes inherit onboarded identity and existing cookie trusted-origin checks. Never accept owner IDs from models/bodies. Add typed responses and stable codes for revision/decision conflicts, invalid/ambiguous date, expired proposal, deleted source, disabled automation, capacity and unavailable verification.

Use a bounded account-scoped in-memory event store and separate Notifications store, not the chat transcript store. Abort/fence stale queries and merge targeted revisioned mutations/deltas. Invalidate affected filtered pages/cursors when sort membership changes. BroadcastChannel distributes owner-scoped invalidation, with focus reconciliation. No new personal-event IndexedDB payload cache without an offline requirement. Future reminder notifications do not justify downloading all events at login.

## 11. Implementation phases and acceptance gates

### Phase 0 — Policy, dependencies and contracts

- [x] Inspect Progress, chat deadlines/states/tool loop, memory boundaries, profile/timezone fields, Compose and installed dependencies.
- [x] Record independent default-on event capture, saved-event retention and in-app reminders.
- [x] Record the user's strict one-reminder-per-event requirement and standalone reusable Notifications module in this delivery.
- [ ] Review temporal/reminder defaults, proposal retention and first-version recurrence scope.
- [ ] Recheck migration head/instructions; resolve and pin compatible LangGraph/saver versions in an isolated dependency rehearsal. Prove existing LangChain 0.3/provider behavior remains intact.
- [ ] Freeze event/proposal/timezone/tool/API contracts and standalone Notifications producer/inbox/preferences/sync contracts and saver cleanup capabilities.

**Exit:** Reviewable contracts and demonstrated dependency compatibility, with no hidden chat-state rewrite.

### Phase 1 — Domain and canonical persistence

- [x] Add provider-independent event contracts, composed facade and repository boundaries.
- [x] Implement owned event/preferences/evidence/revision/receipt/suppression/change tables and frozen migration.
- [x] Implement transactional manual CRUD/lifecycle, revision conflicts, idempotency, date-mode constraints and context ownership.
- [x] Rehearse upgrade/downgrade/no-drift against existing memory/chat/profile/RAG records.

**Exit:** Independently persistent user-managed events with no memory-table mixing.

### Phase 2 — Temporal admission and event tools

- [ ] Implement evidence/intent/consent/date/timezone checks, original-message date anchoring and bounded duplicate resolution.
- [ ] Add separate event tools and registered prompts within the existing shared execution budgets.
- [ ] Check independent auto-capture preferences before verification and inside writes; preserve manual saves/lookup.
- [ ] Keep clearly timed academic events out of high-level memory admission; no retrospective mass migration without a separate reviewed conversion policy.

**Exit:** Clear statements save once; uncertain or conflicting details become explicit proposals with no false success claims.

### Phase 3 — Durable human confirmation

- [ ] Implement narrow graph/checkpointer adapter, proposal lifecycle, typed interrupts and authenticated resume.
- [ ] Separate event workflow lifetime from chat HTTP deadline/turn lease; complete chat with action metadata.
- [ ] Add approve/edit/dismiss receipts, race fences, expiry and graph/event reconciliation after crash/restart.
- [ ] Prove owner-safe checkpoint cleanup across terminal decisions, deletion, source-chat cleanup and abandoned proposals.

**Exit:** A paused proposal survives refresh/restart, resumes once and cannot duplicate or bypass user decisions.

### Phase 4A — Standalone Notifications module

- [ ] Implement provider-independent Notifications facade, opaque shared unit-of-work integration and owner-bound producer API; no import of Events/memory/learner repositories.
- [ ] Add generic inbox, immutable delivery receipt, global preference and sync/change tables with frozen migrations, indexes and retention semantics.
- [ ] Implement authenticated paged inbox/summary/read/dismiss/preferences/sync APIs and explicit error/revision contracts.
- [ ] Verify retries, concurrent producer calls, owner isolation, filtered summaries, retained dedupe after inbox purge and transactional rollback with a second synthetic producer.

**Exit:** Independently reusable Notifications backend, usable by another feature without importing Events or changing its tables.

### Phase 4B — Single-event reminder producer and worker

- [ ] Add one unique lifetime reminder ledger per event and immutable producer key; enforce no rearm after delivery at service and database boundaries.
- [ ] Implement atomic rescheduling/cancellation, disabled-window fencing, delivery through Notifications and both modules' sync changes in one transaction.
- [ ] Implement bounded lightweight worker, owner-first locks, retry/restart catch-up, multiple-worker tests and worker readiness/shutdown/Compose configuration.
- [ ] Verify delivered-event edits/reopen/read/dismiss/retention cannot cause a second reminder; no per-item toast or notification flood during batches.

**Exit:** Each event creates at most one durable reminder across its entire lifetime; no stale schedule or disabled preference bypasses delivery.

### Phase 5 — REST, complete Progress frontend and chat UI

- [ ] Expose typed authenticated events/preferences/proposals/sync endpoints and separate Notifications endpoints.
- [ ] Build Progress Events/Learning tabs, bounded agenda/detail/editor/manual lifecycle, real learner-backed overview/concept views and independent shared toggles.
- [ ] Implement the frontend component/API/state matrix in section 13, including editor preservation, timezone validation, operation recovery and every listed empty/error/terminal state.
- [ ] Build chat proposal review and E references; hydrate action state safely through existing persistence.
- [ ] Add compact shared Notifications header inbox/badge and Settings tab, on-demand pages, visibility-aware delta polling and owner-scoped reconciliation.
- [ ] Verify accessibility, keyboard focus, draft retention, mobile containment and semantic Light/Dark/System styling.

**Exit:** Users can review uncertain additions and fully manage events/reminders from Progress without breaking memory or existing chat/RAG UI.

### Phase 6 — Lifecycle, adversarial and performance verification

- [ ] Test explicit/hypothetical/third-party/sensitive statements, uncertainty, duplicate titles, rescheduling, corrections and input injection.
- [ ] Test relative dates across source/resume midnight, missing timezone/year/time, ambiguous numeric/weekday dates, DST folds/gaps, date-only events and device/account timezone changes.
- [ ] Test independent toggles, disable-during-verification, manual acceptance with capture disabled, source-chat deletion retention/cancellation, suppression and permanent purge including saver blobs.
- [ ] Test concurrent decisions, stale target/proposal revisions, dropped HTTP responses and crashes between graph/event/notification transactions.
- [ ] Test multiple reminder workers, complete/cancel/delete-vs-delivery, single-reminder late-start recovery, offline browser, unread/read/dismiss and no cross-account disclosure.
- [ ] Measure query/index/batch counts, graph payload growth, tool/token budgets, cache bounds and large agenda/inbox latency on synthetic fixtures.
- [ ] Run existing auth/profile/chat/RAG/memory/learner/architecture/theme regressions and production-built browser tests; record actual results and provider-quality limits.
- [ ] Verify Learning owner/context isolation, unknown-vs-zero values, distinct confidence fields, no mastery writes from event actions, bounded queries and genuine evidence-only activity.

**Exit:** All requested end-to-end workflows work under retry/restart/concurrency; semantics and operational limits are explicit.

### Phase 7 — Docker runtime and handoff

- [ ] Rebuild backend/frontend images and verify the new events-worker using the backend image.
- [ ] Rehearse isolated migrations, clear auto-add, actual graph interruption/resume after restart, manual Progress CRUD, learner-backed Learning reads and reminder delivery while the browser is closed.
- [ ] Verify final image browser UI, owner isolation, chat-deletion retention, content purge, worker recovery and cleanup.
- [ ] Document exact dependency pins, configuration, timezone/reminder policies, maintenance/checkpoint cleanup and test artifacts.
- [ ] Report actual application migration/container deployment separately from builds and isolated verification.

**Exit:** Reproducible end-to-end verified images and worker, with all evidence recorded.

## 12. Tracking and definition of done

| Phase | Status | Evidence / gaps |
| --- | --- | --- |
| 0 | In progress; dependency gate unresolved | Python 3.12 disposable-container rehearsal preserved core 0.3.86/provider 0.3.35. Compatible graph 0.6.11 candidates lack strict serializer controls; patched graph 1.0.10 conflicts with the pinned stack. No production dependencies changed. |
| 1 | Backend foundation implemented and verified in isolation | Frozen `20261009_0007` plus additive ledger retention migration `20261009_0008`; public owner transaction boundary; event/evidence/audit/preferences/receipt/suppression/reminder/sync tables; authenticated CRUD/lifecycle/preview/read APIs. Re-pass: 40 focused local tests passed; image evidence in 12.2. Full release gates remain open. |
| 2 | Not started | Implementation acceptance evidence must be recorded before completion. |
| 3 | Not started | Implementation acceptance evidence must be recorded before completion. |
| 4A | Not started | Reusable Notifications contracts, migrations and isolated producer tests required. |
| 4B | Not started | Lifetime one-reminder invariant and transactional worker tests required. |
| 5 | Not started | Implementation acceptance evidence must be recorded before completion. |
| 6 | Not started | Implementation acceptance evidence must be recorded before completion. |
| 7 | Not started | Implementation acceptance evidence must be recorded before completion. |

Completion requires separate event tools/tables; independent preference enforcement; supported auto-add and truthful proposal outcomes; durable confirmation with owner-safe cleanup; manual Progress management and real learner-backed Learning UI; standalone reusable Notifications backend/UI and at-most-one lifetime reminder per event; source-deletion retention and permanent purge; bounded context/cache/queries; migration and failure/race tests; final rebuilt-image/worker verification. Defining tool schemas or drawing a calendar alone is not completion.

**Review focus:** The dedicated events domain, two Progress tabs, independent default-on capture, saved-event retention and in-app reminders are agreed. One reminder per event and a standalone Notifications module are also required. Numerical timing/retention/capacity defaults below are documented engineering proposals. The user authorized starting implementation on 2026-10-09; the first backend increment uses the documented one-off/timing/capacity defaults. The remaining phases retain their acceptance gates.


### 12.1 First implementation increment (2026-10-09)

- Files: `backend/app/history_management/events/`, `backend/app/history_management/repositories/events/`, `backend/app/db/owner_transactions.py`, `backend/app/api/routes/events.py`, factory/router/main/chat-deletion composition, and frozen migration `backend/alembic/versions/20261009_0007_events.py`. Public domain and SQL persistence remain separate. Optional context ownership uses public learner reads plus composite FKs; completing an event never submits learner evidence.
- Related bug fixed: migration advisory-lock acquisition retained a waiting transaction snapshot, deadlocking concurrent index builds during simultaneous isolated schema upgrades. `backend/app/db/migrate.py` now uses committed nonblocking lock probes and a bounded wait; competing schema and timeout-cleanup tests are included.
- Local command: set `PYTHONPATH=backend` and explicit disposable `TEST_DATABASE_URL`, then `.venv/Scripts/python.exe -m unittest backend.tests.test_events backend.tests.test_events_api backend.tests.test_migration_concurrency -v`. **23 passed**, including a run concurrent with the Docker suite. Logs: `.events-tests.log` and `.events-concurrent-local-tests.log`.
- Docker build: `docker build -t mentra-events-foundation-verify -f backend/Dockerfile backend` passed. This is an isolated verification image; production dependencies, images/containers and application database were not changed. Build evidence: `.events-image-build.log`.
- Docker regression: **145 passed** in the final rebuilt Python 3.12 image (70.919 seconds), while local focused tests also exercised concurrent isolated migrations. Command uses the rebuilt image's Python 3.12 and application code, read-only `backend/tests` and `backend/testing` mounts, and an explicit disposable database: `python -m unittest tests.test_events tests.test_events_api tests.test_migration_concurrency tests.test_history_management tests.test_persistent_chat tests.auth.test_auth tests.student_profile.test_profile tests.learner.test_persistence tests.learner.test_integrations -v`. Log: `.events-docker-tests.log`.
- Migration evidence: isolated fresh upgrade, downgrade to `20261008_0006`, re-upgrade, zero metadata drift and unchanged snapshots for all non-event tables. No application migration was applied. Database-level malformed reminder/date/ownership checks and immutable delivery/identity fences were verified.
- Phase 0 evidence: candidate graph/saver resolution/install rehearsed in disposable backend containers. `langgraph==0.6.11`/checkpoint `3.0.1`/saver `3.0.4` preserves existing LangChain but lacks strict msgpack serializer controls; patched `langgraph==1.0.10`/saver `3.0.4` cannot resolve with core `0.3.86`/provider `0.3.35`. Production requirements remain unchanged. `backend/testing/event_dependencies.py` reproduces the hardening gate. Durable graph/resume/cleanup has **not** passed. See `docs/events.md` for upstream metadata/advisory links and the next decision.
- Remaining: phases 2, 3, 4A, 4B and 5 are unimplemented; broader adversarial/performance/browser/account-purge and actual deployed runtime gates in phases 6/7 remain open. Reminder ledgers do not yet deliver notifications. Progress still uses its existing placeholder. This increment does not claim full Events rollout completion.

### 12.2 Implementation verification re-pass (2026-10-09)

- Reproduced and fixed reminder timing changes on unrelated edits, missed reminders rearmed on reopen, equivalent UTC-offset rejection, operation recovery after context loss, context-deletion races, unbounded owner-write waits, upcoming summary mismatches, extreme-date range failures, DST-fold validation/preview errors and historical civil-day second precision. Host timezone aliases are rejected; valid past dates do not resolve unused historical default reminders. Bulk preference/source changes batch queries and page/sync projections share one clock instant.
- Added frozen `20261009_0008_event_reminder_retention.py`, leaving 0007 unchanged. Direct ledger deletion is forbidden while its event exists; event deletion still cascades. Downgrade/re-upgrade preserves ledger rows and the original delivered-update fence. Existing migration tests also verify non-event snapshots, metadata drift and concurrent upgrades.
- Local focused command from 12.1: **40 passed** in 7.216 seconds. Logs include `.events-repass-tests.log`; `.events-repass-before.log` and `.events-repass-ledger-before.log` retain reproduced failures before fixes.
- Rebuilt actual Python 3.12 backend image `mentra-events-foundation-verify`; build log `.events-repass-build.log`. **All 333 backend tests passed** in 138.216 seconds: `python -m unittest discover -s tests -v`, with read-only test/testing mounts and an explicit disposable PostgreSQL database. Final log `.events-repass-docker-tests.log`.
- Frontend `npm.cmd run check:theme` passed; `npm.cmd run build` passed (TypeScript and Vite, 17.51 seconds). The build required execution outside the restricted sandbox because esbuild could not spawn there. Log `.events-repass-frontend-build.log`. Frontend source was unchanged; these checks do not claim browser acceptance for the unimplemented UI.
- Dedicated PostgreSQL 17 disposable container `mentra-events-repass-test-20261009`, temporary owned schemas only. No application database migration, deployment or dependency change. Dependency gate and all remaining rollout phases listed in 12.1 remain open.

## 13. Complete frontend implementation specification

This section is required delivery scope, not a UI sketch. The current `ProgressPage` placeholder is replaced. Existing `AppLayout`, auth/onboarding guards, profile/memory Settings, chat recovery, Sidebar and theme behavior must continue to work.

### 13.1 Information architecture and navigation

- Keep one sidebar **Progress** link. Default `/progress` opens Events. `/progress?tab=learning` opens Learning; existing query parameters are preserved when switching tabs, while incompatible item selections are cleared deliberately.
- Support deep links for `event=<uuid>`, `proposal=<uuid>` and `view=reminders` within Events; `context=<owned-id>` and `concept=<canonical-id>` within Learning. Validate combinations, malformed IDs and deleted/unowned targets; never expose another owner's existence. Unknown tabs fall back to Events.
- Main tabs use tablist/tab/tabpanel relationships, roving tabindex, arrows/Home/End and predictable focus. Refresh/back/forward preserve selection. A deep-linked item outside the current page loads its owned detail directly; its existence does not require downloading the whole agenda.
- Lazy-load Events, Learning, editor/detail/reference dialogs and reminder inbox. Do not fetch all event or learner data at login. Keep visited panels mounted-hidden or retain their draft state outside them; pause their data work when inactive. Page-level draft preservation must not create unbounded mounted rows/dialogs.
- In Events, use Upcoming as the default view, with Overdue deadlines, Past, Completed, Cancelled, Needs confirmation and Reminders as bounded views. Views have meaningful counts only when returned by a bounded owner summary; do not infer total counts from the current page.
- A selected context may narrow both views, but filters do not mutate the active learner context. No unsolicited switch of the student's current study subject.

### 13.2 Events visual layout and actions

Use the existing restrained layout: clear title and tabs, a compact controls row, date-grouped agenda and contextual detail/editor. Avoid a dense dashboard grid. Header actions **Add event** and **Review proposals** remain one line, with shrink protection; stack rows on small screens. Event type color, if used, marks a small icon/dot rather than theming the entire row.

Rows display title, type/context, full local date, date-only or time/range, timezone, lifecycle state and single-reminder summary. Group rows by their event-local date; when multiple zones are present, show the zone on every row rather than falsely grouping all by device-local day. "Today"/"Tomorrow" are relative to the stated zone, with full dates accessible. No midnight shifts from `new Date('YYYY-MM-DD')`.

Provide bounded debounced search (300 characters), type/status/context and date-range filters, a clear/reset action and keyset Load more. Empty agenda, empty filter results, pending-only, past-only and unavailable data have different explanations. An empty result is never used to hide a failed fetch.

Details show current owned fields, source evidence and deleted-chat labels, single-reminder delivery state and lifecycle actions. An event reference from chat/reminders opens the same shared detail surface. Expose Edit, Mark complete, Cancel, Reopen and Delete only when legal for the current state. Destructive deletion uses a native confirmation dialog naming the current event and explaining that reminders stop, while original chat messages remain. Cancellation is reversible and distinct from permanent deletion.

After mutations, merge only the changed revisioned record and affected summaries/actions; invalidate query membership/cursors when dates/status/order change. Preserve scroll sensibly; return focus to the invoking control or nearest surviving row. Do not clear a draft merely because a fetch or tab switch occurred.

### 13.3 Event editor and timezone UX

Use one shared editor for manual creation, event edits and proposal corrections. Required fields: title (1–200), type and a concrete temporal mode. Description is optional (up to 2000); context is optional and must be owned. Dates use canonical ISO strings in transport. Human display uses `Intl.DateTimeFormat` with explicit timezone and locale; text date examples include month names to avoid locale ambiguity.

Offer **Date only** and **Date & time** controls. A date-only assignment is due through that local calendar day; show "Time not specified" for an occurrence. Timed inputs collect local date/time and IANA zone; the server resolves to UTC and returns the normalized preview. Do not send a timezone-free datetime as if it were UTC. Ambiguous/gap times render inline server-provided choices/errors, preserving inputs. End time is optional; v1 date-only events cover one day and timed intervals must end after start.

Timezone defaults come from saved event preferences, otherwise a validated browser suggestion visibly shown to the user. Unsupported/missing suggestion prompts selection. Browser timezone changes never silently overwrite account preferences or existing events. Initialize defaults once, and freeze the current draft's timezone rather than refreshing it while the user types.

Provide one per-event reminder with a shared Toggle and one timing/offset selector, including **No reminder**. Show its computed delivery instant and explain a late-creation immediate reminder before save/approval. If already delivered, show “Reminder already sent” with no rearm control. Event reminders off and global notifications off are separately labelled; an undelivered reminder cannot bypass either preference.

Disable conflicting inputs/actions during a submitted mutation while keeping focus usable. Inline errors link to their fields, summarize ambiguous dates and preserve content. Changed create payloads get a new request UUID; identical retries reuse the same UUID. Revision conflicts show the latest saved version next to the draft and require another explicit save after review. Deleted targets offer "Create as a new event" as a deliberate manual action; never recreate automatically.

Dirty cross-tab switches retain the draft; closing the editor or navigating away asks to discard unsaved changes. Use the installed React Router version's supported routing mechanism; do not assume `useBlocker` works in the current declarative router. If no supported blocker is available, keep a retained account-scoped draft and explicit save/discard controls rather than broken navigation interception. Logout clears drafts without persisting personal data offline.

### 13.4 Event preferences and shared Notifications UI

Event preferences live in an expandable Events controls area and use the shared `Toggle`: **Let Mentra add events** and **Event reminders**. Display timezone and the one default reminder timing there. Settings gains a dedicated **Notifications** tab with a separate **In-app notifications** global switch, shared by future producers. Memory controls remain independent. Both surfaces use their module's authoritative store; do not duplicate forms/caches for the same preference. Explain when the global switch overrides event reminders.

Explain that capture-off blocks AI writes while preserving events, lookup, manual creation and explicit proposal approval. Explain that reminder-off stops future delivery while keeping saved events and delivered inbox entries. Persist server revisions; roll back failed optimistic changes; reload only genuine revision conflicts. Quota/validation/duplicate errors stay visible rather than being replaced by a generic "another session changed" notice.

Add a compact, labelled bell button on the right of `AppLayout`'s header with an unread badge (cap visual text at 99+). The Notifications-owned inbox is a shared dialog/panel, keyboard-dismissible with focus restoration, accessible name, scroll containment and mobile width/viewport bounds. It shows a bounded page of unread/read notifications, Read/Dismiss actions, an Events filter and links to Progress and Notifications settings. Progress Reminders embeds the same component with the producer filter. No hover-only interaction or OS notification permission request.

Opening an event from a notification records the explicit read action idempotently. Merely rendering a notification does not mark it read. Badges never increment optimistically from multiple worker/browser copies. A read/dismiss in another tab reconciles. If a record was rescheduled, show the current event date with "Schedule changed since this reminder"; if deleted, show unavailable without a retained personal title.

### 13.5 Chat proposal cards and references

Assistant metadata includes bounded event reference IDs/revisions and proposal IDs, not copied sensitive form drafts. Render cards only for owned server-returned IDs; plain user text, code fences and unknown markers cannot create actionable cards. E/H/M/S citation namespaces are allowlisted separately.

Cards load live proposal status in a batch per visible message window, rather than one request per chat row. Limit a card list to the accepted per-turn write budget; collapse historical terminal cards into concise outcomes. Do not download the entire proposal queue on every chat render.

Card states: Loading; Needs review; Missing details; Saving; Added; Dismissed; Expired; Source deleted; Target changed; Unavailable. Pending is never labelled Saved. Review uses the same editor and displays exact proposed fields, affected existing event, timezone and reminder preview. Add/Approve requires complete validated details; Dismiss asks no needless second confirmation. Native dialog Escape cancels the dialog, not the proposal; Dismiss is a separate explicit action.

A lost approval response recovers via the decision receipt/current proposal endpoint before offering a new save. Saving in Progress updates cards in chat and vice versa through the shared projection store/deltas. Restart/refresh restores outcome; acceptance does not rerun the old chat prompt or append a fake assistant message.

If the original assistant generation fails after an event/proposal commits, retain it visibly in Progress and offer a safe link to review saved actions. Model failure cannot delete a committed event or silently hide its proposal. If a referenced event changes, final-publication fences prevent stale date assertions; already delivered historical text remains historical, while the viewer labels current changes.

### 13.6 Learning tab: real learner module integration

The learner module is not owned by Events. Add an authenticated `ProgressReadService` that consumes `LearnerService` public methods. Event services must not query learner SQL or write state. Existing methods include `get_context_summaries`, `get_active_contexts`, `get_concept_states`, `get_relevant_context`, `get_study_recommendations` and `get_verification_candidates` in `learner/services.py` and `learner/engine.py`.

Existing context summaries and `explain_state` are not a paginated dashboard API. In particular, `explain_state` returns internal audit details and collects accepted evidence IDs; do not expose it wholesale or pretend it is a historical mastery series. Introduce bounded public progress-context/concept/activity read contracts inside the learner module with owned repository adapters, then use those contracts in the Progress HTTP adapter. Do not slice an unbounded SQL result in frontend code and call it pagination.

| UI feature | Delivered data/behavior | Truthfulness boundary |
| --- | --- | --- |
| Context picker | Owned, bounded context pages; active/related/archive status | Filtering does not activate a context or count as practice. Archived scopes are clearly labelled and read-only. |
| Concept list | Current concept name/status, mastery estimate and support, evidence recency, separate estimate/retention confidence | Unknown is not zero. No invented overall "learning percentage" from an arbitrary top-K subset. |
| Strengths / practice priorities | Bounded supported concepts and returned study/verification recommendations with reasons | Low evidence is "needs evidence/verification," not "weak student." Ranking is a heuristic, not a calibrated prediction. |
| Concept detail | Owned state, misconception/verification flags, difficulty and uncertainty information through typed public reads | Separate mastery, estimate confidence and retention confidence. Predictions, if shown, identify target difficulty and unsupported estimates. |
| Recent learning activity | Bounded, redacted real accepted evidence/activity records with occurrence dates and source availability | Event completion/reminder delivery is not learner evidence. Self-report/calibration estimates are labelled separately. |
| Study action | Navigate to chat with validated concept/context selection and a visible starter prompt | Do not send a message automatically or claim a nonexistent assessment workflow ran. |

No-data view explains what can supply real evidence and links to existing chat/Library/Settings calibration paths that actually exist. No fake chart, mock achievement streak or empty numerical summary. A bounded activity timeline can ship now; a mastery trend chart requires genuine timestamped state snapshots/versioned semantics and is deferred until such a contract is implemented and verified.

Learning fetches only on first visit/filter change/detail expansion or explicit freshness reconciliation. Reuse owner cancellation, bounded caches and error handling; no LLM calls to summarize every page visit. Show generated/as-of timestamps and Refresh; do not invent an aggregate revision absent from the learner service. If a composite read has no single snapshot, mark its sections with their as-of times instead of claiming global transaction consistency.

### 13.7 Frontend files, services and ownership

| File/component | Responsibility |
| --- | --- |
| `pages/ProgressPage.tsx` | Query-driven tabs, layout, visited-panel/draft lifecycle; replace the placeholder |
| `components/events/EventsPanel.tsx`, `EventAgenda.tsx`, `EventFilters.tsx` | Bounded agenda, date grouping, filter/page interactions |
| `EventEditor.tsx`, `EventDetails.tsx`, `EventConfirmation.tsx` | Shared forms, normalized temporal preview, owned detail and destructive confirmation |
| `EventProposalCard.tsx`, `EventProposalReview.tsx` | Server-bound chat/Progress human review and explicit decisions |
| `components/events/EventPreferences.tsx` | Event-only capture/timezone/single-reminder defaults |
| `components/notifications/NotificationBell.tsx`, `NotificationInbox.tsx`, `NotificationPreferences.tsx` | Generic header badge, one paged inbox shared with Progress, global preference form in Settings |
| `services/notifications.ts`, `types/notifications.ts`, `stores/notificationStore.ts` | Independent owner-scoped generic client/contracts/cache and one polling coordinator |
| `pages/SettingsPage.tsx` | Add query-aware Notifications tab, accessible three-tab navigation and shared preference component without losing Profile/Memories state |
| `components/progress/LearningPanel.tsx`, `ContextPicker.tsx`, `ConceptList.tsx`, `ConceptDetails.tsx`, `LearningActivity.tsx` | Real typed learner reads and honest evidence/uncertainty display |
| `services/events.ts`, `services/progress.ts`; corresponding typed schemas | Thin authenticated API clients, cursor/date/revision contracts and AbortSignals |
| `stores/eventStore.ts`, bounded `progressStore.ts` only if shared reuse warrants it | Owner-scoped normalized entities/query pages, decision recovery, delta merge, dedup and cancellation |
| `ChatMessage`, chat types/response metadata, citation transformer, `AppLayout` | Wire bounded proposal/event metadata, references and header bell without rewriting stored chat history |

Reuse existing Button/Input/Textarea/Select/Spinner/Toggle, shared Markdown/Prism for evidence only when useful, semantic tokens and ThemeProvider. Claims/title text never executes HTML/code. Native dialogs must be portaled when layout clipping demands it and correctly trap/restore focus. Avoid nested dialog stacks: one shared review/detail dialog at a time.

### 13.8 Required frontend acceptance matrix

| Workflow | Required coverage |
| --- | --- |
| Navigation | Drawer/sidebar entry, query deep links, back/forward/refresh, unknown tabs/IDs, keyboard tab behavior and preserved drafts |
| Event CRUD | Manual create/edit/complete/cancel/reopen/delete; duplicate/quota/date validation; changed request payload; lost response; deleted/stale targets |
| Date display | Date-only stable in positive/negative offsets, multiple zones, locale display, DST fold/gap choices, midnight rollover and start/end validation |
| Confirmation | Chat/Progress review, edited fields, missing details, capture-off manual approval, approve-vs-dismiss races, stale target and terminal cards after restart |
| Reminders | Badge/inbox/read/dismiss, global/per-event switches, worker-off delay state, offline/focus recovery, reschedule/delete while inbox open and no account leakage |
| Learning | Empty/unsupported data, owned context/concept filtering, separate confidence values, unknown vs zero, bounded activity, real study links and no event-derived mastery |
| Async state | Late page/detail/summary responses, filter changes during pagination, cross-tab changes, repeated clicks, cancellation, logout/account switch and unavailable storage/BroadcastChannel |
| Visual/accessibility | 320/390/768/1280px, Light/Dark/System, reduced motion, keyboard-only, 200% zoom, long titles/localized labels, one-line action buttons, visible focus, screen-reader status/error relationships |

## 14. Correctness rules added during proof-check

### 14.1 Time and date contracts

- Extend `SendTurn` with an optional validated IANA `client_timezone` and persist the accepted source-zone snapshot in user-message metadata. Source creation time remains server-generated. Older messages without a historical zone require confirmation for relative dates; a new account preference cannot retrospectively establish it. Define explicitly whether request timezone participates in retry hashing: identical client turn IDs reuse the original saved scope; a changed semantic payload is a conflict, not a second turn.
- Persist source-time/date wording/zone and date-resolution policy version in the event evidence/proposal. A retry/resume cannot reinterpret a relative date. Runtime account timezone is not the timezone of the coding agent; client Asia/Karachi is not a global application default.
- Default ambiguous "next Monday"/"03/04"/missing year/vague time to confirmation. An explicit full ISO date or unambiguous "tomorrow" with known source zone can save automatically as date-only. Reject invalid dates/leap-day values and unresolved DST gaps; folds require an explicit offset choice. Free-form parser confidence alone does not decide ambiguity.
- Date-only v1 events have one date. Assignment/deadline cutoff is exclusive next-day local midnight. Occurrences stay Today through that day and move to Past at next midnight; timed occurrences move to Past/In progress based on start/end. Deadline equality is due, not a future reminder opportunity. Handle nonexistent/skipped local dates using timezone policy and explicit validation.
- Default date-only reminder is 09:00 event-local time on the prior calendar day. Timed 24-hour reminders mean elapsed duration before the aware start/deadline. A DST gap/fold in a default reminder follows a documented reminder policy (shift to first valid instant, or choose the earlier occurrence), shown in the preview; this cannot silently alter the event time itself.
- Use `ZoneInfo` with timezone data available in Linux images and Windows tests; validate `tzdata` availability and pin/include it if needed. Use database UTC for delivery comparisons and an injected clock in tests. Browser/host clock skew never controls saved deadlines or leases.

### 14.2 State transitions, evidence and race fencing

- Event lifecycle is scheduled -> completed/cancelled and explicit reopen -> scheduled. Completing twice is idempotent. Reopening never replays old delivered reminders; only an undelivered lifetime reminder with a future due instant can be scheduled; a delivered ledger is permanently fenced. Permanent delete is terminal. Time passing only changes the derived time bucket.
- Proposal lifecycle is pending -> accepted/dismissed/expired/cancelled; processing is a recoverable lease, not a permanent final state. Unsupported recurring requests become a clear one-off correction/clarification proposal, never an invented series.
- Store exact proposed operation and target revision. Automatic changes may update an AI-controlled event only on unambiguous new user evidence. Changes to a manually controlled event, fuzzy duplicate selection, completion/cancellation with ambiguous target or conflicting schedule always require explicit review. Completing an event requires a direct completion statement; past time is insufficient.
- At AI commit, fence owner, current turn attempt/RUNNING state/lease, source visibility/existence, preferences, target revision, suppression and quota again. Persist current operation receipts before reporting save success. A later retry must reject an obsolete success receipt after the user corrects/deletes its target. Expired turn execution cannot commit a new proposal/event.
- Explicit proposal decisions have their own workflow/decision lease, not the expired original chat-turn lease. The source chat's continued existence is checked for pending-source validity; once accepted, source deletion detaches evidence and retains the event. Replayed decisions return their original terminal outcome only if it still represents the live record, otherwise unavailable/current-changed.
- Final assistant publication rechecks all exposed E event revisions and pending proposal references under the existing owner lock. An unchanged pending proposal may have become accepted; hydrate its current action outcome without falsely presenting old approval controls. Deleted/changed event dates must not become freshly published current assertions. Previously delivered transcript text is historical and is not rewritten.
- Do not hold database/owner locks across model calls, graph invocation or saver network I/O. Specify a lock order: shared public owner write coordinator -> event/proposal rows -> reminder ledger -> Notifications receipt/inbox -> module sync rows. Graph execution obtains/releases short claims; canonical commit takes the same owner-first order. Cross-owner worker batches use separate transactions, not inversely ordered owner locks.
- Event fingerprints include semantic operation/kind/date/context and source span identifiers, not title alone or the whole message. Suppression targets the dismissed/deleted operation and its relevant span; deleting a quiz must not block an unrelated assignment mentioned in the same message. A new explicit manual addition can intentionally recreate an event. Bound evidence retention while preserving suppression for retired spans.
- Auto-capture off blocks new AI work but leaves user decisions possible. Event reminders off or global notifications off blocks delivery, not existing inbox reads. All relevant switches are rechecked transactionally at their separate write boundaries and never inherit the memory preference.

### 14.3 Minimal checkpoint state and purge reconciliation

Prefer graph state containing proposal/operation IDs, policy versions and decision receipt IDs rather than title/description/quote copies. Persist draft/evidence canonically in owned proposal storage, hydrate it for validation and strip it from graph checkpoint state before writes. ID-only operational checkpoints dramatically reduce duplicated personal data and cleanup risk.

If the selected saver or interrupt payload persists personal draft content, map all saver thread/namespaces to the owned proposal and implement a durable cleanup outbox. Canonical deletion/dismissal/cancellation prevents future graph reads/writes immediately through tombstone/fencing; cleanup is retried idempotently. Reconciliation cannot resume deleted proposals or reintroduce personal payloads while a cleanup task is queued. Do not claim atomic hard purge across separate saver transactions: acceptance tests must wait for and verify completed cleanup. Prefer content-free checkpointing so a canonical content purge has no hidden personal copy.

Deploy saver tables via version-pinned, reviewed migrations in an isolated schema/search path. Do not let every API startup call an uncontrolled saver setup routine or assume opaque saver migrations obey application Alembic. Coordinate application migration lock/setup once; test SQL search paths, permissions, pool lifetime, async/sync saver use, connection limits and shutdown. Cleanup worker/reconciliation must be lightweight and cannot require the LLM to dismiss or expire a workflow.

### 14.4 Reminder scheduling and delivery identity

- Unique `(owner_id, event_id)` on `hm_event_reminder` enforces one lifetime ledger. A schedule version only invalidates pending work; **it never participates in the notification dedupe key**. Immutable Notifications receipt key is `(owner, producer=events, key=reminder:<event UUID>)`. There is no collection of per-event rules and no event-reminder replay endpoint.
- `delivered_at` and receipt identity cannot be cleared by event edits, reopening, preference changes, read/dismiss or inbox cleanup. Keep content-free delivery evidence for the event lifetime and stale retry horizon; pruning a visible inbox row never makes a previously used producer key deliverable again. Account deletion purges all corresponding data. A receipt with missing/pruned inbox content returns a terminal already-delivered result, not a recreated notification.
- Pending schedules can move on temporal/timezone/explicit timing changes and cancel on completion/cancellation/delete. Ordinary title/description/evidence changes do not rearm or change a due instant. Undelivered cancelled/skipped reminders can be explicitly scheduled for a future due time when an event is reopened; delivered ones cannot.
- Retain only minimal temporal metadata on the generic notification (original due/event time and schedule version), plus registered producer/type/owned resource locator. Current owned title/details come through a bounded registered resolver. Mark changed/completed/cancelled events obsolete where appropriate. Deleted targets are unavailable, with no cached title or hidden personal snapshot.
- Date-only catch-up is allowed only before that event's local day starts, not for today's already-started occurrence or deadline. A configured explicit same-day future reminder may deliver before an assignment's cutoff or a timed start; an overdue/past event cannot. The preview and worker use the same eligibility function. This conservative default avoids suddenly reminding about many imported past/today events.
- Both event reminders and Notifications global enablement have persisted revisioned disable windows/epochs. Skip undelivered due instants that fell during any disabled interval, including outages spanning disable/re-enable; do not infer eligibility solely from current enabled=true. A re-enable does not create immediate catch-up. Preserve bounded window history until all relevant pending candidates have been reconciled; a boolean or latest timestamp alone cannot handle multiple toggles. An explicit manual future-time edit may schedule the same undelivered ledger.
- Default timing changes affect new events; explicit bounded apply-to-existing changes only eligible undelivered ledgers. Account timezone changes do not move existing event-local schedules. Global notifications off never stops event saving, manual management or existing inbox reads.
- Shared owner coordination precedes all row locks. Candidate scans hold no locks; each delivery rechecks under owner coordination in one short transaction. Notifications insert/receipt, event delivery mark and both sync changes commit atomically using the public opaque unit-of-work boundary; no nested commit and no direct event SQL access to Notifications tables.
- Inbox read/dismiss never changes event state, due time or the lifetime receipt. Present batches quietly through an aggregate badge and paged inbox; do not toast every event. Bound worker batch size and retries without dropping distinct legitimate events.
- Proposed capacities: 1000 saved events, 50 pending proposals, inbox pages default 30/max 50, 90-day read/dismissed inbox retention and 10,000 changes per module/owner. Unread entries are not silently purged for age or quota. Delivery receipts outlive visible inbox retention. Capacity/backlog/worker degradation is explicit; no silent event deletion or duplicate delivery as a retry strategy.

### 14.5 Delta sync, budgets and recovery

- Encode mixed date-only/timed agenda order in a stable server sort key including temporal mode/timezone policy and UUID. Page cursors bind filter/range/sort and owner scope; do not reuse an upcoming cursor in Completed. Concurrent membership changes invalidate pages instead of claiming a snapshot the query did not take.
- Page responses include the relevant sync watermark; apply subsequent event/proposal and independent notification deltas by entity revision and tombstones. Read snapshots/watermarks consistently or replay overlap safely so an update cannot fall between page fetch and first sync. Never return global counts/unowned IDs before filtering.
- `sync` returns bounded changes, next cursor, has_more, server_time, floor/reset and only changed owned entity projections. Older replay cannot revive a tombstoned event, card, notification or detail. Retained reset clears loaded page caches but never discards an unsaved editor draft without a decision.
- The existing six-call/two-write limit is shared across memories and events. Count each item in a multi-event statement as a write; do not hide an unbounded batch behind one call. If more than two automatic mutations are needed, save at most the verified limit and explicitly report remaining unsaved items/ask for continuation. A model must not claim all requested items were captured.
- Reserve a small bounded result allowance before any event/proposal mutation. Commit outcomes are compact IDs/status/date/single-reminder summaries; personal form payloads load on demand. A post-commit result-budget error cannot be represented as "nothing saved"; recover through receipt/current action state. Model/provider failure and tool-budget failure must not replay a committed write.
- Each module has one owner-scoped polling coordinator, deduplicated across its mounted consumers. Notifications exclusively owns inbox/unread polling; the Events coordinator never polls it again. Poll only while visible/online, reconcile focus/reconnect, use bounded backoff/jitter after failures and stop on logout/401. BroadcastChannel is optional; absent/blocked support falls back to focus reconciliation. Cancel stale requests and compare owner/query epoch before merging.
- Mark payload origin/status/version clearly. No auto-memory injection, no all-events login payload, no full collection replacement on edits, no duplicate interval timers from hidden tabs, and no repeated semantic extraction on progress-page visits.

## 15. API and learner adapter additions

All route paths below are under `/api/v1`; static routes precede UUID routes. Bodies reject unknown fields and carry client request UUID/expected revision where applicable.

| Addition/refinement | Contract |
| --- | --- |
| `POST /events/temporal-preview` | Bounded manual local date/time/zone/single-reminder normalization; no model call or persistence; return UTC/date-mode choices and field errors |
| `GET /events/summary` | Small owned upcoming/pending summary (unread belongs to Notifications), sync watermark/server time; no event collection in login bootstrap |
| `GET /events/operations/{client_request_id}` | Recover a lost manual create or decision response without issuing a new write; no access to arbitrary graph IDs |
| `GET /progress/contexts` | Bounded public learner context pages; auth owner injected; no module-internal SQL from API |
| `GET /progress/learning` | Bounded typed concept/recommendation/verification summary for owned context filters, with as-of times and supported/unknown flags |
| `GET /progress/concepts/{id}` | Typed owned state/details; canonical ID alone does not grant access to another learner's state |
| `GET /progress/activity` | Bounded date/context/concept-filtered, redacted evidence/activity pages through a new public learner read contract |

Keep learner read schemas distinct from event schemas and normalized caches. Do not expose internal audit JSON, raw reasoning, policy internals or an unbounded `accepted_evidence_ids` array. Public learner progress reads must preserve policy identities and unknown states without recomputing/mutating mastery simply because the user opened Progress. Existing state projection freshness behavior should be explicit and tested where reads currently refresh derived state.

Deletion endpoint retries return a stable deleted/unavailable outcome for an owned deletion receipt; they must not create a new record. Distinguish REVISION_CONFLICT, DUPLICATE, CAPACITY, DATE_AMBIGUOUS, SOURCE_DELETED, PROPOSAL_EXPIRED, PREFERENCE_DISABLED and WORKFLOW_UNAVAILABLE instead of using one 409 recovery path for all failures. Unknown owner targets use the same non-disclosing not-found response.

## 16. Audit evidence and release gates

| Proof-check finding | Correction incorporated |
| --- | --- |
| Learning remained a placeholder despite the user's two-feature Progress request | Real Learning UI, bounded learner public read contracts, adapter routes and acceptance tests are required in Phase 5 |
| Original timezone was absent from persisted evidence | Validated source-message zone snapshot and deterministic relative-date replay |
| Past occurrence and overdue deadline were conflated | Type-aware temporal buckets; completion remains a user/evidence action |
| Capture-off cancelled proposals while also promising manual approval | Existing proposals stay reviewable; new/in-flight AI writes stop; explicit decisions remain manual |
| Separate graph/event transactions were described too much like one atomic purge | Minimal ID-only checkpoints, tombstone fences and durable cleanup/reconciliation where personal saver payloads exist |
| Reminder edits could duplicate deliveries or flood after re-enable | One lifetime event ledger, immutable producer key independent of schedule version, retained receipts and persisted disabled windows |
| Event-specific inbox design prevented reuse by other features | Standalone Notifications module, generic producer API, own tables/preferences/sync, shared header/Settings/Progress UI |
| Multiple reminder rules violated the user's anti-flooding requirement | Exactly one configurable reminder, permanently fenced after delivery including edits/reopen and inbox purge |
| Worker lock ordering could deadlock event deletion | One owner-first transaction order across graph/API/reminder paths |
| Shared tool budgets could silently lose extra events or hide a committed save | Per-item counts, pre-reserved compact mutation outcomes and durable operation recovery |
| Frontend lacked component/state/navigation/error coverage | Complete sections 13–15, typed APIs, all terminal states, learner UI and explicit browser matrix |

This is a codebase-checked design, not a guarantee that implementation will be bug-free. No application tests, migration rehearsals, graph dependency installs or image builds were performed for this plan-only request. Mandatory implementation evidence still includes: compatible package pins under the actual Docker Python runtime; schema/upgrade/downgrade and saver-cleanup rehearsal; synthetic and adversarial model/date fixtures; multi-worker/multi-tab race tests; production asset UI/accessibility checks; full relevant regressions; rebuilt backend/frontend/events-worker runtime restart/delivery/purge verification.

Record each phase's files, migrations, dependency pins, commands, actual counts and unresolved deviations in section 12. A phase is complete only after its stated exit and the applicable sections 13–17 acceptance conditions pass. In-app notifications mean a durable inbox delivered while closed and visible on return; they do not promise an OS alert when the browser is closed. Historical mastery charts and recurrence are explicitly future capabilities, not missing implementations disguised as supported features.

## 17. Standalone Notifications module: required implementation

### 17.1 Ownership and public contracts

`app.notifications` is an independent domain module inside the current backend, not a history-management submodule or a new service. Its public facade owns durable in-app notification creation, idempotency receipts, inbox state, preferences, summaries and bounded sync. Events decides when a reminder is eligible, then calls the facade; Notifications neither scans event tables nor implements academic date/lifecycle logic. Future learner/library/account producers use the same facade without importing Events.

Expose server-only `publish_in_transaction(owned_uow, producer, key, type, resource, minimal_metadata)`, bounded lookup/list/summary, read/dismiss, preference and sync contracts. Owner comes from authenticated or registered server context; clients/LLMs cannot publish arbitrary notifications or choose another owner. Producer/type names and resource schemas are registered allowlists, not arbitrary URLs, model HTML or arbitrary client JSON. No new LLM notification-writing tool is required.

Extract a public shared owner-write/unit-of-work coordinator under `app.db`, preserving existing chat/memory serialization and revisions. Consumers must not import private `ChatRepository._sync_lock`. Every competing chat/source deletion, final publication, event/proposal mutation and notification write follows the same owner-first boundary. Verify compatibility with current owner-row locking before selecting a concrete lock implementation; do not add a parallel advisory lock that existing writers ignore. A bound unit of work is opaque to domain callers; Notifications uses its own adapter to participate in the caller's transaction without leaking tables or committing it. Standalone writes may open their own coordinated transaction. Release tests must prove rollback across modules and deployment-compatible lock behavior.

Register resource resolvers/renderers through application composition, not Events imports inside Notifications. Batch owned resource resolution per visible page; no N+1 request/query per inbox row. For event notifications, resolve current details and their lifecycle through Events' public read contract. Missing targets degrade safely; notifications cannot restore deleted resources. Other producers may supply their own safe presentation policy and resource resolver later.

### 17.2 Generic persistence and retention

| Notifications-owned table | Required invariant |
| --- | --- |
| `notification` | Owner, UUID, registered producer/type, owned opaque resource locator, minimal validated payload, delivered timestamp, read/dismiss state and revision. No restricting event FK or permanent event-title/description copy. |
| `notification_receipt` | Unique owner/producer/idempotency key; immutable delivered outcome and optional inbox locator. Inbox deletion can null the locator, never delete the lifetime dedupe record or republish. Keys contain server resource identity, not private user text. |
| `notification_preferences` | Global in-app enabled flag (default on), revision and delivery-disable history/reconciliation watermark. Future channels require explicit new contracts, not implied permissions. |
| `notification_sync` / `notification_change` | Independent owner watermark, bounded entity/preference changes and tombstones, floor/reset contract. Filtered streams advance a global watermark correctly even across nonmatching records. |

Composite ownership constraints, keyset `(delivered_at, id)` pagination, producer/read/dismiss filters, indexed unread counts and bounded payload/locator lengths are mandatory. Notification receipt and inbox creation are atomic. Read is idempotent; dismissal is terminal for the inbox record, implies read and removes it from unread counts; an outdated mark-unread request cannot resurrect a dismissed row. Do not expose mark-unread in v1 unless its concurrency contract is added. Count updates and change records commit with the mutation; choose indexed counts or a tested transactional counter during performance rehearsal, never a drifting frontend-derived total.

Default global disable blocks new publication, preserving existing inbox access. Each producer rechecks it inside publish and defines how skipped eligibility is reconciled; Events uses section 14.4's disabled-window policy. Disabling does not queue an automatic notification dump to be replayed on enable. Preferences can never reset producer receipts. Generic receipts have a documented producer-lifetime/retry retention contract; the Events producer requires lifetime dedupe even when visible read/dismissed notifications are pruned. Account purge covers notifications, receipts, preferences and sync. Deleting the notification's resource invalidates/redacts payload caches and emits notification changes; content-free receipts may remain until account purge. Deleting an event's source chat alone does not delete the saved event or invalidate its reminder: the event remains the notification resource.

### 17.3 API, cache and frontend wiring

All endpoints use existing authenticated `/api/v1` identity/origin protections and fixed paths before UUID routes. No Events aliases that accidentally create a second cache/API owner.

| Endpoint | Behavior |
| --- | --- |
| `GET /notifications` | Bounded cursor page, optional registered producer/unread filters, watermark and server time; dismissed entries excluded by default |
| `GET /notifications/summary` | Small owned total unread and requested producer unread counts, watermark, preference status; no event list |
| `GET/PATCH /notifications/preferences` | Global in-app setting with expected revision; producer-specific reminder setting stays in Events |
| `PATCH /notifications/{id}` | Explicit read or dismiss; expected revision and operation UUID, monotonic/idempotent outcomes |
| `GET /notifications/sync` | Bounded owned entity/preference deltas, tombstones and floor/reset; filtered watermark semantics tested |

Add `NotificationBell`, `NotificationInbox` and `NotificationPreferences`, generic typed client and independent normalized owner-scoped store. One authenticated coordinator serves header, Settings and Progress; no duplicate summary fetch/interval per mounted component. Bootstrap summary once per authenticated owner; load full pages only on opening. Fence owner and filter epochs, use consistent page watermarks, reconcile cross-tab/focus, stop on logout/401 and clear cached payload/drafts on account changes. Do not persist personal inbox payloads to IndexedDB without an offline requirement.

Settings gains `?tab=notifications` alongside existing Profile/Memories. Update its tab validation, URL/back/refresh behavior, roving keyboard navigation and panel retention for three tabs. Remove the existing two-tab assumptions in `changeTab` and arrow/Home/End handling. Use a horizontally scrollable tablist on narrow viewports, keep tab labels unwrapped and reveal the focused tab without horizontal page overflow. Link **Notification settings** from the shared inbox; existing bottom-drawer Settings link continues to open Settings. Global **In-app notifications** uses the shared Toggle and explains its effect on all producers. Events **Event reminders** remains domain-specific. Show each persisted value and failed/stale update independently; one toggle must not mutate the other or memory settings.

The global header panel defaults to all notifications. Progress **Reminders** uses the exact same inbox component/store filtered to Events, and event clicks open the shared owned detail view. Provide loading, empty unread/all, retry, unavailable/deleted target, changed/obsolete event and capacity/degraded-worker states. Generic type renderers are allowlisted and safe text only; unknown future types display a safe fallback without arbitrary navigation. Badges cap visible text at 99+ with accessible actual counts; loaded-page length is never the total unread count. Avoid opening nested dialogs: close the inbox before opening event details and preserve the return focus target.

### 17.4 Anti-flooding and release evidence

- Deliver the same event through two concurrent workers, retry a lost response, reschedule repeatedly before/after delivery, reopen, disable/re-enable, read/dismiss, prune the inbox row and restart containers: lifetime event receipt count and notification creation count remain at most one.
- Repeat with multiple rapid preference toggles and a worker outage spanning them. Eligible future events deliver once; disabled-window/past candidates do not generate catch-up floods.
- Seed many distinct due events: bounded worker batches converge without per-item toasts, sounds or automatic popups; one aggregate badge and paged inbox remain responsive. Grouping is presentation, not loss of distinct notification identities.
- A synthetic second producer publishes without importing Events; verify independent keys, safe render fallback, owned inbox filters, global disable, read/dismiss/count concurrency and retained receipt dedupe after pruning.
- Verify cross-module atomic rollback, consistent owner lock order, no duplicate polling with Settings/Progress/header mounted, bounded resolver queries, stale filtered sync, two-account isolation, logout races and complete account purge.
- Rebuild backend/frontend and verify the shared Notifications UI, Settings third tab, Events-filtered Progress inbox and worker delivery using final images. Record actual migration/runtime/test evidence in phases 4A/4B/5/6/7; this plan alone does not implement Notifications.
