# Backend Engineering Standards

> **Build for the requirements we have, while leaving clean boundaries for the requirements we expect. Do not implement future features before they exist.**

These standards describe the current Python and FastAPI codebase. Update them when an important backend convention changes.

## Project structure

- `api/`: HTTP concerns only—request validation, dependency injection, calling application logic, and mapping results to HTTP responses. Keep handlers thin; organize endpoints in route modules and register them through the central router.
- `core/`: cross-cutting infrastructure such as centralized configuration, logging, and global exception handling. Do not make it a dumping ground for feature logic.
- `db/`: database connection and persistence infrastructure, models, and future repository concerns. Keep database details out of unrelated modules.
- `schemas/`: shared API-boundary schemas only when they have multiple meaningful consumers. Feature-specific schemas should stay near their feature or route module rather than accumulating in a global catalogue.
- `services/`: application workflows and business logic. Add this boundary when a real workflow needs it; services should not depend unnecessarily on FastAPI request or response objects.
- `langchain/`: LLM orchestration, provider integrations, prompts, chains, agents, tools, and related educational orchestration.
- `rag/`: document ingestion and extraction, chunking, embeddings, vector retrieval, reranking, and related retrieval infrastructure.

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

## Database

- SQLite is the current application database. Its location comes from centralized configuration.
- Runtime database files must never be committed; Docker persists them through the repository `data/` mount.
- Do not invent the learner schema during bootstrap work.
- Manage future schema changes deliberately through a migration strategy rather than random startup mutations.
- Keep persistence logic in the database or relevant service/repository boundary; do not leak direct SQL throughout unrelated modules.

## Testing

Test behavior and boundaries that matter. Do not write tests merely to inflate coverage.

Prioritize API behavior, service logic, and persistence behavior. Validate success paths and meaningful error paths, including the standardized API error envelope.

## Dependencies

> Do not add a dependency for something that can be implemented clearly and safely in a few lines, but also do not reimplement complex, security-sensitive, or well-solved infrastructure merely to avoid a dependency. Every dependency should have a reason to exist.
