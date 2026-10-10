# Mentra

Mentra is an adaptive AI learning assistant with a FastAPI backend, React + TypeScript frontend, PostgreSQL persistence, standalone/platform identity, a granular Learner Engine, and a separate high-level Student Profile. Docker Compose runs the backend, frontend, RAG ingestion worker, and local PostgreSQL database.

## What Mentra currently contains

- FastAPI backend with health checks and modular route registration
- Centralized FastAPI error responses for application, HTTP, validation, and unexpected errors
- React + TypeScript + Vite + Tailwind CSS frontend with a responsive, routed learning workspace
- Local-first workspace shell with Chat, Library, Progress, Assessments, and Settings routes
- Account-owned persistent conversations with bounded model context, recoverable turns, incremental browser caching and Markdown responses
- On-demand history retrieval and evidence-backed user memories with manual Settings management and independent AI-write preferences
- Manual Events backend with authenticated CRUD, lifecycle, temporal preview, operation recovery and bounded agenda/sync APIs
- Multi-stage frontend image serving the built app with Nginx
- PostgreSQL repositories using SQLAlchemy 2.x and Alembic
- Modular Learner Engine with concept resolution, immutable evidence, versioned estimates, relevance, and recommendation contracts
- Standalone accounts and generic public-key external SSO with internal learner UUIDs
- Username/password login and registration with persistent HTTP-only sessions and guarded workspace routes
- Separate high-level Student Profile, mandatory profile onboarding, and optional controlled eight-question calibration
- Signed EduVerse student provisioning with an initial profile, preserving future standalone/platform identity boundaries
- Docker Compose setup for PostgreSQL, backend, and frontend services
- Shared LangChain invocation component (`MentraLLM`) with workflow-selected, versioned system prompts in separate modules
- Provider-independent chat model factory for OpenAI-compatible endpoints
- Local, image-baked BGE embeddings kept independent from chat models and exposed through `EmbeddingService`
- Remote Qdrant Cloud adapter with collection dimension and embedding-identity validation
- Learner-owned Library uploads, durable ingestion, local document/OCR extraction, hybrid retrieval, grounded chat citations and source lifecycle workflows
- Shared [Mentra Vision module](backend/app/vision/README.md) for local image and PDF-page OCR, with independent capability providers
- Environment-based configuration through `.env` values

## Project structure

```text
mentra/
|-- backend/
|   |-- app/
|   |   |-- api/routes/         # Auth, profile, EduVerse, conversations, memory, Events, Library, health
|   |   |-- chat/               # Canonical conversations, durable turns, bounded model history
|   |   |-- history_management/ # On-demand history, user memory, separate Events domain/repositories
|   |   |-- auth/               # Accounts, sessions, generic signed external identity
|   |   |-- student_profile/    # User details, broad estimates, controlled calibration
|   |   |-- learner/            # Granular concept knowledge and immutable evidence
|   |   |-- integrations/       # Trusted platform profile provisioning contracts
|   |   |-- langchain/          # Shared LLM, source-specific prompts, chat, profile evaluator, learner tools
|   |   |-- rag/                # Source storage, durable ingestion, parsers, retrieval, vector adapters, evaluation
|   |   |-- vision/             # Shared stateless OCR and PDF-page rasterization with capability providers
|   |   |-- db/                 # Connections, migrations, shared owner transactions
|   |   |-- core/               # Settings, logging, errors, identifiers
|   |   |-- main.py
|   |-- alembic/versions/       # Reviewed PostgreSQL migrations
|   |-- tests/                 # Domain, repository, API, concurrency, parser tests
|   |-- testing/               # Isolated PostgreSQL and browser test fixtures
|   |-- scripts/               # Synthetic learner verification
|   |-- Dockerfile
|   |-- requirements.txt
|-- frontend/
|   |-- src/
|   |   |-- components/        # Shared UI, auth/profile providers, theme, workspace
|   |   |-- pages/             # Login/register, onboarding/calibration, workspace
|   |   |-- services/          # Credentialed backend API clients
|   |   |-- layouts/
|   |   |-- styles/            # Semantic Light/Dark/System design tokens
|   |   |-- types/
|   |-- tests/                 # Real auth/profile browser flows
|   |-- scripts/               # Theme checks
|   |-- Dockerfile
|   |-- nginx.conf
|   |-- package.json
|-- docs/                      # Setup, API contracts, verification reports
|-- .env.example
|-- docker-compose.yml
```

