# Mentra teammate setup

## 1. Prerequisites

- Git
- Docker Desktop (Windows/macOS) or Docker Engine with the Docker Compose plugin (Linux)
- Docker must be running before starting the project

## 2. Clone the repository

In PowerShell, Git Bash, or a terminal:

```sh
git clone https://github.com/clouds440/mentra.git
cd mentra
```

## 3. Create local environment configuration

In PowerShell:

```powershell
Copy-Item .env.example .env
```

Configure server-only `CLOUDINARY_URL` for private files and an OpenAI-compatible chat endpoint before starting the backend; configure Qdrant Cloud for the readiness check to pass. `.env` is ignored by Git; never put credentials in `.env.example` or commit them.

The supported settings in `.env.example` are:

| Variable | Default | Current use |
| --- | --- | --- |
| `APP_ENV` | `development` | Backend environment setting |
| `BACKEND_HOST` | `0.0.0.0` | Backend listener address in its container |
| `BACKEND_PORT` | `8000` | Backend listener and published host port |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Primary allowed browser origin |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins |
| `DATABASE_URL` | *(required)* | Complete hosted PostgreSQL URL, including SSL options; optional local-db profile described below |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | See `.env.example` | Local Compose PostgreSQL settings |
| `AUTH_SESSION_SECONDS` | `3600` | Native bearer session lifetime |
| `AUTH_PERSISTENT_SESSION_SECONDS` | `2592000` | Absolute lifetime for new browser sessions (30 days) |
| `CLOUDINARY_URL` | *(required, server only)* | Authenticated private originals shared by API and file consumers |
| `AUTH_COOKIE_SECURE` | `false` | Require HTTPS for the session cookie; automatically enabled outside development/test |
| `AUTH_COOKIE_SAME_SITE` | `lax` | Cookie SameSite policy: `lax`, `strict`, or `none` (HTTPS required for `none`) |
| `TEST_DATABASE_URL` | *(explicit test database)* | Used only by tests and synthetic verification |
| `AI_PROVIDER` | `openai_compatible` | Mentra chat-model adapter |
| `AI_MODEL` | *(required)* | Model identifier accepted by the configured chat endpoint |
| `AI_BASE_URL` | *(required)* | OpenAI-compatible chat API base URL |
| `AI_API_KEY` | *(required)* | Secret for the configured chat endpoint |
| `AI_TEMPERATURE` | `0.2` | Chat model temperature |
| `AI_TIMEOUT` | `30` | Chat request timeout in seconds |
| `AI_MAX_RETRIES` | `2` | Chat request retry limit |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Local model baked into the backend image |
| `EMBEDDING_DEVICE` | `cpu` | Local embedding inference device |
| `QDRANT_URL` | *(required)* | Remote Qdrant deployment URL |
| `QDRANT_API_KEY` | *(required)* | Qdrant Cloud secret |
| `QDRANT_COLLECTION` | *(required)* | Collection name owned by Mentra |
| `QDRANT_DISTANCE` | `Cosine` | Collection distance metric |
| `VITE_API_URL` | `http://localhost:8000` | Frontend build-time API URL; must be reachable by the browser |

The frontend port is currently fixed at host port `5173` (container port `8080`). If you change `BACKEND_PORT`, also update `VITE_API_URL` and the CORS origins to match the ports/origin you use.

To switch chat providers, keep `AI_PROVIDER=openai_compatible` and set `AI_BASE_URL`, `AI_MODEL`, and `AI_API_KEY` to the compatible provider's values. DeepSeek and Groq use this same adapter; no application-code change is required. AI configuration is validated when a model is requested and reported by readiness, without a paid readiness request. Missing credentials do not prevent lightweight API startup. Qdrant is connected and its existing collection is validated by the readiness check, so a Qdrant outage does not prevent the lightweight liveness endpoint from responding.

Embeddings are independent of the chat provider. `intfloat/multilingual-e5-small` runs locally in the backend container; it is downloaded while building the image, uses CPU by default, and does not call an external embedding API. Changing `EMBEDDING_MODEL` requires rebuilding the backend image and reindexing the Qdrant collection. Mentra checks the collection's dimension, distance metric, model, and resolved model revision; it will not mix incompatible indexes. When replacing BGE with E5, stop API/ingestion/assessment services and run the explicit [vector reset procedure](../../backend/app/rag/README.md#e5-reset-and-verification). Matching 384-dimensional shapes do not make the two embedding spaces compatible.

### Optional local multilingual reranker

Copy these values from `.env.example` into your main `.env` to enable the CPU reranker:

