# Backend Engineering Standards

> **Build for the requirements we have, while leaving clean boundaries for the requirements we expect. Do not implement future features before they exist.**

These standards describe the current Python and FastAPI codebase. Update them when an important backend convention changes.

## Project structure

- `api/`: HTTP concerns only—request validation, dependency injection, calling application logic, and mapping results to HTTP responses. Keep handlers thin; organize endpoints in route modules and register them through the central router.
- `core/`: cross-cutting infrastructure such as centralized configuration, logging, and global exception handling. Do not make it a dumping ground for feature logic.
- `db/`: database connections, migration runner and shared owner transaction infrastructure. Feature tables and SQL remain in feature repositories.
- `schemas/`: shared API-boundary schemas only when they have multiple meaningful consumers. Feature-specific schemas should stay near their feature or route module rather than accumulating in a global catalogue.
- `services/`: application workflows and business logic. Add this boundary when a real workflow needs it; services should not depend unnecessarily on FastAPI request or response objects.
- `langchain/`: LLM orchestration, provider integrations, prompts, chains, agents, tools, and related educational orchestration.
- `rag/`: document ingestion and extraction, chunking, embeddings, vector retrieval, reranking, and related retrieval infrastructure.
- `learner/`: provider-independent learner domain contracts, policies, and persistence ports. Other modules, including LangChain, depend on the public facade and schemas in `app.learner`; they must not read learner tables or depend on persistence models.
- `student_profile/`: separate high-level student details, broad estimates, onboarding, controlled calibration, and repository ports. Its evidence must never write granular concept state. Explicit facts/preferences belong to the learner; only estimate contracts are writable by AI/policy.
- `integrations/`: small authenticated platform adapters. EduVerse provisioning verifies its signed subject against the supplied student ID and initializes a profile only once; no platform SDKs, passwords, or student schema changes.
- `chat/`: canonical conversations, durable generation attempts and bounded model-history selection. History retrieval must reuse these records.
- `history_management/`: on-demand history and user memory, with the separate provider-independent `events/` domain and `repositories/events/` persistence adapter. Compose services in the factory; keep memory, Events and learner authority independent.

LangChain may consume RAG capabilities, but RAG should not become inseparably coupled to LangChain. The expected future existence of learner modeling, assessments, OCR, document processing, embeddings, vector retrieval, LLM providers, and adaptive learning justifies clean boundaries—not empty abstraction layers or fake implementations today.

Chat models are constructed through the Mentra model factory in `langchain/`; compatible providers are configured through environment variables, not hard-coded SDK clients in callers. Embedding inference and Qdrant access belong in `rag/` and remain independent of chat configuration. Local embedding model files must be baked into the backend image, and vector collections must track/validate the embedding model identity as well as vector configuration.

Do not add empty folders or modules merely to mirror a template. Create them when they contain useful code.

## Coding rules

- Use Python type hints and small, focused modules.
- Keep route handlers thin and put workflows in service code when such workflows exist.
- Use Pydantic models at API boundaries; keep shared schemas minimal.
- Read environment-backed configuration through centralized settings. Never hardcode secrets or provider credentials.
- Use structured, consistent logging; do not silently swallow exceptions.
- Avoid broad `except Exception` except at an intentional application boundary. The centralized unexpected-error handler logs the exception and returns a generic response without exposing internals.
- Avoid circular imports and keep domain logic independent from HTTP where practical.
- Use async functions when they provide value for asynchronous I/O; do not make every function async automatically.
- Keep generic helpers genuinely generic. Do not create a giant `utils.py` or speculative domain helpers.

## API and errors