## Requirements

- Docker Desktop or Docker Engine
- Docker Compose
- Node.js 20+
- Python 3.12+
- npm

## Configure `.env`

Copy the example file and adjust environment values as needed:

```bash
cp .env.example .env
```

The values configure the OpenAI-compatible chat endpoint, local embedding model, Qdrant Cloud collection, CORS, and PostgreSQL connection URL. Set `AI_MODEL`, `AI_BASE_URL`, and `AI_API_KEY` before starting. Set the Qdrant values for readiness to pass. `VITE_API_URL` is baked into the frontend bundle when its image is built, so it must be an address reachable from the user's browser (the default is `http://localhost:8000`).

## Run with Docker

Set `DATABASE_URL` in `.env` to your complete Supabase PostgreSQL connection URL. Local
PostgreSQL is opt-in through the `local-db` profile; normal startup uses the hosted database.

```bash
docker compose up --build -d --wait --wait-timeout 180
```

## Frontend URL

- http://localhost:5173

The UI opens at `/login` for guests. Registration signs you in immediately, then requires profile information and offers a recommended, optional 1â€“2 minute calibration before entering the workspace. An HTTP-only cookie restores your session on refresh and return visits; onboarding and assessment progress follow your account. View/edit your profile and retry calibration evaluation in Settings. Sign out from the sidebar to revoke the session. Conversations and their messages are persisted per account in PostgreSQL, with incremental browser caching and recoverable turns. See [persistent chat](docs/persistent-chat.md).

## Workspace routes

- `/login` and `/register` - username/password authentication
- `/onboarding` - mandatory profile information and optional calibration
- `/calibration` - later calibration from Settings
- `/` - Chat
- `/chat/:conversationId` - saved conversations, paged history, and recoverable responses
- `/library` - owned study materials, uploads, source views and retrieval settings
- `/progress` - placeholder; planned Events/Learning interface is not implemented
- `/assessments` - practice and assessment placeholder
- `/settings` - editable Student Profile, calibration/retry, theme, and account data information; `?tab=memories` opens memory management

## Backend URL

- http://localhost:8000

## Swagger/OpenAPI URL

- http://localhost:8000/docs

## Health endpoint

- http://localhost:8000/api/v1/health
- http://localhost:8000/api/v1/health/ready (configuration and dependency diagnostics)

## Stop and rebuild

```bash
docker compose build backend frontend
docker compose up -d --wait --wait-timeout 180
docker compose ps
```

Routine rebuilds recreate containers using the new images. Supabase data remains in the hosted database; if the optional local database is used, its named volume is preserved. The backend upgrades Alembic to head before startup. To rebuild without cache:

```bash
docker compose build --no-cache
```

## Documents, Vision, LangChain and RAG boundaries

- `backend/app/documents/`: shared file detection and component format readers for document consumers, with embedded image extraction through Vision. Read [Mentra Documents](./backend/app/documents/README.md) for the public API, supported formats and library choices.
- `backend/app/vision/`: reusable stateless OCR and PDF rasterization providers. Read [Mentra Vision](./backend/app/vision/README.md).
- `backend/app/langchain/`: `ModelFactory` constructs the configured OpenAI-compatible chat model; the shared `MentraLLM` handles invocations, source-specific prompt composition, and structured-output validation. Workflow services select a trusted `PromptSource`; prompt modules live under `backend/app/langchain/prompts/` and own their versions. The application injects the same component into chat and Student Profile evaluation. Learner tools are scoped to the authenticated internal `learner_id`.
- `backend/app/rag/`: the framework-independent source service owns private uploads, versioned extraction/chunking, scoped dense/lexical retrieval, optional local reranking, and source lifecycle. A separate durable worker shares the private materials volume with the API. LangChain receives bounded source packets and owns answer generation; it never constructs embeddings or Qdrant clients in chat code. Read [RAG setup and contracts](./docs/rag.md) and [verification evidence](./docs/rag-verification.md).

