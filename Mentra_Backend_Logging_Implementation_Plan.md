# Backend workflow logging implementation plan

Status: implemented and verified, October 10, 2026. Runtime logging and module connections are implemented. Verification used isolated PostgreSQL and mocked providers; the application database has not been migrated or deployed.

Daily-file extension: API and workers now append JSON records to a shared `logs/backend/backend-YYYY-MM-DD.log` for each UTC day. Compose bind-mounts the host directory; OS locking protects complete records across processes and containers. Files remain until explicitly archived/deleted. File errors produce throttled structured terminal warnings and are retried without failing business operations. Four file-specific tests passed on Windows; all 22 file/workflow logging tests passed in Python 3.12 Docker. Two independent containers wrote 200 intact, unique large records into one shared host file. These changes require a rebuild/recreation before they run in existing containers.

Implementation results: 378 full backend tests passed; the final 18-test logging suite also passed, including the actual app startup/shutdown fixture added after full-suite discovery. The final Python 3.12 container run passed 30 logging/streaming/orchestration/assessment tests. Migration upgrade/downgrade, legacy-record preservation and schema drift checks passed. The local JSON-to-memory benchmark passed the stated overhead budget. See `docs/backend-logging.md`, `docs/backend-logging-coverage.md`, and `docs/logging-examples/` for usage, coverage and reproducible artifacts.

Resolved implementation details: contextlib managers automatically receive scope lifecycle logging; transaction ownership is declared explicitly to avoid falsely claiming a commit. Plain generators record invocation with a lazy-result marker. Dependency/legacy free text is normalized rather than guessed safe. Summaries bound operation/module/link storage and disclose overflow counts. Hidden SDK retries are not fabricated, and terminal sink latency remains dependent on the terminal.

## 1. Intended result

Every main backend workflow prints structured events as it progresses. A reader can identify the request or job, see each module and feature called, understand what it was asked to do, and see its result and duration. Completion prints an ordered summary of actual execution, including failures, fallbacks, and deferred jobs.

“Each step” means meaningful execution boundaries: authentication, validation, domain operations, orchestration decisions, tool dispatch, storage operations, external calls, durable job stages, and transaction outcomes. It does not mean every Python function or SQL statement. Connecting a module automatically instruments its public operations. Optional declarations add business semantics or internal stages; do not trace imports or patch unrelated third-party methods.

Extension requirement: a new backend service can connect to the shared logger once and receive operation logging and inclusion in request/workflow summaries immediately. Adding a new public method to a connected service must not require adding logging statements, per-method decorators, or editing a central list of known domains.

For every main workflow, maintain a coverage inventory mapping the route/job to its expected boundaries and verification scenario. Only actual execution appears in the visited-module list; planned but unused capabilities are reported separately when relevant.

## 2. Findings from the current backend

- `backend/app/core/logging.py` configures a root console handler and one shared `mentra` logger. Its timestamp has no explicit timezone, and messages have no standard request, operation, or outcome fields.
- `main.py` configures logging for the API. RAG worker startup also configures it, but assessment/evidence and event worker entry points do not consistently do so.
- Existing logs mostly cover startup, errors, RAG diagnostics, and ingestion stages. Authentication, profile, learner, memory, event, and notification operations lack consistent execution logs.
- `ConversationService.send` starts generation using `asyncio.create_task`; generation is shielded and can continue after the caller disconnects. HTTP lifecycle and generation lifecycle must therefore be separate.
- Conversation activity is already persisted and served through SSE. `ActivityPublisher` and `announced_tool` provide public progress, but are not a complete backend trace. Preserve that public contract and add separate terminal events.
- RAG ingestion/deletion, grading, chat evidence extraction, reminders, and reconciliation run outside the originating HTTP request. Context must survive durable handoff and retries.
- Domain services use synchronous SQLAlchemy and Starlette thread-pool calls. The reranker also uses a raw `ThreadPoolExecutor`, requiring explicit context propagation.
- `documents.worker` prints JSON to stdout, which `documents.isolation.read_isolated` parses. Adding console logs to that stdout would break extraction.
- Some failures are caught and converted to fallback results or durable failed states. A returned function or HTTP 200 is not sufficient evidence of business success.

## 3. Shared architecture

Use Python standard-library `logging`, `contextvars`, UTC datetime, and monotonic timing. No additional logging dependency or remote tracing service is required for this implementation.

Keep `core/logging.py` as the compatibility entry point for `configure_logging` and `logger`; split supporting code into `core/observability/`:

