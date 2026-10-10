# Backend workflow logging

The backend emits UTC timestamps with millisecond precision, correlation IDs, module and operation names, execution/semantic status, safe metadata, and monotonic durations. HTTP requests and independent jobs each finish with a bounded execution summary. Console format is intended for the terminal; JSON format emits one valid JSON object per record.

## Running

Docker configuration passes logging settings to the API, RAG worker, event worker, and assessment/evidence worker. View their combined output:

```sh
docker compose logs -f backend rag-worker assessment-worker events-worker
```

The same events are also appended to `logs/backend/backend-YYYY-MM-DD.log` on the host. API and workers share **one file per UTC day**, including after a container restart or recreation. Files always contain JSON lines, regardless of terminal format; `process_role`, PID and correlation IDs identify the producer and request. The directory is bind-mounted at `/var/log/mentra` in all four backend containers. Logging uses an OS file lock to prevent concurrent records from interleaving. Daily files are retained until you archive or delete them; they are excluded from Git. No midnight restart is needed. A write failure prints a rate-limited terminal warning and retries on subsequent events without failing the request. Writes are flushed to the OS but are not a crash-proof audit ledger.

Local runs use `LOG_DIRECTORY=logs/backend` relative to the working directory; set an absolute path to have separately launched processes share the same directory. `LOG_FILE_ENABLED=false` disables file output. Rebuild/recreate the existing services to activate these changes.

### Why multiple Docker containers?

Compose groups this repository under the project `mentra` by default. Its default services are the frontend, backend API, and three backend workers: `rag-worker` handles document ingestion, `events-worker` handles event/reminder processing, and `assessment-worker` handles assessment grading and chat evidence. The API and workers connect to Supabase through `DATABASE_URL`. Local PostgreSQL is optional under the `local-db` profile and does not start by default. Separate workers can restart independently and keep long jobs from competing with HTTP request serving. Compose shows a flat list inside the project, rather than a nested backend subgroup.

Running only a frontend and backend container would require a process supervisor in the backend to manage the API and workers, and an external PostgreSQL instance. That is a deployment architecture change; the daily logger works with the existing services.

Local API (from `backend`, after migration):

```sh
python -m app.db.migrate
uvicorn app.main:app --no-access-log
```

Worker commands are `python -m app.rag.worker`, `python -m app.assessments.worker` and `python -m app.history_management.events.worker`. Workers have the same event format but separate process roles. API stdout cannot contain another process's stdout unless the logs are combined.

| Setting | Default | Purpose |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Application severity; DEBUG reveals routine polling |
| `LOG_FORMAT` | console in development, JSON in production; Compose defaults to console | Explicitly set `console` or `json` |
| `LOG_FILE_ENABLED` | true | Append the same events to daily JSON log files |
| `LOG_DIRECTORY` | `logs/backend` locally, `/var/log/mentra` in Compose | Daily file directory; Compose mounts host `./logs/backend` |
| `LOG_WORKFLOW_SUMMARIES` | true | Include final operations and module lists |
| `LOG_SUMMARY_MAX_STEPS` | 500 | Combined own/child operation summary cap |
| `LOG_EVENT_MAX_BYTES` | 32768 | Summary splitting budget, minimum 8192 |
| `LOG_HEALTH_REQUESTS` | false | Show successful health traffic at INFO |
| `LOG_POLL_REQUESTS` | false | Show successful sync/status traffic at INFO |

The API returns `X-Request-ID`, exposed through CORS. Caller-provided correlation headers do not override server-owned IDs. Request bodies, URL queries, arbitrary path parameters, credentials, prompts, source text, answers and tool arguments are not recorded. Free-text application/dependency logs are normalized; use structured events for meaningful new diagnostics.

## Connecting a new module

```python
from app.core.logging import workflow_logger

@workflow_logger.connect_module()
class NewService:
    def feature(self, request):
        return self.repository.feature(request)

    async def refresh(self, request):
        return await self.provider.refresh(request)
```

One connection traces all declared public sync/async methods, including new source methods on the next load. It keeps the original class and function signatures, traces nested public calls, and joins the active request/job automatically. No central list of domains or AI-planner changes are needed. The normal-return execution status is `returned`; without a declared business policy its outcome is `unknown`.

Add optional, local policies when the module has a meaningful return status or useful safe counts:

```python
@workflow_logger.connect_module(policies={
    'search': {
        'input': lambda args: {'limit': args['request'].limit},
        'result': lambda value: {'match_count': len(value.matches)},
        'outcome': lambda value: 'degraded' if value.used_fallback else 'success',
    },
})
class SearchService:
    ...
```