Switch compatible chat providers by changing `AI_BASE_URL`, `AI_MODEL`, and `AI_API_KEY`. `EMBEDDING_MODEL` and `EMBEDDING_DEVICE` configure the independent local embedding service. The local embedding model is baked into the backend image; changing it requires an image rebuild and Qdrant reindex. Readiness verifies configuration, the local embedding model, and Qdrant without invoking the chat model. Qdrant connectivity is checked by readiness rather than liveness, so an outage does not prevent the backend health endpoint from responding.

Chat renders user and assistant Markdown with shared Prism code blocks. Library sources reuse the same formatting, with extracted/original views, authenticated downloads and responsive Light/Dark styling. See [code rendering and visual evidence](./docs/code-rendering.md).

## Persistence and identity

Read [PostgreSQL and identity setup](./docs/identity-and-postgresql.md) for migrations, native Python setup, trusted external providers, and PostgreSQL tests. [Frontend authentication](./docs/frontend-auth.md) describes browser session configuration and end-to-end tests. Learner-owned data uses internal `learner_id` UUIDs; services and LangChain access it through repository-backed learner contracts.

GitHub Actions can apply Alembic revisions to Supabase PostgreSQL on `main` pushes after the repository secret `SUPABASE_DATABASE_URL` is configured. See the [schema deployment instructions](./docs/identity-and-postgresql.md#deploying-schema-updates-from-github).

Read [Student Profile and calibration](./docs/student-profile.md) for the separate high-level profile, API contracts, conservative adaptation, and the EduVerse provisioning request. Neither onboarding nor its AI evaluator writes granular concept mastery.

## History, memory and Events

[History management](docs/history-management.md) provides bounded conversation lookup and evidence-backed user memory. Memory admission and manual management use separate contracts from Events; their preferences do not control each other.

The [Events backend foundation](docs/events.md) is composed as `HistoryManagement.events`. It stores one-off date-only or timed events, enforces owner/context isolation and revisioned writes, and retains one reminder ledger per event. A ledger records scheduling state; it does not deliver a notification. Event completion does not change learner mastery.

AI event tools/admission, durable proposals, standalone Notifications, reminder delivery, and the Progress Events/Learning UI remain unimplemented. The LangGraph dependency/security gate is unresolved and production dependencies are unchanged. Follow the [Events implementation tracker](Mentra_Events_Implementation_Plan.md) for verified increments and remaining acceptance gates.

The repository migration head is `20261009_0008`: Events foundation (`0007`) and additive reminder-ledger retention (`0008`) follow Library, persistent chat and memory revisions. Repository head does not prove that a deployed database has been upgraded.

## Engineering standards

Backend workflow tracing, terminal output, settings, and the one-connection recipe for new modules are documented in [backend logging](docs/backend-logging.md). Upgrade to migration `20261010_0014` before running the updated API or workers.

- [Backend contributor standards](./backend/standards.md)
- [Frontend contributor standards](./frontend/standards.md)
- [Teammate setup guide](./docs/SETUP.md)

The frontend shared API client is in `frontend/src/services/api.ts`. Backend errors use a consistent `{ "error": { "code": "...", "message": "..." } }` structure; validation errors may include field details.

## Verification

The 2026-10-09 Events re-pass passed all **333 backend tests** in the rebuilt Python 3.12 image, **40 focused local tests**, and frontend build/theme checks. See [Events verification](docs/events.md#verification-and-deployment-boundary). These runs used disposable PostgreSQL resources and did not migrate or deploy the application; earlier browser/runtime reports retain their original scope and dates.

See the [full-stack verification report](./docs/student-profile-verification.md) for PostgreSQL tests, browser checks, Docker image/runtime checks, and external-provider limits. Build/start commands and migration diagnostics are in the [setup guide](./docs/SETUP.md).