| Component | Responsibility |
| --- | --- |
| `context.py` | Trace/workflow context, IDs, nesting, sequence allocation, context cleanup and explicit propagation |
| `events.py` | Versioned event contract, allowed outcomes, bounded workflow summary collector |
| `registration.py` | One-time module connection, automatic public-operation wrappers, optional per-operation policies, duplicate-registration protection |
| `steps.py` | Shared sync/async span execution, optional internal stages and semantic outcome annotations |
| `formatters.py` | Human-readable terminal formatter and JSON-lines formatter using the same event data |
| `sanitization.py` | Safe metadata builders, field allowlists, length limits, exception formatting |
| `middleware.py` | Pure ASGI HTTP tracing, response lifecycle, headers, streaming/disconnect handling |

Domain services depend on this small shared API. The logging layer must not depend on domain services. Preserve original returns, exceptions, cancellation, transaction ordering, and frontend response schemas. Module identities are open strings derived from Python module/class names, not the closed module vocabulary in `langchain/planning.py`; adding logging support must not require changing the AI planner.

Configure logging once per process before meaningful initialization. Repeated app creation must not duplicate handlers. Give API, RAG worker, assessment/evidence worker, and event worker distinct `process_role` values. Include PID because several processes can share a terminal.

## 4. Event structure and timestamps

Every structured application event includes the common timestamp/severity/event/process fields below. Correlation and operation fields are present only where applicable: startup can have no request/trace, and a request start has no operation duration. JSON uses absent optional fields consistently rather than fabricated IDs or statuses.

| Field | Meaning |
| --- | --- |
| `schema_version` | Start at 1; version the event contract |
| `timestamp` | UTC ISO 8601 with milliseconds, for example `2026-10-10T09:12:44.381Z` |
| `level`, `event` | Severity and stable event name |
| `service`, `process_role`, `pid` | `mentra-backend` and emitting process identity |
| `trace_id` | Correlation across the initiating request and linked workflows/jobs |
| `request_id` | Current HTTP request identity; absent for independent workers |
| `origin_request_id` | Original request for deferred work, when available |
| `workflow_id`, `workflow` | One execution, such as a chat turn attempt or ingestion job attempt |
| `span_id`, `parent_span_id`, `sequence` | Unique operation, caller relationship, workflow event ordering |
| `module`, `operation`, `purpose` | Actual Python module, stable feature name, server-authored explanation |
| `execution_status`, `outcome`, `duration_ms` | Automatic invocation status, optional authoritative business outcome, and monotonic elapsed time |
| `input`, `result`, `error` | Small, explicitly approved metadata objects, when relevant |

HTTP events additionally include method, route template, HTTP status, transport outcome, and response duration. Jobs include job ID, attempt, and queue delay when enqueue time is known. Optional entity correlation includes conversation/turn/document/assessment/event IDs; omit learner identities unless operationally necessary.

Use monotonic clocks for durations; UTC wall-clock timestamps for human correlation. Sequence is workflow-local, not a global ordering across processes. Nested spans can overlap, so their durations must not be added to calculate total latency.

Stable event names: `request.started`, `request.response_started`, `request.completed`, `request.post_response_error`, `workflow.started`, `workflow.completed`, `step.started`, `step.completed`, `summary.part`, `job.enqueued`, `job.claimed`, `job.retry_scheduled`, `dependency.retry`, `transaction.committed`, `transaction.rolled_back`, `process.started`, and `process.stopped`.

Automatic `execution_status` is `returned`, `raised`, `cancelled`, or `timeout`. Terminal business outcomes, when known, are `success`, `rejected`, `failed`, `degraded`, `skipped`, `cancelled`, `timeout`, and `deferred`. For an unconfigured operation returning normally, show `execution_status=returned` and `outcome=unknown`; do not invent business success. Domain status is a separate field, for example `no_eligible_sources`, `already_applied`, or `grading_queued`. Enqueue success means durable acceptance, not finished processing. Existing main workflows receive semantic policies as part of this implementation.

## 5. HTTP tracing and lifecycle

