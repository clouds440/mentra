# History management and AI memory verification

Verified on 2026-10-08. All implementation phases are complete in the [tracker](../Mentra_History_Management_Implementation_Plan.md). See [operational documentation](history-management.md) for contracts, configuration and lifecycle policies.

## Application checks

Later regression evidence: the 2026-10-09 Events re-pass passed all **333 backend
tests** in the final rebuilt Python 3.12 verification image, including memory and
chat regressions after extracting their shared owner-lock boundary and adding
transactional event evidence detachment. See [Events verification](events.md#verification-and-deployment-boundary).
This does not replace the original browser/runtime evidence below or claim a new
application deployment; the dedicated test database was disposable.

- Full backend regression suite: **292 tests passed**. Subsequent focused verification after the final corrected-save retry fix: **68 tests passed**, including **42 history-management tests**. These counts overlap and should not be added together.
- Full Playwright regression suite against production-built frontend assets: **44 tests passed**, including seven memory scenarios, auth/profile, persistent chat, RAG and Markdown/Prism regressions.
- Frontend TypeScript/Vite build, semantic theme checks, backend compilation and whitespace validation passed. Vite retains an existing main-bundle size warning; memory settings and reference viewers load as separate lazy bundles.
- PostgreSQL migration upgrade, downgrade and metadata-drift checks passed on isolated databases, preserving existing canonical chat records. Existing chat search indexes build concurrently.
- Desktop and mobile memory Settings were visually inspected; theme behavior is also covered by the browser suite. All eight memory browser scenarios passed again after the final quota-error feedback fix, against production assets.

## Final rebuilt images

Both images built successfully. The final runtime harness recorded the actual running container image IDs:

| Image | Verified image ID |
| --- | --- |
| `mentra-backend:latest` | `sha256:f5ebbf8642d0040cc7dd8cc49b29c0efbb71c19632b94402a91649ac81750ffc` |
| `mentra-frontend:latest` | `sha256:07162c84161d35a8930bae27e9e53d158b495acd0b4fade0a4014422dfc78458` |

[Runtime evidence](history-runtime-verification.json) records nine successful checks: automatic migration/startup, actual ChatOpenAI tool binding and structured admission, history/memory recall with distinct references, restart/session persistence, account isolation, chat-deletion retention, revision conflicts/content purge, Nginx deep links/bundles, and browser manual CRUD against the rebuilt API.

The runtime uses disposable test databases and a deterministic local HTTP model provider. It validates integration and failure boundaries, not universal real-model semantic quality. Its browser proxy targets only the isolated API. Temporary runtime containers/databases are cleaned up by the harness. **The application database was not migrated and application containers were not deployed or restarted.**

## Performance and limits

[Measured performance](history-performance-verification.json) uses 10,000 messages in 200 conversations and 500 memories on dedicated local PostgreSQL 17. History expansion used two read SELECTs and the full-text index: cold 17.26 ms, warm median 8.31 ms, p95 11.09 ms. Lookup also sets a transaction-local two-second statement timeout. These local measurements are not production latency promises.

History responses are bounded to three windows/nine expanded messages, memory recall to five records, tool execution to six calls/two write proposals, and cumulative tool results to 3000 UTF-8 bytes. Repeated reads reuse turn-local results. Automatic admission caps, account capacity, evidence pruning, candidate maintenance, revision fencing and source suppression prevent unbounded accumulation or forgotten-memory resurrection.

Prompt token estimates retain the existing approximate strategy with protocol/output reserves. Lexical search is intentionally bounded and does not promise arbitrary semantic paraphrase recall. Inferred candidates require manual confirmation, and ambiguous/unavailable semantic verification saves nothing. These limits are documented implementation choices, not hidden guarantees.

## Memory-module re-pass

The re-pass fixed stale pagination/evidence responses, optimistic preference rollback and revision recovery, outdated conflict snapshots, conflict-edit dead ends, create-request idempotency after changed drafts, and actionable quota/duplicate error retention. The Add memory button no longer wraps; all binary frontend options use the shared accessible switch.

Backend fixes retire corrected claim/source hashes, distinguish manual assertions from inferred candidates, refresh manually corrected applicability, reject elapsed AI deadlines, anchor automatic freshness to the original user statement, and prevent retry receipts from reporting an obsolete save after manual correction. A new statement may reaffirm a current AI-origin fact; simply retrieving old evidence cannot renew it. The disable-during-validation test proves that the transactional preference check blocks in-flight AI writes while manual management and recall remain usable.

A rapid New chat navigation race discovered during browser verification could erase the first typed question. Draft resets now happen before the new workspace becomes interactive. Conflict corrections are reviewed and committed atomically without temporarily activating an incorrect statement.
