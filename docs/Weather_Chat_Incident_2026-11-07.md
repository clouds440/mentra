# Weather chat and source-panel incident — 2026-11-07

## Confirmed causes

The latest Islamabad weather conversation had one user row and one assistant row despite four attempts. A later typed formatting request was stored as `resume_instruction`, rather than as a user message. The frontend automatically attached `resume_from` after incomplete/paused responses; an extra semantic classifier routed related typed messages into resume, and resume intentionally rewrote the original assistant. This was a persistence/routing problem, not merely missing React bubbles. Normal sends now always create independent durable exchanges; only explicit Retry/Resume controls continue an existing turn. The automatic continuation classifier and its prompt/verification script were removed.

Weather search succeeded twice, but supplied short snippets (some with old indexing dates), not the daily forecast. The response correctly marked the required forecast task partial, but offered an unhelpful table with unverified placeholder conditions. The model had no tool to read returned pages. A live bounded read confirmed timeanddate returned403, while BBC and Met Office contained the daily values.

## Changes

- `web_read` reads only exact W tokens already admitted by this turn's search. No arbitrary model URLs. Existing HTTPS/DNS-pinned public transport, 4-second request bound, one executor attempt, three physical reads per invocation, bounded byte/token packets, explicit blocked-page outcomes and original citations apply. It is available after quick search closes and when explicitly retrying an older snippet-only checkpoint. Page text remains untrusted; retrieval time does not establish fact freshness.
- The web prompt directs the model to read a relevant source when snippets omit requested facts, verify dates/location/units, and avoid invented conditions and placeholder forecast rows. The shared reader preserves table columns.
- Normal typed follow-ups create new turns and preserve both earlier messages. Explicit retry/resume remain idempotent and separately tested.
- Source collection and chat catalog tabs have identity-based reuse keys. Existing entries, including entries in tab history, are focused and the panel reopened instead of duplicating tabs. Refocusing updates the content while retaining the entry identity/history.
- The website toolbar now has an icon-only Refresh page control alongside Back/Forward. It refetches preview checks and remounts the embedded page, or refetches Reader text in Reader mode. It adds no tab and cancels obsolete requests.

## Verification

- 110 backend tests passed across 11 modules: web reader/search, explicit response resume, streaming, chat endpoint, workflow guards, publisher preview, smart tools, prompt efficiency, search persistence and image network safety. An adjacent test's fake profile object was changed to a serializable Pydantic fixture; production checkpoint serialization remains strict.
- 12 compiled browser cases passed, through the complete side-panel run and the corrected existing toolbar-count assertion rerun. Includes normal typed follow-ups after partial failure and pause, preservation after reload, deduplication/focus/reopening, preview and Reader refresh, desktop/mobile panel behavior, source selection, pins and history.
- Frontend TypeScript and production Vite build passed.
- Real configured model/search smoke: expanded public request completed in9.399s with one search and two page reads, all seven daily highs/lows and BBC citation.
- Exact original public request, with no added reader hint, completed in8.582s with one search and one page read; native first-turn title and outcome handling returned `completed`, `retryable=false`, and seven forecast rows7–13November2026. These are two smoke samples, not a production latency percentile. Neither run included private learner context/history or performed writes to the user's conversation.

## Acceptance and limits

A normal Send must preserve the old exchange and save a distinct user/assistant pair, including after pause/partial failure and after reload. Retry/Resume may replace the selected earlier response only when explicitly invoked. Repeated source clicks must retain one matching tab, select it and reopen a hidden panel. Different source/message identities remain distinct. Refresh must reload the current page/Reader without adding tabs or changing chat content. Blocked/unsupported pages must return a bounded truthful failure, never fabricated forecasts. Public-source availability and model output can still vary; the fallback is a brief accurate gap with useful verified information.

The existing weather chat was inspected without rewriting or inventing its missing historical exchanges. The exact latest formatting instruction remains in its saved resume metadata; overwritten earlier assistant versions were not reconstructed.