1. Generate a server-owned request ID and trace ID at ingress. Return `X-Request-ID` and expose it through existing CORS configuration. External caller IDs, if needed, are validated length-bounded metadata; they never replace trusted internal identifiers.
2. Use pure ASGI middleware and never read/buffer request bodies or streamed responses for logging.
3. Use a small FastAPI subclass whose `build_middleware_stack()` returns the tracing ASGI middleware around `super().build_middleware_stack()`. This places tracing outside the framework's error handler, CORS and upload limiting while `create_app()` still returns a FastAPI instance with the original state, router, dependency overrides, OpenAPI and lifespan interfaces. Do not assign a live middleware stack or replace the application with a proxy. Verify this extension point against installed FastAPI/Starlette and Python 3.12 (Docker) as well as the local test runtime.
4. Bind the context before calling the app. At ingress route is `unresolved`; populate the route template after routing. For unmatched routes use a fixed unmatched label, not arbitrary raw URL paths. Do not log query strings or path parameters by default. Early rejections can retain unresolved route plus a fixed rejection category.
5. Observe `http.response.start` and final `http.response.body`; emit exactly one HTTP terminal event after the final body has been successfully passed to the ASGI server, or on exception/cancellation/disconnect when no complete body was sent. This measures application response delivery, not client receipt. Freeze its summary at that point. Do not infer success merely from response headers or emit a second terminal event if the framework re-raises afterward.
6. For SSE, report connection start/end, elapsed duration and terminal reason. Do not log tokens, SSE payloads, heartbeats, or every polling iteration. A stream ending is not proof that generation completed.
7. Exception handlers attach normalized error codes to tracing state and mark whether an unexpected exception has already been reported. The tracing boundary emits the one sanitized application error if not reported. Errors after response start retain the sent HTTP status and report a failed/incomplete transport outcome. A new, unreported error after a successfully sent final body emits `request.post_response_error`, linked to the closed request, without rewriting its completed summary. The framework re-raising the already reported exception that produced a 500 is not a new post-response error.
8. Reset context tokens in `finally`; verify cancellation and all early exits. Track HTTP body completion separately from any later application/background cleanup.

Retain normal request coverage at INFO. Successful health checks and frequent sync/status polling use DEBUG, while errors remain visible. A context-local verbosity policy applies to nested automatic operation events and ordinary application messages too, not just the request middleware. Requests on the fixed health/poll route set run at DEBUG; a failure/rejection promotes the terminal/error record and bounded summary to the appropriate visible level. Avoid buffering complete routine traces solely to decide later whether they succeeded.

## 6. Automatic module connection and operation instrumentation

### 6.1 One connection per service

Expose a module-aware facade through the existing logging entry point. Proposed usage, to be implemented:

```python
from app.core.logging import workflow_logger

@workflow_logger.connect_module()
class RecommendationService:
    def recommend(self, request):
        return self.repository.recommend(request)

    async def refresh(self, context_id):
        return await self.provider.refresh(context_id)
```

The connection derives identity from `RecommendationService.__module__` and its qualified name. It automatically wraps eligible public methods when the class is defined, including future public methods added to that class. Each invocation emits start/completion, operation name, approved input shape, duration, error classification and nesting. It contributes the module and operation to the active summary without a logging call in the method body.

Keep this an opt-in class registration decorator that returns the same class object and wraps its declared operation methods; do not substitute an object proxy or mutate unrelated service classes. This preserves normal construction, instance identity, `isinstance`, and internal `self.other_public_operation()` tracing. Protect wrappers with a marker so repeated registration and inherited wrapped methods do not produce duplicate spans. Register subclasses separately when they introduce or override operations.

By default register ordinary public instance methods and supported static/class methods. Skip constructors, private/dunder methods, properties, data descriptors, abstract placeholders and explicitly ignored methods. Inspect class dictionaries without invoking descriptors. Private helpers needing a visible stage can use an optional operation declaration. For inherited unwrapped methods, an explicit include policy installs a wrapped override on the connected subclass rather than modifying a shared base. Method replacement after registration requires reconnection; normal newly added source methods are detected on the next application load.

Use `functools.wraps` and preserved signatures/annotations. Sync functions remain sync; async functions remain async. Resolve postponed annotations against the original function's globals when exposing a signature to FastAPI or tool-schema inspection. Test dependency injection and tool schemas; do not assume `wraps` alone fixes forward-reference resolution.

Do not transparently guess lifecycle from an arbitrary returned object. Ordinary methods log invocation return. Declare `kind='contextmanager'` or `kind='asynccontextmanager'` for known context-manager operations; detect `contextlib` wrappers through their unwrapped generator functions and require this declaration or an explicit invocation-only opt-out. For transactions, start at enter and finish after the original manager's exit/commit/rollback, preserving exception suppression behavior exactly. Existing owner/profile/learner transaction boundaries must use this adapter.

Generator functions require an explicit lifecycle policy. For the initial implementation, use invocation-only tracing with a visible `lazy_result=true` flag unless a consumption adapter is required by a current workflow. A supported consumption adapter preserves iterator send/throw/close and async equivalents, records exhausted/closed/error states, and restores context on every yield to avoid leaking it into consumer code. Never keep a ContextVar token across consumption in different tasks/threads; reject unsupported cross-context consumption clearly. SSE transport stays with the ASGI tracer. Known unsupported operation descriptors fail registration with a clear error; deliberately skipped properties and ordinary class attributes are not registration errors.

For function-oriented modules, offer the same `connect_module()` API on an explicitly supplied collection of exported functions, returning wrapped callables which the module rebinds before consumers import them. A single-function variant is `@workflow_logger.operation()`. Avoid inspecting/replacing every callable in `sys.modules`; document that calls through references captured before registration cannot be intercepted. Register tools and graph nodes at their existing construction/dispatch boundaries so new tools/nodes inherit tracing there automatically.

