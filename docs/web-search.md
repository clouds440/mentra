# Web search

Mentra exposes one optional LLM tool: `web_search(query, website?)`. The backend connects directly to [You.com's hosted free MCP](https://you.com/docs/agents/mcp-server) at `https://api.you.com/mcp?profile=free&tools=you-search`. No You.com account, API key, OAuth or payment method is needed for this free profile. There is no paid fallback. You.com currently advertises 100 queries per day; its quota identity/reset semantics are not guaranteed by Mentra.

## Configuration and enablement

The supported backend runtime is Python 3.12 (the existing Docker image). The official SDK is pinned to `mcp==2.3.0`, with `httpx2==2.13.1` and compatible `sse-starlette==3.0.3`. The SDK requires the Uvicorn pin to move from 0.30.6 to 0.31.1; existing FastAPI and LangChain pins are retained. These dependencies resolved together and `pip check` passed in the actual backend runtime. The SDK's Python 3.14 dependency constraints differ; use Python 3.12 for native backend installation too.

Run the additive Alembic migration through `python -m app.db.migrate` before starting the backend. Configure:

```dotenv
WEB_SEARCH_ENABLED=true
WEB_SEARCH_TIMEZONE=Asia/Karachi
WEB_SEARCH_DAILY_LIMIT=90
WEB_SEARCH_USER_DAILY_LIMIT=10
WEB_SEARCH_USER_MINUTE_LIMIT=3
WEB_SEARCH_CACHE_SECONDS=120
```

Timezone must be an IANA name. Defaults keep search disabled until explicitly enabled. Native and Compose use the same settings; the frontend has no provider secrets or search endpoint configuration. Rebuild/recreate the backend to install the new dependencies and apply changed environment settings; rebuild the frontend for the new rendering components. Startup/readiness do not perform searches or consume allowance. Disable the flag to stop new searches while old saved citations remain readable. Normal rollback retains usage and chat metadata.

## Ownership and contracts

`app.web_search` owns search I/O, public URL/hostname validation, provenance normalization, typed outcomes and operational persistence. `app.langchain.web_tools` owns the model schema, dated reuse, budget fitting and staged W references. Orchestration injects the service independently of history and RAG. Stateless chat can search through an ephemeral runtime without acquiring fabricated history/memory write authority.

The LLM receives the versioned `WEB_SEARCH` prompt: search only for necessary additional/current knowledge or an explicit search/verification request, honor no-web instructions and user website scope, omit private material from queries, and treat every snippet as untrusted evidence. Prompts guide model judgment; they do not guarantee perfect decisions.

Website accepts a public hostname or HTTP URL and keeps subdomain specificity. Reject IPs, credentials, explicit ports, private/reserved hosts, conflicting/negative/boolean site operators and invalid URLs. Host inclusion uses the provider override and every result is filtered again with exact-host or dot-delimited subdomain matching. Restricted empty results never broaden scope. The module never fetches a model-selected page directly.

The fixed free search operation uses snippets (`extraction=none`), count 5 per provider section and at most 5 normalized sources overall. SDK initialize/initialized, bounded tools/list contract discovery and tools/call contexts enter and close in the same task. No automatic tools/call retry, sampling, elicitation, credentials, redirects or paid extraction. Bound decoded transport bytes and SSE events to 512 KiB and contract metadata to 64 KiB. Discovery has a one-hour cache and a one-minute cooldown after three failures.

## Dates, citations and activity

Every returned outcome includes `current_date`, `current_datetime`, `reference_timezone` and `delivered_at`; attempted retrieval has `searched_at`. Source publication/update/data-as-of are distinct optional fields. The current You.com adapter maps its documented `page_age` publication field. Unprovided update/data-as-of/fetch dates remain null. Invalid/missing/future dates are explicit. Naive provider timestamps retain their date/raw value and a timezone warning rather than a fabricated UTC instant. No date inference from titles or URLs.

Successful admitted evidence receives message-local W tokens. The final response persists `web_sources`, `web_citations` and `web_searches` in existing canonical chat metadata. Unknown tokens, escaped markers, code and existing Markdown links do not become web citations. Prior assistant W markers are renamed only in prompt projections so a new W1 cannot be confused with old evidence. Source registries are committed only after the exact JSON result fits the shared result budget; rejected packets cannot create orphan citations.

The existing attempt-fenced activity stream announces search before provider I/O. A website-restricted search shows the requested domain while running; an unrestricted search names You.com until result domains are known. Completed updates show up to five distinct result websites. These are consulted sources, not a claim that Mentra directly crawled every website. No raw query/snippets enter activity or logs.

Frontend `WebCitation`, `WebCitations` and `WebsiteIcon` render safe new-tab links, accessible names, cited/consulted labels, source/search dates and optional favicons. Favicons use each validated HTTPS origin's `/favicon.ico`, anonymous requests and no referrer. Missing, blocked or CORS-restricted icons fall back to a globe; no icon aggregator receives search terms. Activity and citations reuse the same identity component. Publication dates render as civil dates without timezone shifts. Old messages lacking web fields continue to render.

## Bounded caching, quota and recovery

Completed source-bearing searches are cached across turns and workers in PostgreSQL for **120 seconds**, with a fixed global maximum of **128 entries**, **32 KiB per payload**, and oldest-entry eviction. Matching uses a digest of canonical query, exact website, authenticated owner and current reference date; raw queries are not stored. Cache reads enforce owner and expiry. Midnight/date changes miss the cache. Expired entries are removed on writes; no background cache worker or growing server memory cache. `WEB_SEARCH_CACHE_SECONDS=0` disables caching; its maximum is 300 seconds. Explicit “fresh search”, “search again”, “recheck” or “don't use the cache” requests bypass cross-turn cache. Failures and empty results are not cached across turns.

Cache hits spend no provider quota, refresh the current clock and keep original `searched_at`/source dates. `cache_hit`/`cache_expires_at` are returned to the model and cached-result use appears in activity and the source UI. In-turn identical results are also reused, including bounded failure receipts, without redispatch; `reused_within_turn` distinguishes this from cross-turn caching. Owner-scoped caching avoids exposing one account's query/result context to another.

Rolling PostgreSQL limits default to 90 deployment calls/24h, 10 owner calls/24h and 3 owner calls/minute. Admission acquires the existing chat owner lock, then a provider guard. Reservations, sent calls and unknown outcomes remain charged; only a proven unsent reservation can be released. Deterministic attempt/query operation IDs prevent an ambiguous retry from redispatching the same operation. This is conservative admission, not an exactly-once remote guarantee. Owner deletion anonymizes charged usage without refunding global allowance; owned cached results are deleted. Cache eviction never refunds usage.

SQL never spans provider/model I/O. Admission/query waits are bounded, cancellation reconciles pending threadpool reservations, and old operational rows are cleaned lazily in bounded batches. Two local search requests can run concurrently; queue wait is at most one second. Each call has a 20-second deadline within the shared workflow deadline, preserves final-answer time, and never refreshes the parent 150-second clock. Per turn: two searches, shared six tool calls/two writes, 1200-token/4800-byte search packets within the shared 3200-token/12800-byte packet budget. Account for Unicode with the existing conservative offline-tokenizer policy. Only complete JSON packets are admitted.

Search results never automatically write learner mastery, user memory, assessments or Library material. Logs contain outcome/count/latency/error classes only, never queries, snippets, URLs or raw MCP errors. Cache read/write failures leave caching optional and preserve a valid search result; quota admission failures stop provider dispatch and return a dated unavailable receipt. Cached partial results retain their original reason. These failures do not prevent a useful stable answer.

## Verification

The explicit live check is `python -m testing.web_search_probe`; it never runs in startup or normal test suites. A keyless SDK search succeeded on 2026-10-11 for `Python latest release` restricted to `python.org`, returning five sources on `www.python.org`, `devguide.python.org` and `blog.python.org`, including provider publication dates and missing dates. This verifies free retrieval with snippets; highlight extraction is not enabled.

Focused tests: `python -m unittest tests.test_web_search tests.test_web_search_persistence tests.test_tool_recovery tests.test_orchestration tests.test_persistent_chat`. Persistence tests require explicit dedicated `TEST_DATABASE_URL` and isolated migrated schemas. `npm run test:e2e -- web-search.spec.ts orchestration.spec.ts` exercises real auth/chat/quota storage with deterministic external model/search doubles. `npm run build` and `npm run check:theme` verify the frontend. Live provider success and fixture/browser checks are separate evidence from the local application rollout described below.

Final verification on 2026-10-11: 97 affected backend checks passed in Python 3.12 against dedicated PostgreSQL, including SDK contracts, cache expiry/capacity, quotas, migration round trips, canonical chat and recovery. The 507-test broad run found a service persistence import violating the architecture boundary and a historical Events migration snapshot including newly added tables; both were corrected and their checks included in the passing focused run. The two affected browser scenarios passed, including mobile citations, successful/failed favicon loading, canonical reload and repeated-query cache reuse. Production frontend build and theme checks passed. A final live keyless search negotiated MCP `2025-11-25` and returned five in-scope sources. Local rollout completed: rebuilt backend/frontend images, recreated all five application services, and enabled keyless search with Asia/Karachi temporal context and a 120-second cache. Startup applied revision `20261011_0017`; learner and chat-message counts remained unchanged (one each). All five services were running; backend and frontend were healthy and returned HTTP 200. The same 97 affected checks passed in the rebuilt production backend image, and `pip check` passed. The collapsed desktop account drawer was visually verified at 280px, with expanded/mobile drawers matching their capsule. Sidebar branding now uses capitalized Mentra and the empty-chat accent color.

## Additional You.com capabilities (discussion only)

Reviewed the [You.com onboarding guidance](https://you.com/SKILL.md), [API comparison](https://you.com/docs/choose-the-right-api), [MCP contract](https://you.com/docs/agents/mcp-server) and [pricing](https://us-west-2.you.com/pricing) on 2026-10-11. The onboarding document configures a developer's agent host; it does not need to be installed in order for Mentra's backend integration to work.

| Capability | Potential Mentra use | Recommendation |
| --- | --- | --- |
| Search | Current external evidence that Mentra's own LLM explains and cites | Implemented through keyless free MCP |
| Contents | Read a specific public article, documentation page or search source when snippets cannot support the answer | Most useful next addition; separate bounded URL-read capability |
| Answer | A provider-written answer from one search pass | Optional benchmark; Mentra already owns tutoring and synthesis, so treat any returned answer as external evidence |
| Research | Multi-source comparisons, literature surveys and explicitly requested research reports | Separate user-requested workflow with effort/cost limits and background execution for long tiers |
| Finance Research | Financial coursework and sourced company/filing case studies | Add only for a concrete finance-learning requirement; no automatic personalized advice workflow |

The free MCP profile includes search/discovery only, with 100 queries/day. An API key can authenticate the same MCP server using Bearer authorization; key authentication and MCP are compatible. Authenticated contents/research/finance require a profile and allowlist permitting those tools. There is no `you-answer` MCP tool; Answer uses REST. Current implementation deliberately strips credentials and fixes the free profile, so supplying a key alone does not enable authenticated usage.

Stay on free MCP for this initial module. For production capacity or Contents, introduce an explicitly configured authenticated provider mode behind the existing public facade, retaining cache/date/citation contracts. Keep the key in backend secrets, set spend/usage limits, and stop when credits are unavailable rather than silently purchasing more or changing modes. A fallback consuming account credits must be explicitly enabled.

Current public pricing advertises $100 signup credit (20,000 plain searches at $5/1,000), rather than the earlier $10 offer. An actual $10 account grant would cover approximately 2,000 plain searches. Verify the account's awarded balance and any grant terms in its dashboard; credits are a finite balance, not the recurring free MCP allowance. Contents, extraction and research consume that balance too. These additional capabilities and authenticated mode are proposed, not implemented or activated.
