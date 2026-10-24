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

Composite foreign keys enforce conversation ownership. The authenticated `learner_id` is the owner for Mentra accounts. No client-provided owner is accepted. Cookie mutation endpoints retain trusted-origin enforcement and onboarding requirements. Read-only bootstrap is permitted before onboarding so registration does not trigger a failing chat prefetch.

Owner-scoped locks serialize short writes and synchronization snapshots, never model/RAG network work. Every change and its revision commit in the same transaction. Revisions cannot commit out of order. The last 10,000 changes per owner are retained; an expired cursor requires a fresh bounded bootstrap. Deletion removes message/turn content while retaining a conversation tombstone for reconciliation.

## API

The shared owner lock is exposed by `app.db.owner_transactions.lock_owner` and
still locks the existing `chat_sync_state` row. Memory and Events join this boundary
without importing private chat methods or introducing an unrelated lock. Deleting
a conversation detaches both modules' evidence in the same transaction; saved
events remain available and receive their own sync revisions. See
[Events source-retention policy](events.md#structure-and-integration).

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

Send the current turn request contract, including the conversation/client-turn IDs, expected revision, content, retrieval selection and optional staged attachment IDs or structured interaction response. Do not send a client transcript. The server retrieves history. A successful send returns the affected turn's messages, not a transcript page. Retries use the same client turn UUID; a changed payload under the same UUID is rejected. Conversation edits and new turns require the expected revision. One running generation per conversation is allowed; other conversations are independent.

The user question is committed before inference. Assistant messages are appended after successful inference; failures retain the question. Generation runs in a shielded, tracked task with a 150-second deadline and a 180-second durable lease. Disconnecting an HTTP caller does not cancel the generation. Restarted processes expose expired attempts as recoverable failures; retries increment the attempt and fence out late results. A completed turn is replayed without another model call. Only the latest failed question can be retried without introducing conversation branches.

Provider execution is not exactly-once across process failure. Persistence is deduplicated and attempt-fenced; the model provider may still charge for an interrupted attempt.

The first user turn starts with a provisional title derived from its first line.
The AI is also asked to return a short, descriptive title in the learner's language
alongside its answer, using the Pydantic `NewChatReply` schema and the registered
`chat_title` prompt. Domain tools remain available before the final structured reply;
there is no separate title-generation model request. First-turn answer text is buffered
until validated and then sent through the activity stream; titles and output JSON never
appear as answer text. Later turns use the existing text-streaming path and do not
request another title. Providers without function calling are asked for equivalent JSON;
unstructured replies and invalid/missing titles retain the provisional title.

The generated title is persisted atomically with the first successful assistant answer,
under the existing owner/attempt locks and revision change feed. A manual rename while
generation is running, or a custom title before retry, is preserved. Retries can name
the first turn, while stale attempts and subsequent turns cannot rename the chat.
The frontend's normal mutation/recovery/sync responses update its sidebar and cache;
no database migration or separate frontend request is needed.

The old `/api/v1/chat` endpoint remains **deprecated and stateless** for existing integrations/tests. The frontend no longer uses or exports its full-transcript sender. Persistent clients must use `/conversations/turns`.

## Loading, caching and synchronization

`chatStore` is an external React store with separate list/conversation subscriptions. Authentication activates it once per owner/session restoration. Repeated auth identity checks do not repeat bootstrap. It hydrates cached summaries first, then makes a single-flight delta/bootstrap request. Initial summaries are bounded to 40; history is fetched when opening a conversation, with a latest page of 40. Reopening a loaded conversation displays memory immediately and reconciles previously loaded history pages against the database.

IndexedDB uses `idb` and separate conversation, immutable message, pending-send, deletion, and cursor stores. A cache transaction applies changed records and the synchronization cursor together. Existing message IDs are not rewritten. Successful sends cache only the new turn messages. IndexedDB remains bounded to 80 conversation summaries, 200 messages per conversation and 10,000 deletion fences. Session memory retains loaded conversations until account/session reset; rendering remains bounded separately. Pagination cursors account for disk eviction. Cache schema upgrades close older connections. Blocked storage falls back to memory and PostgreSQL.

The rendered window is capped at 200 messages. Older messages are loaded with sequence cursors and scroll-position preservation. When older paging drops the newest messages, Back to latest restores the latest page. Sending from such a window first restores latest history, preventing a gap in the displayed exchange.

Mutation responses append committed records immediately. BroadcastChannel signals other tabs; settled chat history synchronizes on these write notifications and when reopening a conversation. Idle timers and focus do not poll settled history. Unchanged messages are not rewritten. Revisits re-fetch the previously loaded history pages to repair cross-device gaps, while unseen older pages remain lazy. Recovery polling is bounded to accepted running turns. New provisional conversations avoid status/history requests before the first send is acknowledged, preventing a transient Conversation not found error.

Account transitions cancel stale requests, replace memory and close the old cache. Logout also deletes that account's IndexedDB cache and propagates through existing auth cross-tab signaling. A pending send is stored before HTTP transmission; unknown outcomes are checked before retry, and no offline question is automatically sent. Explicitly rejected questions can be restored to the composer. Deletion fences prevent delayed responses from resurrecting deleted cache records.

## LLM context

Stored/UI history and model input are independent. Recent messages, a private database summary and tool results are bounded separately; original user-facing content remains intact. Failed/stopped turns and historical attachment/source packets are not blindly re-injected. RAG prefetch remains private until the model requests retrieval.

| Configuration | Default |
| --- | --- |
| `CHAT_HISTORY_TOKEN_BUDGET` | 1800 |
| `CHAT_INPUT_TOKENS` | 8192 |
| `CHAT_RECOVERY_INPUT_TOKENS` | 12288 |
| `CHAT_CONTEXT_WINDOW_TOKENS` | 16384 (assessment workflow context) |
| `CHAT_OUTPUT_TOKEN_RESERVE` | 2048 |
| `CHAT_SUMMARY_ENABLED` | true |

There is no fixed number of turns: token capacity and complete exchange boundaries determine selection. `chat_summary` stores owner/chat-scoped incremental summaries and coverage watermarks. Every persistent request fetches the applicable summary; old attempts cannot see future coverage. Compaction runs after responses only when enough displaced history accumulates, with cross-process leases, no paid retry loop and failure cooldown. Summaries are historical background, not evidence or an instruction to recap unrelated topics.

Exact/keyword `history_lookup` can recover original messages and token-bounded continuations when detail is needed. The offline tokenizer (with conservative fallback) avoids request-time downloads. Output reserve is also enforced on provider completion. Oversized packets fail safely rather than silently discarding required evidence. See [compaction policy](../backend/app/chat/SUMMARIES.md) for thresholds, concurrency and rollback.

## Verification (original persistent-chat rollout)

- Full backend regression: 247 passing checks; final chat/provider checks: 25 passing, including three additional history-reader/input-budget tests (250 distinct backend tests verified across these runs).
- Full Chromium regression against compiled assets: 35 passing checks. Final focused history suite: 7 passing, including the 200-message window and delayed completion/deletion race (37 distinct browser tests verified across these runs).
- Alembic upgrade/downgrade and no-drift checks preserve existing identity/profile tables.
- Theme checks and TypeScript/Vite production builds pass.
- Backend and frontend Docker images rebuilt. [Runtime report](chat-runtime-verification.json) records isolated production-image startup, provider calls, idempotency, restart persistence, owner isolation, deletion, and Nginx route/bundle checks.

Tests use explicitly configured disposable PostgreSQL schemas/databases and deterministic providers. The application database and deployed services are not modified by these checks. Docker startup applies the new migration through the existing `python -m app.db.migrate` entrypoint when the rebuilt backend is started.

## Stopping and saved files

The composer replaces Send with Stop during a running turn. Stop fences the current attempt in an owner transaction before cancelling local work; a durable watcher cancels work owned by another backend process. Completed actions are not rolled back. A stopped notice remains in history, without creating learning evidence or entering later model context. Late completions cannot replace it.

Chat attachments retain their original bytes and extracted content in owner-scoped PostgreSQL records linked to the conversation. Reloaded message metadata restores the attachment cards. Raster previews load lazily through the authenticated original-source endpoint; document originals download without rendering active content. Deleting the conversation removes its chat attachments; a separate Library copy remains independently owned by Library. Unsent uploads expire after one day and storage remains capped at 100 MiB per owner and 25 MiB per file.

## Attachment and answer presentation

Files/images can be pasted or staged inside the composer before Send (four files, including up to three images). Preview cards sit above the text bubble; clicking opens an overlay with download/close actions. Add to library copies through the Library boundary. Transient loading is not shown as an unavailable-file error, and extraction status/filenames do not add another chat-card row. Vision-capable providers receive current images alongside the question; OCR is fallback.

Answers render with Markdown/Prism and a bounded top-to-bottom reveal, with a copy-as-plain-text action. Optional tool failures are returned to the agent for judgment; there is no deterministic Response limitations box.

## New exchange positioning

`useChatScroll` groups messages by their user exchange and anchors newly sent questions below the floating controls. Only the current exchange receives a viewport-sized minimum height: the answer consumes that room as it grows, with no appended tail spacer and no second jump on completion. Exchange groups remain stable so attachments and assessment controls are not remounted during a send. Manual scrolling takes precedence, restored chats use their actual content height and open at the bottom, and earlier-page loading retains its scroll position. The disclaimer sits at the bottom of the conversation region, above the composer.


## Unified files — 20 October 2026

Original uploads now use the shared [Files module](../backend/app/files/README.md). Configure the server-only `CLOUDINARY_URL`; all assets live under `mentra/<APP_ENV>/`. Run `python -m app.files.worker` for expiry/reconciliation/deletion. No persistent materials volume is required. Upload UI, source filenames, Library version history and authenticated previews/downloads remain unchanged.