### 6.2 What connection supplies automatically

- UTC timestamps, standard event structure, module/class/method identity, generated invocation span IDs, parent relationships and durations.
- Invocation start, normal return, raised error, cancellation and timeout events for supported operation types.
- Request/job correlation from the active context, with an independent root workflow when called directly without one.
- Requested feature name and declared parameter names, with fixed schema/type labels only. For `**kwargs`, report its presence/count, not caller-supplied key names. Omit `self`/`cls`. Do not introspect or serialize arbitrary values, call `repr`, read properties, or access content to guess metadata.
- Safe return type/schema label, execution status and optional declared outcome policy.
- Inclusion in ordered operations and visited-module summaries, including repeated/nested calls.
- Correlation on ordinary `logger.info/warning/error` messages inside the connected call, through the shared log-record filter.

No module must register HTTP IDs, format timestamps, maintain summary arrays, or manually emit routine start/end logs. Using `logging.getLogger` alone formats messages but cannot observe operations; `connect_module()` is the one-time connection that enables automatic execution tracing.

### 6.3 Optional local operation policies

Connection supports an optional dictionary of operation policies, kept with the service/module rather than in the logger core. Policies declare a stable feature name/purpose, safe input/result builders, semantic outcome resolver, log level or ignored operations. New methods without a policy still receive full automatic invocation tracing.

Code handling a failure can annotate the current span through a facade call such as `workflow_logger.set_outcome('degraded', code='RAG_UNAVAILABLE')`; alternatively its declared result resolver maps existing return statuses. Provider fallback is degraded; authorization refusal is rejected; an empty retrieval result is success with a domain status; a swallowed generation error is failed. Instrumentation cannot infer these from arbitrary returned objects. A normally returned call without a resolver is reported as returned with unknown business outcome, keeping the distinction visible in summaries.

Policy callbacks are synchronous, side-effect-free, bounded and restricted to explicitly selected schema fields. Their errors produce a sanitized instrumentation diagnostic and unknown metadata/outcome, never change the operation's return/exception. No network/DB reads or bulk serialization in metadata callbacks.

For a meaningful internal stage that is not a public operation, `with workflow_logger.step(...)` and its async form remain optional. Use explicit stages only for decisions, catches, transaction outcomes or substeps whose behavior cannot be observed at a connected method boundary.

Safe examples:

- RAG search: input mode, selected-document count, limit; result source/chunk counts, retrieval status, reranker fallback.
- Learner context: feature requested, context count, maximum concepts; result concept count and status.
- LLM call: registered prompt source/version, configured provider/model, round, tool count; result finish reason and usage counts if actually provided.
- Authentication: operation and authentication mechanism; result authenticated/rejected with a stable error code.
- Repository write: operation and entity ID; result committed, deduplicated, stale claim, or rolled back.
- Tool call: exact registered tool name and call ID, approved argument shape/counts; result outcome/counts. Do not serialize tool arguments or returned content.

Connect shared LLM, repository and provider adapters once. Instrument shared LLM calls once per actual provider invocation, including tool rounds and streaming completion; avoid both a wrapper and a manual span representing the same invocation. Log application-managed retries where observable. Do not invent events for retries hidden inside an SDK; either expose an available supported hook during implementation or report configured retry policy and final outcome.

Explicit dispatch instrumentation must also cover unknown tools and argument-validation failures before announced tool execution. Keep backend tracing independent of public activity so it works for stateless chat, direct APIs, workers, and executions without an activity sink.

## 7. Main workflow coverage

