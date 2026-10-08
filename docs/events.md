# Events implementation: first backend increment

Implementation began on 2026-10-09. This increment provides manual event storage
and authenticated APIs. Automatic extraction, proposals/LangGraph, Notifications,
reminder delivery, and the Progress frontend are still unimplemented. A pending
reminder ledger is a schedule record, not a delivered notification.

## Structure and integration

- `app.history_management.events`: provider-independent service, contracts, typed
  schemas, temporal normalization and factory; composed as `HistoryManagement.events`.
- `app.history_management.repositories.events`: PostgreSQL persistence, independent
  event/evidence/audit/preferences/receipt/suppression/reminder/sync tables.
- `app.db.owner_transactions`: public owner-first transaction boundary using the
  existing chat sync row. Chat and memory use the same lock; no parallel advisory
  lock or new turn status was introduced. Persistence adapters receive the bound
  unit of work; domain callers do not receive SQL sessions.
- `app.api.routes.events`: thin, onboarded, owner-bound `/api/v1/events` endpoints.
  Cookie writes retain the existing trusted-origin checks. Personal responses use
  `Cache-Control: no-store`; request bodies reject extra fields.
- `20261009_0007_events`: frozen migration from `20261008_0006`. It includes owned
  composite FKs, temporal/status/reminder constraints, indexes and a trigger that
  prevents changing a reminder identity or rearming delivered reminders.
- `20261009_0008_event_reminder_retention`: additive deletion fence retaining
  every reminder ledger until its parent event is permanently removed. Parent
  deletion still cascades; migration 0007 remains frozen.

Optional learning contexts are checked through the public learner facade, with a
composite ownership FK as the transactional fence. Event completion never submits
learner evidence or changes mastery. Source chat deletion marks event evidence
deleted and emits event changes in the existing chat deletion transaction; saved
events remain. Permanent event deletion cascades personal evidence/audit/ledger
rows and retains content-free operation receipts and suppression hashes.

## Manual API

| Endpoint | Behavior |
| --- | --- |
| `GET/POST /events` | Bounded agenda / idempotent manual creation |
| `GET/PATCH/DELETE /events/{id}` | Owned detail, versioned replacement/lifecycle, permanent deletion |
| `GET/PATCH /events/preferences` | Independent capture/reminder settings, timezone, default timing |
| `POST /events/temporal-preview` | UTC choices, DST ambiguity and field errors, computed single reminder; no write/model call |
| `GET /events/operations/{request_id}` | Recover a lost response; deleted outcomes cannot recreate events |
| `GET /events/summary` | Small upcoming count and sync watermark |
| `GET /events/sync` | Bounded current projections/tombstones, watermark/floor/reset |

Create, edit and delete require a client request UUID. Edits/deletes require the
expected event revision. Detail edits supply a complete `details` draft, avoiding
partial date-mode switches; lifecycle edits supply `status`. Reopen uses
`status=scheduled`. Reusing a request UUID with a different payload yields
`OPERATION_CONFLICT`; a stale revision yields `REVISION_CONFLICT`. Operation replay
hydrates current state, including deletion, instead of replaying historical form
payloads. Unknown owner resources return non-disclosing 404s.

List requests accept aware `after`/`before` instants, kind/status/title filters and
pages of at most 50. Ranges are capped at 366 days. Supply a stable explicit range
when paging; cursors bind the owner, filters and watermark. Membership changes
return `PAGE_CHANGED`. Page/detail/sync reads use a consistent PostgreSQL snapshot
and a five-second query deadline. Owner writes also bound lock/query waits;
known timeout failures return retryable `EVENTS_UNAVAILABLE` without committing.
Reads batch projections, and the sync log retains
10,000 changes per owner. Expired/future sync cursors return reset. Historical
change entries hydrate a tombstone if an event has since been deleted.

## Temporal and reminder policies

Dates are accepted from 1900 through 2200. Date-only events require a local date
and IANA zone; timed events require aware instants and their original IANA zone.
The server never uses the host zone or invents a start time. The preview returns
both UTC choices for a repeated local time and no choices for a nonexistent time.
Entirely skipped civil dates are rejected; midnight DST gaps are handled as civil
day boundaries. Timed ends must follow starts.

An exam/quiz/study becomes past, while an unfinished assignment/deadline becomes
overdue at its cutoff. Date-only cutoff is the end of its local civil day; timed
cutoff is the explicit end or start. Passage of time does not complete an event.

Defaults follow the plan: capture and event reminders on; account timezone unknown
until set; timed reminder 24 hours before; date-only reminder 09:00 the previous
day. One event owns one lifetime ledger. Before delivery, edits replace its pending
schedule when its date or reminder is explicitly changed. Metadata edits preserve
the saved due instant even after account default changes. Reopening preserves
that instant, skips a missed reminder and only rearms a future undelivered one.
After delivery, lifecycle/date edits retain its delivered outcome and
the database rejects rearming. A late-created upcoming event gets one immediate
eligible schedule. Past events get a skipped schedule. Disabling reminders fences
already due ledgers; re-enabling skips times missed while disabled even if no
worker ran, preserving future due schedules. An ordinary title edit cannot revive
a skipped reminder. Global notification preferences and publication will be added
by the separate Notifications module, not inferred from this event preference.

