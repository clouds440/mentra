# Chat organization

Pinning and archiving change metadata, never message content. They retain activity timestamps and advance conversation revisions. Archiving clears pins; unarchiving returns chats to Recents. Archived chats remain readable from Settings and explicit search results.

| Experience | Behavior |
| --- | --- |
| Pinned | Icon and heading above Recents; menu supports Unpin. Up to 100 pins per owner; bootstrap includes older pins. |
| Archive | Separate Settings tab with pagination, Open, Rename, Delete, Unarchive and selection. |
| Search | Archives excluded by default; explicit Include archived chats switch and archived result label. Automatic cross-chat summary search excludes archives too. |
| Selection | Menu or mobile long press → Select. Circular checks, count, select up to 100 loaded chats, archive/unarchive, delete and Escape. |
| Bulk work | Immediately opens a fresh chat; pending rows are gray, inert and show a spinner. Permanent deletion requires confirmation with selected titles. |

All paths below are under `/api/v1/conversations`. Authenticated owner, trusted-origin and onboarding requirements apply to mutations. No client owner field is accepted.

| API | Contract |
| --- | --- |
| `PATCH /{id}/organization` | `expected_revision` and exactly one of `pinned` or `archived`; returns canonical conversation. |
| `GET ?archived=true&limit=30&cursor=…` | Owner-scoped archive ordered by archive timestamp/ID. Default collection pages unpinned active chats. |
| `POST /bulk` | `client_request_id` UUID, `action` (`archive`, `unarchive`, `delete`), 1–100 unique `{conversation_id, expected_revision}` items. Returns 202 durable receipt. |
| `GET /bulk/{id}` | Owner-scoped progress, completed IDs, per-item failures and terminal state; no-store. |
| `GET /search?query=…&include_archived=true` | Explicit archive opt-in; existing search bounds and authorization apply. |

Admission validates the whole selection atomically. A UUID identifies one immutable action/selection; retries replay its receipt even after completion. Changed payloads are rejected. Each owner may have 10 unfinished batches. Pending rows cannot be renamed, pinned or admitted twice; pending deletion rejects new turns.

The existing events worker processes bounded batches without inference/network calls. It takes the existing owner-first lock and processes one chat per short transaction. Deletion reuses the canonical purge and dependency-detachment contracts. Savepoints isolate item failures and preserve failed content; process/connection failure rolls back both item and receipt for retry. Concurrent workers skip busy owners.

The browser persists an owner-scoped outbox before admission, retains UUID/payload after uncertain responses and recovers accepted work from server pending markers. Pin/pending rows are protected from ordinary cache eviction. Account changes fence late responses. Feedback reports partial failures without displaying arbitrary server text.

Migration `20261107_0051` is additive. Deploy backend/migration before events worker and frontend; recreate other workers using the same backend image. Application rollback retains the additive schema. Schema downgrade refuses to discard existing pins, archives or receipts.

Regression checks: `backend/tests/test_chat_organization.py` and `frontend/tests/chat-organization.spec.ts`, alongside persistent-chat, saved-search and design suites. Tests use synthetic chats/disposable schemas and cover ownership, revisions, idempotency, partial rollback, concurrent workers, restarts, both themes, keyboard, mobile long press, accessibility, reload and lost responses.
