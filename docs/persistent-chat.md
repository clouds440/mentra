# Persistent conversations

PostgreSQL is the canonical history store. Browser memory and IndexedDB are disposable, account-scoped caches. New Chat creates a conversation only on its first send. The sidebar can reopen, rename, and delete conversations; `/chat/:conversationId` survives refresh and login on another device. The Google Drive backup placeholder has been removed.

## Backend boundaries

`app/chat/repositories` owns SQL and table metadata. `ConversationService` owns durable generation attempts. `HistoryContextPolicy` owns prompt selection. `ConversationHistoryReader` exposes synchronous/asynchronous LangChain messages from the same canonical rows; it does not maintain another transcript or bypass the transactional write service. API routes reuse the existing authenticated identity, profile gate, RAG orchestration, provider service, and database pool.

Alembic migration **20261008_0005** adds:

| Table | Records and access path |
| --- | --- |
| `chat_conversation` | Owner, title, selection, revision, message count, timestamps, deletion tombstone; recent chats by owner/time/ID |
| `chat_message` | Immutable individual messages, conversation sequence, content and JSONB citation/retrieval metadata; owner/conversation/sequence index |
| `chat_turn` | Client UUID, request fingerprint, user/assistant sequences, attempt, lease, state and safe error |
| `chat_sync_state` | Owner's committed revision and retained change floor |
| `chat_change` | Compact conversation references ordered by owner/revision |

Composite foreign keys enforce conversation ownership. The authenticated `learner_id` is the owner for both standalone accounts and mapped external identities. No client-provided owner is accepted. Cookie mutation endpoints retain trusted-origin enforcement and onboarding requirements. Read-only bootstrap is permitted before onboarding so registration does not trigger a failing chat prefetch.

Owner-scoped locks serialize short writes and synchronization snapshots, never model/RAG network work. Every change and its revision commit in the same transaction. Revisions cannot commit out of order. The last 10,000 changes per owner are retained; an expired cursor requires a fresh bounded bootstrap. Deletion removes message/turn content while retaining a conversation tombstone for reconciliation.

## API

All paths are under `/api/v1/conversations`.

| Operation | Endpoint |
| --- | --- |
| Bootstrap / changes | `GET /sync?cursor=…` |
| Older conversations | `GET ?cursor=…&limit=40` |
| New question / retry | `POST /turns` |
| Latest / older / newer messages | `GET /{id}/messages?before=…` or `?after=…` |
| Generation recovery | `GET /{id}/status` |
| Rename | `PATCH /{id}` with title and expected revision |
| Delete | `DELETE /{id}?expected_revision=…` |

Send only `{conversation_id, client_turn_id, expected_revision, content, retrieval, retry?}`. The server retrieves history. A successful send returns the affected turn's messages, not a transcript page. Retries use the same client turn UUID; a changed payload under the same UUID is rejected. Conversation edits and new turns require the expected revision. One running generation per conversation is allowed; other conversations are independent.

The user question is committed before inference. Assistant messages are appended after successful inference; failures retain the question. Generation runs in a shielded, tracked task with a 150-second deadline and a 180-second durable lease. Disconnecting an HTTP caller does not cancel the generation. Restarted processes expose expired attempts as recoverable failures; retries increment the attempt and fence out late results. A completed turn is replayed without another model call. Only the latest failed question can be retried without introducing conversation branches.

Provider execution is not exactly-once across process failure. Persistence is deduplicated and attempt-fenced; the model provider may still charge for an interrupted attempt.

The old `/api/v1/chat` endpoint remains **deprecated and stateless** for existing integrations/tests. The frontend no longer uses or exports its full-transcript sender. Persistent clients must use `/conversations/turns`.

## Loading, caching and synchronization

`chatStore` is an external React store with separate list/conversation subscriptions. Authentication activates it once per owner/session restoration. Repeated auth identity checks do not repeat bootstrap. It hydrates cached summaries first, then makes a single-flight delta/bootstrap request. Initial summaries are bounded to 40; history is fetched when opening a conversation, with a latest page of 40. Reopening an unchanged, loaded conversation uses memory without another history request.

IndexedDB uses `idb` and separate conversation, immutable message, pending-send, deletion, and cursor stores. A cache transaction applies changed records and the synchronization cursor together. Existing message IDs are not rewritten. Successful sends cache only the new turn messages. Cache capacity is 80 conversation summaries, 200 messages per conversation, and 10,000 deletion fences; memory retains up to 12 inactive conversation views plus active/pending views. Pagination cursors account for disk eviction. Cache schema upgrades close older connections. Blocked storage falls back to memory and PostgreSQL.

The rendered window is capped at 200 messages. Older messages are loaded with sequence cursors and scroll-position preservation. When older paging drops the newest messages, Back to latest restores the latest page. Sending from such a window first restores latest history, preventing a gap in the displayed exchange.

Mutation responses update memory immediately. BroadcastChannel signals other tabs to synchronize. Focus, visibility restoration, and network reconnection fetch bounded deltas; idle clients have no permanent polling or socket. Recovery polling runs only for accepted, running turns, with bounded backoff. The database change feed can support future SSE without changing canonical history storage.

Account transitions cancel stale requests, replace memory and close the old cache. Logout also deletes that account's IndexedDB cache and propagates through existing auth cross-tab signaling. A pending send is stored before HTTP transmission; unknown outcomes are checked before retry, and no offline question is automatically sent. Explicitly rejected questions can be restored to the composer. Deletion fences prevent delayed responses from resurrecting deleted cache records.

## LLM context

Stored/UI history and model input are independent. Generation reads a bounded recent candidate set (256 messages), excludes failed earlier questions, and selects context **once, after retrieval**. Only role/content enters history input; UI citations, retrieval metadata and historical source packets are not re-injected. The latest question is always retained and trimming starts at a user-message boundary.

| Configuration | Default |
| --- | --- |
| `CHAT_HISTORY_TOKEN_BUDGET` | 4096 |
| `CHAT_CONTEXT_WINDOW_TOKENS` | 16384 |
| `CHAT_OUTPUT_TOKEN_RESERVE` | 2048 |

These are adjustable engineering defaults, not a final product decision about message count. Set the context window to the actual provider/model capability. Input selection reserves estimated system/current RAG tokens, the configured output allowance, and a 256-token safety margin. Oversized current sources/question produce a recoverable error rather than silently discarding source evidence. Token estimates use LangChain's local approximate counter, avoiding a network request to count tokens; they are not exact tokenizer guarantees. The output reserve budgets input space and does not itself configure a provider completion limit. Future model-specific counting or summaries can replace the policy without changing history records.

## Verification

- Full backend regression: 247 passing checks; final chat/provider checks: 25 passing, including three additional history-reader/input-budget tests (250 distinct backend tests verified across these runs).
- Full Chromium regression against compiled assets: 35 passing checks. Final focused history suite: 7 passing, including the 200-message window and delayed completion/deletion race (37 distinct browser tests verified across these runs).
- Alembic upgrade/downgrade and no-drift checks preserve existing identity/profile tables.
- Theme checks and TypeScript/Vite production builds pass.
- Backend and frontend Docker images rebuilt. [Runtime report](chat-runtime-verification.json) records isolated production-image startup, provider calls, idempotency, restart persistence, owner isolation, deletion, and Nginx route/bundle checks.

Tests use explicitly configured disposable PostgreSQL schemas/databases and deterministic providers. The application database and deployed services are not modified by these checks. Docker startup applies the new migration through the existing `python -m app.db.migrate` entrypoint when the rebuilt backend is started.