Capacity is 1,000 saved events per owner, with explicit `CAPACITY` errors. Manual
capture is independent of the automatic-event switch. Automatic enforcement will
be implemented with the event tools; this increment does not claim AI capture.

## Dependency gate discovered during rehearsal

The real backend image runs Python 3.12 with `langchain-core==0.3.86` and
`langchain-openai==0.3.35`. In disposable containers:

1. `langgraph==0.6.11` / saver `2.0.25` resolves without upgrading those packages,
   but selects checkpoint `2.1.2`.
2. `langgraph==0.6.11` / checkpoint `3.0.1` / saver `3.0.4` installs and has
   `delete_thread`, but its serializer lacks `allowed_msgpack_modules` hardening.
3. Patched `langgraph==1.0.10` / saver `3.0.4` cannot resolve with the current
   LangChain/provider pins: its prebuilt package requires core 1.x while the
   provider requires core below 1.0.

The [upstream checkpoint advisory](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-g48c-2wqr-h844)
identifies affected graph releases through 1.0.9 and describes strict serializer
controls. The [prebuilt 1.0.8 metadata](https://pypi.org/pypi/langgraph-prebuilt/1.0.8/json)
declares core 1.x. Neither an unsafe old candidate nor an untested framework
upgrade was added to production requirements. Phase 0 remains open; the graph
adapter, durable interruption/restart/resume and saver cleanup rehearsal still
need a safe compatible selection or an explicitly documented framework migration.

`backend/testing/event_dependencies.py` is a reproducible **disposable-container**
rehearsal, guarded by `MENTRA_DISPOSABLE_REHEARSAL=1`. It installs candidates only
in that container and refuses to proceed without strict serializer support. It
must never run during application startup. Graph runtime/cleanup assertions have
not passed and are not claimed as implemented behavior.

## Verification and deployment boundary

### Verification re-pass (2026-10-09)

The re-pass reproduced and fixed reminder timing drift, missed-reminder replay on
reopen, equivalent-offset rejection, receipt recovery after context loss,
context-deletion races, unbounded owner-lock waits, upcoming-count discrepancies,
extreme-date API failures, DST-fold comparisons and preview errors. It also rejects
host timezone aliases, accepts valid past dates with unused historical reminder
gaps, preserves second-accurate historical civil boundaries, batches bulk owner
changes and uses one clock instant per page/sync projection.

The database now fences direct ledger deletion as well as delivered-ledger
updates. Tests verify direct deletion fails, parent purge succeeds, and migration
0008 downgrade/re-upgrade preserves rows and the original delivery fence.

Local focused verification: **40 tests passed** in 7.216 seconds, covering Events,
API and migration concurrency (`.events-repass-tests.log`). The final image suite
passed **all 333 backend tests** in 138.216 seconds
(`.events-repass-docker-tests.log`); frontend build and theme checks also passed.
Details are recorded in plan section 12.2. The disposable database
is `mentra-events-repass-test-20261009`; application databases and running
application containers remain untouched. The earlier counts below describe the
initial increment, before this re-pass.

The dedicated `mentra-events-test-20261009` PostgreSQL 17 container used only a
localhost port and a disposable database; tests created temporary owned schemas.
No application database or existing application container was migrated/restarted.
The verification image is `mentra-events-foundation-verify`, built with the actual
backend Dockerfile; test fixtures are mounted read-only, application code and
migrations come from the rebuilt image.

Local Python 3.14: **23 tests passed**, including event temporal/persistence/API
and migration concurrency. They also passed while the broader Docker suite ran.
The final Python 3.12 image regression result is recorded in the implementation
plan, section 12, alongside the exact command and logs.

Verification covers revision and create races, changed-payload retries, permanent
purge/replay, owner/context isolation, independent preferences, disable windows,
immutable delivery, DST gaps/folds/skipped dates, cutoffs, query-bound cursors,
tombstones, capacity, rollback, source retention, cookie origins and typed API
responses. Upgrade/downgrade compares all non-event row snapshots and schema
metadata, preserving existing records with zero metadata drift.

Concurrent rehearsals exposed an existing migration deadlock: blocking on the
global advisory lock held a transaction snapshot that another migration's
concurrent index build awaited. `app.db.migrate.upgrade` now probes the same
session advisory lock without blocking, commits failed probes before waiting,
and times out after 300 seconds. Tests cover competing fresh schemas and timeout
cleanup; the migration lock identity and existing schema revisions are preserved.

Remaining rollout work: AI admission/tools, safe durable confirmation, generic
Notifications, event reminder producer/worker, complete Events/Learning UI, chat
references/proposals, account purge/retention/performance gates and deployed
end-to-end/browser verification. The original plan remains the delivery contract.