| Workflow | Required visible steps and outcomes | Main locations |
| --- | --- | --- |
| Registration, login, external login, identity, logout | Validation, credential/token verification, identity persistence, session issue/revoke; denial and duplicate outcomes | `auth/dependencies.py`, `auth/service.py`, auth repository/tokens, auth and eduverse routes/integration |
| Profile and onboarding calibration | Profile load/update, attempt creation, complete-answer validation, scoring, evidence write, AI evaluation/fallback, final transaction | `student_profile/service.py`, `calibration/service.py`, `evidence_service.py`, profile evaluator/repository |
| Persistent and stateless chat | Begin/deduplicate turn, load history, actual plan selection, profile/learner/RAG/history/memory context, attachment extraction, provider/tool rounds, references, response persistence, evidence enqueue | `chat/service.py`, `chat/generation.py`, `langchain/orchestration_service.py`, `history_orchestration.py`, tools, shared LLM, chat repositories |
| Conversations and SSE | List/sync/detail/edit/delete, reconnect/reset, stream completion/disconnect; no per-token events | Conversation routes/services/repositories and activity stream route |
| Materials ingestion, versioning, reindex, deletion | Upload acceptance, storage, durable enqueue, claim/resume, parse/OCR, chunk, embed, vector write/verification, fenced publication, retry/failure, cleanup | `rag/service.py`, `rag/worker.py`, processing/storage/repository, embedding/vector adapters, documents/vision services |
| Retrieval and source access | Scope/eligibility resolution, lexical/vector branches, fusion/window expansion, reranking/fallback, source hydration, result counts/status | RAG service, repository, Qdrant store, reranker, source routes |
| Attachments and document reading | Ownership/read, extraction/cache, format routing, isolated parser/OCR, timeout, context preparation, optional library import | `chat/attachments.py`, documents service/isolation/readers, vision provider |
| Learner operations | Context/concept resolution, evidence validation/deduplication, scoring and state persistence, recommendations, verification, misconception changes | Learner engine/services/repository and learning routes/tools |
| History and memory | Context budgeting, history lookup, memory admission/validation/recall, save/confirm/retire/delete, maintenance | History service/tools/repository, memory validation, maintenance CLI |
| Events and proposals | Timezone/temporal validation, admission, proposal create/decision, graph resume/checkpoint, event mutation, reminders queued/disabled, idempotent outcomes | Events/proposal services, event tools, confirmation graph/checkpointer, event repository |
| Notifications and reminders | Preferences, inbox/sync/read/dismiss, batch claim/due evaluation, publication and unique-ledger deduplication, commit/failure | Notifications service/repository, event worker and reminder transaction boundary |
| Assessments and evidence jobs | Generate/source retrieval/model validation, attempt submission, optional extraction/correction, grading claim/model call, evidence application, atomic completion, retry/stale claim | Assessments service/repository, assessment workflows/worker, chat evidence worker/repository |
| Lifecycle and maintenance | Configuration validation without values, DB initialization/migration, service initialization, readiness failures, reconciliation/maintenance counts, shutdown/cancel/close | Main lifespan, migration CLI, worker entry points, RAG reconciliation and memory maintenance |

Instrument repository boundaries at meaningful read/write/transaction granularity; SQL echo and bind values stay disabled. Emit commit success only after the transaction actually commits. Rolled-back or fenced-out work cannot appear as successful publication. Document reader/OCR routing must name the reader/provider actually used, not all possible formats.

## 8. Deferred work, retries, and correlation persistence

- Each detached chat generation owns a separate workflow context and summary collector. Carry immutable trace/origin IDs and entity IDs into it; never share the mutable HTTP collector. The request summary links the generation workflow whether pending or already completed.
- Provide shared workflow launch and job-envelope helpers used by existing dispatchers. A connected service called through these launchers inherits correlation automatically. Connecting a class alone cannot intercept arbitrary new `asyncio.create_task` calls or invent durable database propagation; new modules use these shared launch/enqueue helpers when introducing deferred work. Do not add per-domain trace handling or a custom queue abstraction solely for logging.
- Thread-pool boundaries preserve bound context; test actual Starlette propagation. For raw executor submissions use a fresh `copy_context()` per submitted callable. A workflow collector needs a lock for sequence and summary updates across threads; span nesting stays context-local.
- A timed-out executor call can continue in its thread. Close/freeze the request collector without waiting for it; late events retain correlation but carry `after_parent_completion=true` and cannot mutate an emitted summary. A snapshot may contain running steps at closure; report their state instead of fabricating completion. Detached background workflows always own their own collector.
- Persist a small versioned correlation envelope at durable enqueue: trace ID, origin request ID, origin workflow/span ID. Add a nullable `log_context` JSONB column to `rag_job`, `chat_turn`, `assessment_attempt`, and `chat_evidence_job`. Keep envelope fields bounded and versioned; no indexes, backfill, user-facing metadata, business fingerprint or idempotency-key changes are required. Repository methods obtain an immutable envelope from the shared logging context while enqueuing; callers need no new business parameters. Explicit response serializers exclude this column, including dict-based APIs. Malformed/unknown-version envelopes are ignored with a safe diagnostic and an independent trace.
- For assessment resubmissions/corrections, record the envelope for the newly accepted grading generation while leaving an idempotent replay's original envelope intact. For chat retries distinguish the new attempt from replaying an existing turn.
- On claim, create a fresh workflow ID per execution attempt with the stored trace/origin links. Retries keep trace/job identity, but receive new span/workflow IDs. Old rows without correlation start independent traces and mark origin unavailable.
- Reminder delivery occurs later by schedule: start a fresh batch trace, identify processed events and notification outcomes, and link event IDs. Do not hold an HTTP trace open until the reminder fires or force scheduled reminders into the creator's trace.
- Queue, claim, retry, and final completion logs must reflect durable outcomes. Logging errors cannot roll back domain writes or acknowledge an unfinished job.
- Migrate additively, rehearse on an isolated PostgreSQL database, and preserve existing ownership, fencing, uniqueness, and one-reminder invariants. No log-event tables are introduced.
- Apply the additive migration before deploying code that selects these columns; old binaries continue with nullable fields. Test new schema with old-style writes. Downgrade is permitted only after reverting dependent application code; never remove columns under running new workers. Use the existing migration command and locking protocol, not a new migration runner.