Policies must be bounded and side-effect-free: no DB/network reads or serialization of arbitrary values. Their failures do not change domain results. A caught failure can annotate its current operation with `workflow_logger.set_outcome('degraded', code='OPTIONAL_DEPENDENCY_UNAVAILABLE')`. This annotation takes precedence over a default outcome. Do not set `default_outcome='success'` when normal returns can hide unhandled business failures.

Properties, constructors, private/dunder methods and abstract placeholders are skipped. Static/class methods are supported. Register subclasses adding overrides separately; `include_inherited=True` wraps inherited functions on that subclass without modifying the base. Dynamic replacement requires reconnection. For free functions use `@workflow_logger.operation()` or `workflow_logger.connect_module()({'feature': feature})`, rebinding returned functions before consumers import them.

Known `contextlib` managers receive enter/exit scope spans automatically; policies can declare `kind='contextmanager'`, `kind='asynccontextmanager'` or `kind='scope'`. Declare contextmanager ownership for a transaction that actually commits; a generic or borrowed context only reports scope completion. Decorated generators with unknown lifecycle require a policy. Plain generators record invocation only with `lazy_result=true`; exhaustion and consumer work are not falsely reported as completed processing. SSE transport is traced by ASGI middleware without buffering or per-token logs.

## Background work

```python
task = workflow_logger.start_task(generate(), name='new-module.generate')
```

This creates an independent collector, links it to the caller before scheduling, and preserves immutable trace/origin IDs. Waited children appear as grouped completed summaries; pending children are linked. Once a response is passed to the ASGI server, its summary is frozen. Late completion, disconnect-surviving generation, and worker attempts emit their own final events.

For existing durable queues, persist `workflow_logger.envelope()` in the queue's dedicated internal correlation field in the enqueue transaction. On claim:

```python
with workflow_logger.workflow('new-module.job', log_context=job['log_context']) as run:
    process(job)
    run.outcome = 'success'  # after durable completion
```

Retries retain trace/job identity and create new workflow/span IDs. Legacy or malformed envelopes start independent traces. Raw executor work needs `copy_context().run`; ordinary Starlette/asyncio thread helpers preserve context. Connecting a class cannot intercept arbitrary new tasks or transport correlation across an uninstrumented queue.

## Summaries and interpretation

`execution_status` describes running/returned/raised/cancelled/timeout. `outcome` describes success/rejected/failed/degraded/skipped/cancelled/timeout/deferred/unknown. HTTP status and transport outcome are separate. In particular HTTP 202 means deferred, and persistent chat can report HTTP 200 with a failed turn.

Summary operation order uses `start_sequence` inside each workflow. Child workflows are grouped; sequence is not a global order across processes. Nested durations overlap. Transaction success is emitted after actual commit. Borrowed scopes report completion/staging rather than committing a transaction they do not own.

At limits, summaries disclose dropped/overflow counts; individual events remain available at the configured severity. Large summaries have one completion record and numbered `summary.part` records. Logging is operational diagnostics: sink failure or process crash can lose output; it is not an exactly-once audit ledger. Slow terminal or file writes can add latency.

## Migration and verification

Migration `20261010_0014` adds nullable internal `log_context` JSONB columns to RAG jobs, chat turns, assessment attempts and chat evidence jobs. Upgrade before running the new code. Existing rows require no backfill and the fields are excluded from public serializers and business fingerprints. Revert dependent code before downgrading the columns.

Focused tests live in `backend/tests/test_observability.py`. They cover new-module registration, nested calls, concurrency/thread propagation, cancellation (including before task execution), completed/pending child snapshots, late completion, transaction timing/rollback, metadata failures, privacy, ASGI streaming/disconnect/post-body errors, route/header/status behavior, summary limits, and real PostgreSQL correlation/migration preservation. Existing domain suites verify the connected workflows.

`backend/tests/test_log_files.py` verifies daily rollover, append after restart, concurrent large-record writes, configuration/disable behavior, and failure warning/recovery. Shared host-directory locking was also verified with two independent Docker containers producing 200 intact records in one file. The earlier JSON-to-memory benchmark excludes file I/O and lock contention.

Reproduce an isolated regression run with an explicitly dedicated `TEST_DATABASE_URL`:

```sh
python -m unittest discover -s backend/tests -t backend -q -b
```

`backend/scripts/verify_logging.py` creates safe console/JSON examples and a local mocked-workflow overhead measurement without contacting a model or application database.