- Version public routes under `/api/v1`; define feature routers in route modules and include them in the central API router.
- Validate inputs and define response contracts with Pydantic schemas at API boundaries.
- Choose HTTP status codes that match the outcome; use clear resource- and action-oriented route names rather than defaulting to RPC-style endpoints.
- Return application errors in the consistent shape `{"error":{"code":"...","message":"..."}}`. Request validation errors may include sanitized field details. Unexpected failures return a generic 500 message and are logged server-side.
- Raise `AppError` for expected application-level failures. FastAPI HTTP errors are normalized by the central handler; do not return ad hoc error dictionaries from individual routes.
- Keep health routes lightweight and preserve their stable status/service response for health checks.
- Bind ownership through existing authentication/onboarding dependencies; reject client-selected owners and unknown request fields. Keep cookie-origin checks and `Cache-Control: no-store` on personal responses.
- Run synchronous persistence/services in the threadpool from async routes. Keep bounded pagination, typed projections and recovery endpoints close to their feature.

## Database

- PostgreSQL is the application database; configure its standard connection URL through `DATABASE_URL`.
- SQLAlchemy 2.x tables and queries belong in feature repositories. Services, routes, LangChain, and RAG never access SQL/ORM directly. `db/` owns connection/migration infrastructure.
- Alembic owns all schema changes. The Docker entrypoint runs `python -m app.db.migrate` before Uvicorn; application lifespan checks the revision and does not create tables. Freeze reviewed migration definitions instead of importing mutable application tables; add a follow-up revision for later corrections.
- All learner-owned rows use internal UUID `learner_id` foreign keys. Preserve composite ownership constraints, immutable evidence, transactions, indexes, and optimistic state versions.
- Test against an explicit dedicated `TEST_DATABASE_URL`, with temporary per-test schemas; never fall back to the application database.
- Chat, memory and Events share the existing `chat_sync_state` owner-row lock through `app.db.owner_transactions`. Acquire it before feature row locks; never introduce a separate coordination lock that existing writers ignore. Domain callers receive an opaque `OwnedUnitOfWork`; only persistence adapters access its session. Hold no transaction over model/network calls.
- Events writes bound query/lock waits to five seconds; map known timeout/context-FK races to typed application errors and let unexpected database failures reach centralized logging. Use consistent read snapshots for page projections and watermarks; batch projections/audits/changes rather than adding a query per item.
- The migration runner keeps its session advisory lock, uses committed nonblocking probes to avoid concurrent-index snapshot deadlocks, and bounds acquisition to 300 seconds. Rehearse simultaneous migrations and timeout cleanup when changing this path.

## Testing

Test behavior and boundaries that matter. Do not write tests merely to inflate coverage.

Prioritize API behavior, service logic, and persistence behavior. Validate success paths and meaningful error paths, including the standardized API error envelope.

Run affected tests against dedicated PostgreSQL and rehearse upgrade/downgrade/re-upgrade, non-feature row preservation and metadata drift for schema changes. Verify races, rollback and retry receipts with real persistence. The backend Dockerfile uses Python 3.12; validate dependencies and final application code in that runtime even when the local virtual environment differs. Distinguish unit/integration checks, image tests, browser checks and actual deployment in reports; do not combine overlapping test counts.

## Dependencies

> Do not add a dependency for something that can be implemented clearly and safely in a few lines, but also do not reimplement complex, security-sensitive, or well-solved infrastructure merely to avoid a dependency. Every dependency should have a reason to exist.