## 9. Completion summaries and terminal output

Print step events while execution runs, then a compact terminal block for each completed request/workflow. JSON mode emits one `request.completed` or `workflow.completed` object with a bounded summary; when size requires splitting, the terminal event carries a summary-part count and `summary.part` records carry the operation lists. There is still exactly one terminal event.

Summary contains root outcome, HTTP status separately when applicable, total duration, unique visited modules in first-entry order, and operations ordered by start sequence with span/parent IDs, execution statuses, known outcomes, safe result status, and duration. Repeated calls remain separate; mark recoverable failures, unresolved failures, skipped decisions, linked deferred workflows/jobs, and operations whose business outcome is unknown. Unknown semantics do not conceal normal return or exception status.

Resolve request outcome from explicit workflow results: HTTP 200 with a failed durable chat turn cannot be labeled workflow success; expected no-results is not a failure. A recovered dependency failure makes the root degraded when a fallback materially changes the result. The final workflow owner reports the authoritative outcome after persistence.

Separate result ownership from simple worst-child aggregation: a handled child failure does not automatically make the parent failed. The operation's policy/explicit annotation determines whether it recovered successfully, degraded, or failed. Unannotated parents retain unknown business outcome; HTTP transport status remains independently visible.

For child workflows completing in the same process before the request closes, register an immutable bounded child-summary snapshot with the parent. The request summary includes those child modules/operations grouped by workflow with their own sequence, and origin links preserve causality; do not claim a total cross-workflow order from workflow-local sequence numbers. Pending children appear as links with pending state. Child completion after closure updates only the child's final log, not the frozen parent. A replay/status request may link an existing turn/job without pretending that it executed the job's modules. Jobs in other processes produce their own correlated summaries; no distributed trace aggregation service is implied.

Every collector has a single close transition under its lock. Start/completion events allocate event sequence separately from an operation's fixed `start_sequence`, used for ordered summaries. Bound operation entries, child snapshots/links, unique module names and aggregate buckets; fixed limits for links/modules/buckets are 100 each with overflow counters. This prevents nominal step limits from leaving other collector collections unbounded.

Illustrative output only (short IDs for readability):

```text
2026-10-10T09:12:44.381Z INFO  request.started trace=tr1 request=r1 method=POST route=/api/v1/conversations/turns
2026-10-10T09:12:44.388Z INFO  step.started trace=tr1 workflow=w1 span=s1 module=app.auth.dependencies operation=authenticate purpose="Verify caller session"
2026-10-10T09:12:44.394Z INFO  step.completed trace=tr1 workflow=w1 span=s1 outcome=success duration_ms=6.0
2026-10-10T09:12:44.421Z INFO  workflow.started trace=tr1 workflow=w2 workflow_name=chat.generate turn_id=t1 attempt=1
2026-10-10T09:12:44.424Z INFO  step.started trace=tr1 workflow=w2 span=s2 module=app.rag.service operation=search input={mode:STANDARD,selected_document_count:2}
2026-10-10T09:12:44.507Z INFO  step.completed trace=tr1 workflow=w2 span=s2 outcome=success result={retrieval_status:ready,chunk_count:6} duration_ms=83.0
...
2026-10-10T09:12:46.120Z INFO  workflow.completed trace=tr1 workflow=w2 outcome=success duration_ms=1699.0
  modules: chat.service -> langchain.orchestration_service -> rag.service -> learner.engine -> langchain.llm -> chat.repositories.postgres
  operations: load_context=success; search=success; get_relevant_context=success; provider.chat=success; persist_response=success
2026-10-10T09:12:46.126Z INFO  request.completed trace=tr1 request=r1 status_code=200 outcome=success duration_ms=1745.0 linked_workflows=[w2]
```

The real summary includes all executed instrumented steps, not the abbreviated example. Concurrent traces may interleave in a shared terminal; correlation IDs, sequence, and parent links make them reconstructable. Within one process, render a summary block through one logging record to reduce interleaving.

## 10. Data policy, bounds, and output configuration

Use explicit allowlists for input/result metadata, then a shared sanitizer as defense in depth. Never capture arbitrary function arguments, request/response bodies, prompts, messages, tool arguments, extracted text, grades/answers, passwords, auth headers/cookies/tokens, connection URLs, keys, or provider payloads. Record the feature requested and operational metadata rather than copying user content.

