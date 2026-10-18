# Saved chat search

Search uses the canonical owned chat history; no parallel transcript store or model
call is involved. Open **Search saved chats** in the sidebar, enter a phrase and
open an exact matching exchange. Browser Back restores the phrase and search UI.

| Contract | Behavior |
| --- | --- |
| Search endpoint | `GET /api/v1/conversations/search?query=&offset=` |
| Matching | Case-insensitive literal substring in title or user/assistant message; all scripts supported; `%`, `_` and backslash are literal |
| Bounds | Query up to 200 characters; 20 hits per page, at most 200 results; refine the phrase beyond that cap |
| Title match | Latest eligible message represents the chat once unless it already matched by message |
| Result payload | Bounded SQL snippet, message ID, chat ID, title and timestamp; never entire transcripts |
| Exchange endpoint | `GET /api/v1/conversations/{cid}/messages/{mid}/window` |
| Exact exchange | Matching original message with at most one neighbor on each side, fetched in one authorized SQL snapshot |
| Access | Onboarded owner only, live chats only; both endpoints use private no-store responses |
| Timeout | Two-second search SQL timeout maps to retryable `CHAT_SEARCH_BUSY` |
| Index | Existing PostgreSQL trigram message index; separate title/message branches retain index opportunities |
| UI | 300ms debounce, aborted stale requests, pagination, local loading/error/empty states, keyboard focus and native dialogs |

The saved exchange is read-only and keeps old interactive actions out of the live
chat store. Continue chat returns to current history. Search words remain in the
browser URL for navigation; they are not included in the bundled Nginx access log.
External reverse proxies must apply their own equivalent query/referrer policy.
Do not log private query text during operational diagnostics.

Regression checks use synthetic histories, literal wildcard cases, owner isolation,
deleted chats, old messages outside the loaded live window, cancellation and mobile
Back navigation. The index-plan check uses 10,000 synthetic messages and normal
GIN maintenance; it is not a production load benchmark.