```dotenv
RAG_RERANKER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
RAG_RERANKER_PATH=/opt/mentra/models/reranker
RAG_RERANKER_TIMEOUT=5
RAG_RERANKER_MAX_CANDIDATES=20
```

`MODEL` selects the build-time download; `PATH` enables the baked model at runtime. After changing them, run `docker compose build backend`, then `docker compose up -d --no-build --force-recreate backend assessment-worker`. A restart alone cannot provision new model weights. Leave `MODEL` and `PATH` empty to disable reranking. Your existing E5 vectors remain valid; no reset/reindex is required.

The reranker runs locally on CPU with a reusable process, batches of eight, and a 512-token query/passage budget. It reads plain text rather than E5 vectors or prefixed embedding inputs. `MAX_CANDIDATES` defaults to 20 and accepts 1–40. The warm inference timeout is five seconds; cold loading gets at least 30 seconds. When unavailable, retrieval reports degraded reranking and retains the original hybrid ranking. No language allowlist is applied.

## 4. Start Mentra

From the repository root:

```sh
docker compose up --build -d --wait --wait-timeout 180
```

Compose starts `backend`, `frontend`, `rag-worker`, `assessment-worker`, `events-worker`, `summarizer` and `files-worker`. Workers use the backend image; private original bytes live in Cloudinary, with ownership and lifecycle metadata in PostgreSQL. Startup applies migrations and checks the schema revision against the configured PostgreSQL database. Local PostgreSQL is opt-in: run `docker compose --profile local-db up -d postgres` and explicitly set `DATABASE_URL=postgresql://mentra:mentra_local@postgres:5432/mentra` for containers. The frontend waits for backend liveness.

## 5. Verify the app

- Open the workspace: http://localhost:5173
- Open the backend: http://localhost:8000
- Open Swagger/OpenAPI: http://localhost:8000/docs
- Check API health: http://localhost:8000/api/v1/health
- Check readiness diagnostics: http://localhost:8000/api/v1/health/ready
- View service status: `docker compose ps`

The lightweight liveness endpoint is `GET /api/v1/health` and returns `{"status":"ok","service":"mentra-api"}`. The readiness endpoint independently reports AI configuration, the loaded local embedding model and dimension, and Qdrant collection validity/reachability. Readiness does not call the paid chat API. Compose uses liveness for the backend container health check.

Guests are redirected to `/login`. Create an account at `/register` using only a username and password; registration signs in immediately, then requires high-level profile information at `/onboarding`. The recommended eight-question calibration is optional. Workspace routes `/`, `/library`, `/progress`, `/assessments`, and `/settings` require a session and completed onboarding. Refresh and later visits restore identity and onboarding/assessment progress; sidebar sign-out revokes the session. Use the same hostname for the frontend and backend locally (`localhost` for both, or `127.0.0.1` for both) so the default SameSite policy works.

Chat requests use the configured AI endpoint. Account-owned conversations and messages are persisted in PostgreSQL by migration `20261008_0005`; the browser caches individual records in IndexedDB and synchronizes changes. RAG material uploads, document readers, and Vision are available. See [persistent chat](../chat/persistent-chat.md), [RAG](../library/rag.md), [Student Profile setup](../profile/student-profile.md), and [frontend authentication](../identity/frontend-auth.md).

Events are available in `/progress?tab=events`, with manual APIs, upfront semantic chat capture and durable proposals. Learning Progress and Assessments are implemented; `/notifications` exposes the independent inbox populated by the Events worker. Memory management lives in `/settings?tab=memories`. See [Events](../events/events.md), [Notifications](../notifications/notifications.md), [Learning Progress](../learning/learning-progress.md) and [history/memory](../memory/history-management.md).

## 6. Update Docker images

Routine updates can rebuild and recreate containers directly. If you need to stop
the stack first, preserve the PostgreSQL volume:

```sh
docker compose down
```

Pull the latest project changes and rebuild/restart:

```sh
git pull --ff-only
docker compose build backend frontend
docker compose up -d --force-recreate --wait --wait-timeout 180
docker compose ps
```

The optional local-db profile uses the `mentra_postgres` named volume; hosted PostgreSQL remains outside Compose. `docker compose down` preserves it; `docker compose down -v` deletes it.

An image rebuild alone does not update an existing container. The `up` command recreates
containers when their image/configuration changes and applies Alembic migrations before
the backend starts. No `down`, volume deletion, or uncached build is required for routine
updates. Changing backend settings requires container recreation; changing `VITE_API_URL`
requires a frontend rebuild.

After updating, confirm `/api/v1/health` and `/api/v1/health/ready`, then check the schema:

```sh
docker compose exec backend python -m alembic -c /app/alembic.ini current
docker compose exec backend python -m alembic -c /app/alembic.ini check
docker compose exec backend python -m pip check
```