Unexpected errors include exception type, stable code if known, and useful stack frame locations. Omit exception message text, source-code lines, locals, and raw cause content by default; a regex cannot reliably sanitize arbitrary private content. Expected domain failures log declared stable codes without private user-facing details. Audit existing application messages and replace unsafe payload interpolation (including full RAG diagnostics) with safe structured builders. Ordinary correlation filters do not make arbitrary `logger.info(user_content)` safe.

Configure one controlled handler path, removing/neutralizing known third-party console handlers to prevent output bypass. Provider/network/SQL free-text messages are suppressed by default; emit safe dependency summaries through connected adapters. For third-party/Uvicorn errors retain only normalized logger identity, severity, exception type and frame locations unless a fixed approved lifecycle template is used. Application DEBUG must not enable arbitrary provider body/header logging. Dependencies that directly print outside logging remain a documented boundary; audit known startup/model-loading output and preserve parser stdout as described below.

Initial configuration:

- `LOG_LEVEL=INFO` for Mentra application events.
- `LOG_FORMAT=console` in development, `json` in production; both explicitly selectable.
- `LOG_WORKFLOW_SUMMARIES=true`.
- `LOG_SUMMARY_MAX_STEPS=500`; cap each collector's combined own/child summary operation entries. All individual step events still emit at their configured level. If exceeded, show `summary_truncated=true`, dropped summary count, and bounded aggregate module/outcome totals. Never imply a truncated summary lists every call.
- `LOG_EVENT_MAX_BYTES=32768`; bounded metadata and safe truncation flags keep output predictable. Split large summaries into numbered correlated parts rather than silently cutting valid JSON or operation lists.
- `LOG_HEALTH_REQUESTS=false`, `LOG_POLL_REQUESTS=false` suppress successful routine traffic at INFO; DEBUG enables inspection. Failures bypass suppression.

Use one console stream per normal application process, initially stdout with immediate normal handler emission. Unify Uvicorn lifecycle/error formatting and disable redundant access output through `--no-access-log` in Docker and documented local launch commands. Framework re-raises may still reach Uvicorn after the application error was reported: a handler filter uses a bounded thread-safe TTL cache of reported exception identities to suppress the duplicate only, while preserving the re-raise and TestClient behavior. An unreported server error must remain visible. The cache expires promptly and is capped at 1024 entries; test duplication without altering exceptions or setting attributes on arbitrary exception objects.

Parser subprocess stdout stays its JSON protocol. Emit parser lifecycle events in the parent; any child diagnostics use sanitized stderr and are forwarded selectively by the parent. Never blindly forward captured stderr or parsed document output.

Start with synchronous bounded event formatting and a stream handler, matching current operation. Measure overhead before introducing asynchronous queues. If terminal backpressure proves material, a later bounded QueueHandler design must capture context before enqueue, report dropped events, define shutdown flushing, and preserve terminal/failure event delivery as far as the sink permits.

Logging must fail safely: formatter/sink failures cannot alter request/job results. Report a minimal sanitized fallback diagnostic where possible. Terminal logs remain operational diagnostics, not an exactly-once audit ledger; process crashes or a broken output sink can prevent a final event.

Workers use the same formats. To view the complete system in one terminal use `docker compose logs -f backend rag-worker assessment-worker events-worker`; API terminal alone cannot show another container's stdout. Update README launch instructions accordingly.

## 11. Implementation order

1. **Shared contract and automatic connection:** context/events/registration/formatting/sanitization/span helpers, compatibility facade, validated settings, console/JSON fixtures, idempotent configuration; prove a previously unknown connected module works with no central edits or per-method log statements.
2. **HTTP lifecycle:** middleware placement, request header/CORS, exception integration, SSE and disconnect semantics, Uvicorn setup; authenticate and route-to-domain boundaries.
3. **Chat and shared dependencies:** connect services/adapters once, add semantic policies and necessary internal stages for persistent/stateless chat, detached generation, orchestration, tools/graph nodes, LLM, context retrieval, response persistence and attachments/document/OCR. Produce complete sample traces.
4. **Durable context and workers:** additive correlation migration/enqueue/claim changes; RAG ingestion/reconciliation, grading/evidence, reminder and lifecycle initialization. Rehearse migration and legacy-row behavior.
5. **Remaining domains:** connect auth/profile/calibration, learner, history/memory, events/proposals/checkpoints, notifications, assessment APIs, CRUD/read boundaries and maintenance; declare safe metadata/outcomes locally. Complete the coverage inventory and document the one-connection recipe for future modules.
6. **Acceptance and documentation:** capture representative console/JSON runs, measure overhead, verify privacy/limits, complete affected regression suites, document event contract/settings and combined terminal commands.

