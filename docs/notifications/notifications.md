# Notifications inbox

`app.notifications` owns account-scoped inbox records, publication preferences,
read/dismiss state and synchronization. It is independent of Chat, Learner, the
LLM and scheduler logic. Registered producers publish through its public service;
Events is the current producer. `/notifications` provides the inbox, and the
sidebar shows unread status.

## Reminder delivery

`events-worker` processes due event schedules. Notification publication and the
event's lifetime reminder ledger outcome commit in the same transaction. A
successful publication marks delivery and retains its receipt; disabled
publication is skipped. A pending schedule alone is not proof of delivery.
Replays cannot duplicate a delivered lifetime reminder.

Notifications preferences (`enabled`, `disabled_kinds`) are separate from Events
capture/reminder preferences. Turning off automatic event capture does not delete
saved events or disable the inbox. This implementation delivers in-app records;
email and push channels are not implemented.

## Authenticated API

All paths are under `/api/v1/notifications`, require onboarded identity, and
return personal responses with `Cache-Control: no-store`. Ownership is bound by
the server. Cookie mutations retain trusted-origin enforcement.

| Method/path | Purpose |
| --- | --- |
| `GET /` | Inbox page; `unread`, optional `before` UUID and `limit` (default 30, maximum 50) |
| `GET /preferences` | Current publication preferences |
| `PATCH /preferences` | Update `enabled` and `disabled_kinds`, with `expected_revision` |
| `GET /sync?after=…` | Reconcile inbox changes from a revision |
| `PATCH /{identifier}` | Revision-fenced `read` or `dismiss` action |

Inbox actions require a positive expected revision; preference creation accepts
revision zero. There is no separate unread-count endpoint. Read/dismiss actions
do not modify event details, submit learner evidence or call an LLM.

See [Events](../events/events.md) for temporal and lifetime-ledger rules, [setup](../getting-started/SETUP.md)
for worker startup, and [logging](../observability/backend-logging.md) for delivery diagnostics.