Resolve new graph/checkpoint dependencies against the existing LangChain/provider pins in a disposable actual-runtime image. Require serializer hardening and durable restart/resume/cleanup evidence before adopting a saver. `testing/event_dependencies.py` is disposable-only and must never run on application startup. The Events graph gate remains open; see [rehearsal evidence](../docs/events.md#dependency-gate-discovered-during-rehearsal).

## Events contracts

- Use `HistoryManagement.events` and public learner context reads; no event writes to learner tables or mastery. Keep event capture, event reminders and memory admission independent.
- Preserve explicit IANA zones and date-only versus aware-instant modes. Normalize instant comparisons to UTC, including DST folds; never use host timezone aliases or turn a date-only value into a browser-local midnight. Keep preview and saved reminder eligibility consistent; reject gaps/skipped dates and expose fold choices.
- Manual mutations use request UUID/payload receipts and expected revisions. Recover committed or deleted outcomes before revalidating mutable dependencies; retries must not resurrect deleted events. Preserve owned composite FKs as the transactional fence.
- One event has one lifetime reminder ledger. Unrelated edits preserve its due instant; explicit scheduling edits can update an undelivered schedule. Reopen skips missed reminders and only rearms future undelivered ones. Delivered outcomes are immutable; direct ledger deletion is prohibited while the event exists. Parent deletion owns the purge.
- Source-chat deletion detaches evidence transactionally and retains saved events. A pending ledger is not delivery evidence; AI proposals, Notifications and worker delivery remain future implementation scope. See [Events contracts](../docs/events.md) and the [delivery plan](../Mentra_Events_Implementation_Plan.md).

## Learner Engine

- Inject `LearnerService`; application startup provides `app.state.learner_service`. The concrete `LearnerEngine` remains independent of LangChain, providers, persistence imports and database configuration.
- External modules resolve canonical identity and submit observations through the facade. Never update learner state/tables directly or expose unrestricted mastery, ontology, or OCR-confirmation tools to an LLM.
- Bind authenticated learner UUID and observation provenance in orchestration. The anonymous HTTP chat must not accept a client-selected learner identity to retrieve private history.
- Preserve source, question/item, session and occurrence identity across retries. Assessment revisions automatically replace accepted earlier grades for the same item/session/attempt; explicit corrections preserve known identity. Immutable provenance is retained.
- Keep SQL in focused `learner/repositories/postgres_parts` stores and share the adapter's transaction session. Do not move scoring, context selection, or ranking into persistence.
- Ordinary evidence ingestion uses sufficient statistics; only older arrivals, corrections, ontology changes, or policy changes require history replay. Batch context/state reads and bound prompt/tool outputs.
- Version replaceable policies and retain evidence for recalculation. Baseline heuristics require empirical evaluation before their values can be treated as calibrated probabilities.
- Separate independent demonstrations, guided practice, challenge coverage, item diversity and spaced recall. Unknown independence/difficulty stays unknown; total marks cannot be copied onto multiple concepts. Predict before ingesting each held-out label during evaluation.
- Store explicit context goals for importance/target difficulty. Default importance is neutral, and unknown target performance is not evidence of weakness or mastery.
- See `app/learner/README.md` for consumer integration boundaries and test commands.

## Authentication

Authentication lives in `auth/`, with separate repository ports and PostgreSQL adapters. Standalone accounts use Argon2id passwords; opaque bearer sessions store only token digests. External assertions are verified using configured issuer, audience, algorithm and public keys before provisioning identities. The Learner Engine receives the authenticated `learner_id` and has no account, password or token logic. Do not pass client-selected ownership to learner operations or trust token-provided keys/algorithms. See [identity setup](../docs/identity-and-postgresql.md).

## Student Profile

Keep factual edits, calibration scoring, and conservative estimate updates centralized in their services/policy. The configured model factory provides structured AI evaluation outside database transactions; validate every estimate and evidence reference before applying. Persist deterministic results before provider calls, preserve unknown fields on failure/skip, and reject stale context/duplicate applications. Blueprints are curated, versioned and snapshotted; never generate arbitrary onboarding items or expose their keys. See [profile contracts](../docs/student-profile.md).

## LLM prompts

Use the application-shared `MentraLLM` for model invocation. Each request must supply a fixed internal `PromptSource` selected by its trusted workflow; never accept prompt selection from HTTP/client input. Keep system prompt text in a source-specific module under `langchain/prompts/`, register it in `prompts/registry.py`, and keep dynamic context separate from reusable instructions. Pass structured-output schemas through the same component. Do not embed system prompt strings in services, routes, tools, or agents. See [LangChain prompt routing](app/langchain/README.md).