The repository migration head is `20261021_0030`, including proposals, notifications, assessments, web search and conversation summaries after the original identity/Library/chat/memory/Events foundations. Check `current` against repository head; documentation alone does not establish the deployed revision. Migrations
must preserve existing non-feature records; rehearse upgrade/downgrade on a
dedicated test database before release. API liveness and AI configuration checks
do not prove the paid provider can generate a response. Insufficient provider balance
leaves completed calibration answers saved, estimates unknown, and evaluation retry
available in Settings. See the [verification report](../profile/student-profile-verification.md)
and [profile contracts](../profile/student-profile.md) for testing and supported integration behavior.

## Chat and optional capability settings

- Chat input: `CHAT_INPUT_TOKENS=8192`, `CHAT_RECOVERY_INPUT_TOKENS=12288`, `CHAT_HISTORY_TOKEN_BUDGET=1800`, `CHAT_OUTPUT_TOKEN_RESERVE=2048`. Assessment workflows retain their separate 16k context. `CHAT_SUMMARY_ENABLED=true` enables incremental database-backed summaries; see [context compaction](../../backend/app/chat/SUMMARIES.md).
- Vision requires a model/endpoint that accepts images. Chat sends up to three images with the question; CPU OCR provides fallback extraction. CPU voice settings and image-baked weights are described in [voice input](../speech/voice-input.md).
- Enable keyless search with `WEB_SEARCH_ENABLED=true`. `YOU_WEB_SEARCH_API_KEY` separately enables authenticated research, which can consume credits; it never authenticates ordinary free MCP search. See [web tools](../web-search/web-search.md).
- `LOG_PARAMETER_DETAILS=true` records bounded parameter shapes, presence and timing, not payload values. Daily files live in `logs/backend`; see [logging](../observability/backend-logging.md).

`.env.example` and `app.core.config.Settings` are the complete configuration references. Provider secrets belong only in backend settings, never `VITE_*` variables.

## Troubleshooting

The migration entrypoint uses committed nonblocking probes for its session advisory
lock and waits at most 300 seconds. A timeout means another migration runner may
still own the lock; inspect its status before retrying. Use a session-capable
PostgreSQL connection, not a transaction pooler. Never print connection URLs or
credentials into shared logs. Tests require a separate explicit `TEST_DATABASE_URL`
and temporary schemas, never the application's database. Dated verification reports describe their own isolated resources, not the current deployed schema or service status.

- **Docker connection error:** Start Docker Desktop or the Docker Engine, then retry `docker compose up --build`.
- **Port already in use:** Free ports `5173` and `8000`. If changing the backend port, update `BACKEND_PORT`, `VITE_API_URL`, and the CORS origins in `.env`, then rebuild.
- **Backend not ready:** Check `docker compose logs backend` and `/api/v1/health/ready`; confirm AI settings, Qdrant Cloud access, collection compatibility, and that `DATABASE_URL` points to reachable PostgreSQL and migrations have run. The basic liveness endpoint does not require Qdrant.
- **Frontend is stale after configuration changes:** Rebuild with `docker compose up --build`; `VITE_API_URL` is embedded at frontend build time.
- **Image build download failure:** Retry `docker compose build frontend` or
  `docker compose build backend` separately. A package-registry connection reset can
  cancel the other build in a combined invocation; it is not an application-test failure.

For code conventions, see [frontend/standards.md](../../frontend/standards.md) and [backend/standards.md](../../backend/standards.md).


## Unified files — 20 October 2026

Original uploads now use the shared [Files module](../../backend/app/files/README.md). Configure the server-only `CLOUDINARY_URL`; paths use `FILES_NAMESPACE/(FILES_ENVIRONMENT or APP_ENV)`, defaulting to `mentra/<APP_ENV>/`. Preserve the historical storage suffix explicitly when enabling production mode for existing originals. Run `python -m app.files.worker` for expiry/reconciliation/deletion. No persistent materials volume is required. Upload UI, source filenames, Library version history and authenticated previews/downloads remain unchanged.

Chat and persistent memory summaries share one durable `summarizer` worker and the configured LLM, while retaining independent prompts and token/character limits. Apply migrations through `20261021_0030` before starting the updated services. The old `memory-summary-worker` service is replaced; remove its orphan container during the upgrade. See [memory summaries](../memory/memory-summaries.md) for settings, recovery and verification.

For HTTPS, proxy trust, initial index provisioning, backups, legacy-file migration and rollback, follow the [production runbook](../deployment/production-readiness.md). Backend container builds and CI constrain transitive packages with `backend/requirements.lock`; update and audit the manifest and lock together.
