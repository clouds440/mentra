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

## General completion and publisher-reader correction — 2026-11-07

The next real chat exposed a gap in the prior release. Its required answer task was completed, a supporting page read succeeded, and one other page returned403. The tool diagnostic correctly called that read optional, but the finalizer treated every receipt as required unless the model explicitly declared its optionality. That converted a fulfilled request to partial. Prompt instructions alone did not enforce the intended contract.

The shared server finalizer now determines required receipts against the complete declared deliverables. When all requested tasks are completed, an unreferenced read-only failure is incidental; the model does not have to enumerate every exploratory attempt as a separate optional task. Referenced required reads, explicit verification/source/count gaps, all writes and unknown effects remain blocking. Missing/unknown receipt references stay conservative. This policy applies to all read capabilities, rather than a weather or website exception. The same read-only projection corrects saved false-partial message and turn outcomes without rewriting answers or generating new replies.

The generic publisher reader also now supports bounded gzip/deflate decoding instead of rejecting all compressed responses. Both encoded and decoded input are capped at768KiB; a decompression-bomb regression verifies the cap. Main content takes precedence over unrelated article/sidebar fragments. Failures distinguish access denied, rate limit, not found, timeout, unsupported content and unreadable text. Only transient failures are retryable. Requests retain public HTTPS/DNS pinning, redirect checks, no cookies/authorization and fixed deadlines. The model receives a per-source read-result inventory and is instructed not to call unattempted sites unreadable. Weather-specific prompt wording was replaced with general evidence/date/source requirements.

Live six-publisher reads: BBC, Met Office, The Weather Network, AccuWeather and Python documentation returned readable text. Timeanddate returnedHTTP403. This is an access restriction, not evidence that all other publishers failed. Arbitrary server-blocked, login-only or client-rendered pages are not guaranteed readable; actual required evidence gaps must remain visible.

Validation:147 focused backend tests are covered by the146-test broad run plus the added retry-diagnostic test and final16-test reader/preview rerun. Two compiled browser cases verify completed answers have no unfinished/retry warning, including after reload, while actual required gaps retain the warning. Coverage includes unrelated read operations, blocked-first/successful-alternative coordination, explicit multi-source requirements, failed/uncertain writes, conservative saved projections, redirects, compression, malformed/nontext responses and input bounds. The actual saved chat projected from partial to completed for both message and turn, with Retry disabled and unchanged answer content; no history write was performed.

Real model evidence: the exact public weather formatting request reached completed in10.816s despite one HTTP403 read, recorded as optional. A temporary live-probe cleanup typo occurred after that result and cancelled its parallel documentation check; the documentation request was rerun separately with proper cleanup and passed in11.882s, using two searches and two official-page reads, with completed/nonretryable outcome. These are smoke measurements, not latency percentiles. Neither request included private learner context or wrote to the user's chat.

Acceptance: a blocked optional page must not mark a fulfilled answer unfinished. A specifically requested missing source, cross-check, required subtask or write must still prevent a completed status. The existing false warning must clear on reload without regenerating the answer. No publisher hostname, city or weather-specific completion rule selects the outcome.