Each phase has concrete verification below. Infrastructure alone is not completion; all listed main workflows must be instrumented and demonstrated.

## 12. Verification and acceptance

Add targeted unit/ASGI tests and extend existing domain tests; do not make real AI calls to verify logging.

- Timestamps include UTC and milliseconds; JSON parses, console shows required correlation, and monotonic durations remain correct under wall-clock changes.
- Nested sync/async steps retain parentage and start order; simultaneous requests, thread-pool/executor work, cancelled tasks, and detached chat cannot leak or share mutable collectors.
- Define a test-only module unknown to the logger and planner, connect it once, and invoke multiple sync/async public methods plus a nested public method: each logs automatically and appears in the summary. A newly defined additional method requires no logging policy to emit events. Verify optional policies, unknown outcomes, skipped private methods/properties, supported static/class methods, subclass overrides, preserved signatures/identity, direct standalone invocation, and repeated connection without duplicate spans.
- Verify generator/context-manager lifecycle where supported, clear registration errors for unsupported boundaries, and that a metadata/outcome resolver failure cannot affect business execution. Check ordinary application log messages inherit active correlation and that dynamic dispatch can call a newly connected module without a central allowlist change.
- Exactly one terminal event per lifecycle across 2xx, 4xx, 500, validation/auth failures, preflight, 413, SSE normal close, disconnect, cancellation, and errors after response start. Verify HTTP body completion timing without delaying or buffering streaming.
- Verify FastAPI instance/state/lifespan/OpenAPI/dependency overrides, deferred annotations and tool schemas still work after registration/middleware integration on supported runtimes. Verify post-body errors yield a separate error event, not a second completed event, and Uvicorn filtering preserves unrelated server failures.
- Tool argument refusal, unknown tool, provider timeout, handled RAG/reranker fallback, no-source results, swallowed chat failure, and profile evaluation fallback report correct semantic outcomes.
- Request and final workflow summaries list the operations actually visited, repeated tool/provider calls, durations, fallback/error codes, and linked pending jobs.
- Persisted correlation survives enqueue/claim across distinct processes, retries, restart and legacy rows; replay does not overwrite original correlation or change idempotency fingerprints. Stale/fenced claims never report committed success.
- Domain transaction failures log rollback; log-write failure does not change commit, retry, reminder ledger, evidence, or chat behavior.
- Parser stdout remains valid JSON and parent extraction still works for successful parsing, malformed result, OCR failure and timeout. Document content and raw stderr do not enter logs.
- Canary secrets/private content are absent from both formats, exception chains and third-party output. Long strings/control characters cannot inject terminal lines or corrupt JSON.
- Summary limits, multipart JSON summaries, repeated configuration, repeated app startup, worker startup/shutdown, polling suppression and duplicate access/error handling behave as specified.
- Verify completed child workflows appear in a request's grouped summary, pending/replayed work is linked honestly, late thread completions cannot mutate snapshots, and module/link/aggregate limits hold under concurrent overflow. Confirm poll verbosity applies to nested spans and still exposes failures.
- Run existing affected auth, student-profile, persistent/stateless chat, streaming, orchestration, RAG workflow/API, document/OCR, learner, history, event/proposal, notifications, assessment/evidence, and migration tests against the appropriate isolated database.
- Compare logging enabled versus a no-op sink on representative mocked non-LLM workflows, including concurrency. Initial budget: median and p95 increase at most 5% or 2 ms, whichever is larger, on the same controlled host; document measurement conditions. Measure slow-terminal behavior separately because terminal I/O is not bounded latency.

Completion requires a reviewable trace for each coverage row, verified migration, passing targeted/regression checks, and documented terminal commands. No frontend logging UI, file retention service, or external telemetry platform is required.

## 13. Technical references

- Python's [Logging Cookbook](https://docs.python.org/3.10/howto/logging-cookbook.html) describes context-local metadata and logging handlers; use the same concepts with the project's installed Python version.
- Starlette's [middleware documentation](https://www.starlette.io/middleware/) describes pure ASGI middleware, middleware ordering, and `BaseHTTPMiddleware` context propagation limitations. Validate against the installed FastAPI/Starlette versions during implementation.

## 14. Reviewed decisions for implementation

Adopt standard-library logging; one-time module connection with automatic public-operation tracing; optional local semantic policies/internal stages; UTC timestamps; console development output with JSON production output; complete actual-operation summaries within stated bounds; server-owned request/trace IDs; shared launch/enqueue propagation and durable correlation for queued user work; independent scheduled reminder traces; safe input/result metadata; and separate HTTP/generation/job lifecycles.

The implementation status and verification evidence are recorded at the top of this document. Deployment requires applying the additive migration before starting the new code; isolated verification did not change the application database.
