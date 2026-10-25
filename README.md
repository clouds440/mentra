# Mentra

Mentra is an adaptive learning workspace built with FastAPI, React + TypeScript,
PostgreSQL, LangChain/LangGraph, local CPU embeddings, and Qdrant retrieval.
PostgreSQL owns canonical conversations, attachment metadata, assessments, learner
evidence, events, notifications, settings and durable jobs. Private original files
live in Cloudinary; Qdrant holds derived retrieval vectors. Browser caches
accelerate navigation and synchronize with authoritative server records.

Start with [setup](docs/SETUP.md) to run Mentra, the
[backend atlas](docs/Mentra_Backend_Map.md) to understand its implementation, or
the [production runbook](docs/production-readiness.md) to prepare a deployment.

## Current features

- **Persistent chat:** account-owned conversations, rename/delete, recoverable
  generation and Stop, incremental cross-tab/device synchronization, and immediate
  session-cache rendering followed by database reconciliation on revisits. Search
  finds literal phrases in owned titles/messages and opens the exact saved exchange,
  including messages outside the current window.
- **Chat context:** private rolling summaries stored by chat ID, recent verbatim
  context, exact/keyword history recovery, and an owner-scoped tool for searching
  past conversation summaries before retrieving original exchanges. Summary search
  supports pagination and marks incomplete coverage; referenced messages can be
  recovered by ID from selected owned chats. Normal chat input is 8,192 tokens,
  with a bounded 12,288-token recovery allowance and a separate 2,048-token output
  reserve. Original displayed messages remain intact.
- **Rich answers:** Markdown, shared Prism code blocks, rendered equations, citations, interactive
  choices, compact assessment cards and a copy-as-plain-text action. Scrolling is
  contained within chat, and answers use a short top-to-bottom reveal.
- **Attachments and voice:** stage uploads or paste files/images inside the
  composer before sending; up to four files including three images per message.
  Durable authenticated previews open in a download overlay and can be added to
  Library. Vision-capable chat models receive images with the question; local OCR
  is a fallback. CPU Whisper voice transcription fills the editable composer.
- **Private files:** one authenticated upload pipeline handles chat, Library,
  answer sheets and speech. Domains bind original assets by ID; chat-to-Library
  and chat-to-assessment flows reuse the original. Downloads recheck current
  ownership and bindings, support streaming/ranges, and expose no provider URLs.
  Cleanup respects surviving references and active read leases; speech originals
  and calendar exports have bounded retention.
- **Library and RAG:** durable ingestion, native document reading and local OCR,
  multilingual E5 embeddings, hybrid dense/lexical retrieval, optional reranking, provenance
  and source lifecycle controls. Prefetch warms caches; passages reach the model
  only after a requested retrieval tool call. Selected materials are cleared after
  a successful response. Library title/filename search runs on the server; ready
  materials offer an editable, source-grounded quiz shortcut. Citations open their
  exact source passage before full-document browsing.
- **Assessments:** chat drafts and saved assessments, interactive MCQs or written
  answers, revisions that preserve originals, reviewed image/document answer
  extraction, durable grading and learner evidence. Interactive choices stay in
  memory until final Submit; grading status is visible in the composer. Assessment
  source selection searches/pages the complete Library and preserves selections.
  Graded results can prepare selected mistake questions with durable answer-exposure
  and item lineage; repeated practice cannot count as fresh independent evidence.
  Mistake history also supports generated revision practice. Grades publish before
  nonessential learning updates, with explicit pending/applied evidence status.
- **Solve on paper:** download an answer-free, numbered question PDF, solve offline,
  then upload PDF, TXT or PNG/JPEG answers. Review and explicitly confirm the
  extracted answers before submitting through the same grading/evidence pipeline
  as UI answers. Incomplete extraction preserves saved drafts, and recognized
  option letters/text normalize to immutable choice IDs. Downloading an unsaved
  chat question paper does not publish it or create an attempt.
- **Learning Progress:** concept review, searchable understanding, practice
  recommendations and evidence-supported follow-up reviews. Accepting a topic
  does not count as mastery evidence. Practice/review actions retain exact owned
  concept/context targets; Quick review prepares three questions for an eligible
  topic, with explicit generation before starting. Per-topic evidence details explain
  uncertainty, independent difficulty coverage and recent accepted practice.
- **Events and notifications:** an owned agenda, reminders, manual editing and
  durable proposals. Actual first-party event announcements are captured before
  chat answers and auto-saved when complete/unambiguous; uncertain details remain
  reviewable. Event announcements alone do not request practice quizzes. An
  independent Notifications inbox receives reminder publications.
  Events can be downloaded as calendar snapshots; imported files do not sync later changes.
- **Web tools:** keyless You.com MCP `web_search` and a separate authenticated
  `web_research` tool using `YOU_WEB_SEARCH_API_KEY`, with independent quotas,
  caching, source dates and citations. Research can consume provider credits.
- **Identity and personalization:** standalone username/password accounts,
  HTTP-only sessions, current-password-verified password changes in Settings,
  mandatory profile onboarding, optional calibration, evidence-backed memories,
  preferred names and shared Light/Dark/System themes. Password changes preserve
  the current session and revoke other active sessions. New browser sessions have
  an absolute 30-day default lifetime. Retired external/platform sign-in routes
  are not available; legacy records remain preserved.
- **Background context:** a dedicated summarizer maintains separate private chat
  and persistent-memory summaries. Memory blocks retain current supporting memory
  IDs/revisions; edits, deletions and expiry invalidate stale support. Summaries
  are lossy context, not replacement transcripts or independent learning evidence.
- **Diagnostics:** correlated request/job/tool/model traces with execution timing,
  supplied/skipped/defaulted parameter shapes and sanitized failures. Query and
  response bodies are not retained in logs.

## Quick start

Docker Desktop/Engine and Docker Compose are sufficient for the container setup.
Node.js 24 LTS and Python 3.12 are needed only for native development/testing.

```powershell
Copy-Item .env.example .env
```

Fill the required values before starting; keep `.env` private and out of Git.

| Configuration | Purpose |
| --- | --- |
| `DATABASE_URL` | Complete PostgreSQL connection URL with provider-required SSL options; hosted or explicitly configured local database |
| `CLOUDINARY_URL` | Server-only credentials for private original files; required by the API and file-consuming workers |
| `AI_MODEL`, `AI_BASE_URL`, `AI_API_KEY` | Compatible chat/tool/structured-output provider; `AI_PROVIDER=openai_compatible` |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | Retrieval index configuration; configure the key when required by the deployment |
| `FRONTEND_ORIGIN`, `CORS_ORIGINS` | Allowed browser origins; use explicit HTTPS origins for production |
| `VITE_API_URL` | Browser-reachable API base, built into frontend assets; local default `http://localhost:8000` |
| `FILES_NAMESPACE`, `FILES_ENVIRONMENT` | Private asset namespace; preserve the existing suffix when changing deployment environment |

Models and parser tools are provisioned during backend image build; runtime local
inference does not download weights. Building requires network access and enough
disk space for dependencies and model assets. See [setup](docs/SETUP.md) for the
full setting reference and native-development prerequisites.

```sh
docker compose up --build -d --wait --wait-timeout 180
```

Default services are `backend`, `frontend`, `rag-worker`, `assessment-worker`,
`events-worker`, `summarizer` and `files-worker`. Local PostgreSQL is optional:

```sh
docker compose --profile local-db up -d postgres
```

For that profile, set `DATABASE_URL=postgresql://mentra:mentra_local@postgres:5432/mentra`
for containers; native clients use the configured localhost port instead. The API
applies Alembic migrations before starting. The repository migration head is
`20261021_0030`; verify the actual database revision rather than assuming deployment.
Read the [production runbook](docs/production-readiness.md) before migrating an existing installation;
the storage migration refuses to discard legacy file data.

| Address | Purpose |
| --- | --- |
| `http://localhost:5173` | Frontend |
| `http://localhost:8000/docs` | OpenAPI |
| `http://localhost:8000/api/v1/health` | Lightweight liveness |
| `http://localhost:8000/api/v1/health/ready` | Database, AI configuration, embeddings and Qdrant readiness; no paid model call |

Guests use `/login` or `/register`, then complete onboarding. Use the same hostname
for frontend/backend locally so cookie policy works.

## Models and retrieval

| Capability | Model / execution | Configuration |
| --- | --- | --- |
| Chat, tools and structured educational workflows | Configured OpenAI-compatible model; reused for generation, grading, extraction/admission and summary workflows | `AI_MODEL`, endpoint and key; no fixed model name required by the repository |
| Assessment image transcription | Optional vision-capable override; empty inherits the main model | `AI_VISION_MODEL`, `ASSESSMENT_VISION_ENABLED`; provider image support required |
| Dense embeddings | Local CPU `intfloat/multilingual-e5-small` | `EMBEDDING_MODEL`; baked revision and vector dimensions must match Qdrant |
| Multilingual reranking | Local CPU `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Optional `RAG_RERANKER_MODEL` build argument and `RAG_RERANKER_PATH` runtime setting |
| Voice | Local multilingual Whisper Base, CPU INT8 | `SPEECH_MODEL=base`; `tiny` and `small` are also supported |
| OCR / PDF pages | English Tesseract OCR and Poppler rasterization | System tools baked into the backend image; separate from multilingual image-model transcription |

Retrieval combines dense and optional lexical candidates, hydrates currently owned
sources, then optionally reranks them before final source/token limits. The
reranker uses plain query/passage pairs, batches of eight and a default cap of 20
candidates (configurable 1–40). Warm inference defaults to five seconds; cold model
loading has a separate allowance. Busy/unavailable inference retains the original
retrieval ranking and reports fallback diagnostics.

The current `.env.example` includes the optional reranker configuration. Keep its
model and path empty to disable it. Enabling/changing it requires rebuilding the
backend and recreating consuming services; it does **not** require resetting E5
vectors. See [reranker setup](docs/SETUP.md#optional-local-multilingual-reranker).
Actual model image support, generation quality and provider availability require
their own checks; readiness validates configuration without generating a response.

## Workspace routes

| Route | Feature |
| --- | --- |
| `/login`, `/register` | Local account access |
| `/`, `/chat/:conversationId` | New/saved chat |
| `/library`, `/library/new`, `/library/:documentId` | Materials and source views |
| `/assessments` | Saved practice, attempts and grading |
| `/progress` | Learning Progress; `?tab=events` opens the agenda |
| `/events` | Redirect to the Progress Events tab |
| `/notifications` | Notifications inbox |
| `/settings` | Profile, calibration, password and assessment preferences; `?tab=memories` or `?tab=notifications` selects those settings |
| `/onboarding`, `/calibration` | Profile setup and optional calibration |

## Services and persistence

| Compose service | Responsibility |
| --- | --- |
| `backend` | FastAPI and domain composition; durable chat turn execution, activity and local inference helpers |
| `rag-worker` | Durable ingestion, parsing/chunking/embedding, generation publication and index reconciliation |
| `assessment-worker` | Independent generation, grading, chat-evidence and assessment-evidence consumers |
| `events-worker` | Reminder publication and bounded session/attachment/memory maintenance |
| `summarizer` | Durable chat and memory summary queues with bounded concurrency, retries and independent limits |
| `files-worker` | Private-original expiry, deletion retries and orphan reconciliation |
| `frontend` | Built React assets served by unprivileged Nginx on container port 8080, host port 5173 |
| `postgres` | Optional `local-db` profile; hosted PostgreSQL is otherwise external |

PostgreSQL is authoritative for domain state, file registry/bindings and queues.
Cloudinary stores original bytes; there is no production fallback byte store in
PostgreSQL or a permanent local file mirror. Qdrant is a derived index whose hits
must pass current source authorization. A database backup alone cannot restore
external originals; coordinate preservation of database records, provider assets,
private configuration and compatible application/model images.

## API overview

All feature routes mount under `/api/v1`; authentication and ownership apply to
personal records. The [backend atlas](docs/Mentra_Backend_Map.md#module-reference)
lists every operation, and running `/docs` or `/openapi.json` describes exact
request/response schemas.

| API family | Capabilities |
| --- | --- |
| `/auth`, `/student-profile` | Local identity/session/password changes, onboarding and calibration |
| `/conversations`, `/chat-attachments` | Durable turns, Stop, sync, saved-message search/windows, public activity and attachment associations |
| `/files` | Single multipart intake, upload receipts/cancellation, sanitized metadata and authenticated GET/HEAD content |
| `/documents`, `/rag`, `/learning-contexts` | Materials/versions/jobs, source access/retrieval and owned learning context lifecycle |
| `/assessments` | Papers/chat drafts, generation jobs, attempts, answer-sheet preparation, submissions/corrections, mistake practice and question PDFs |
| `/learning` | Aggregate progress, concept review, searchable understanding and evidence explanations |
| `/memories`, `/events`, `/event-proposals`, `/notifications` | Owned memory/agenda/inbox management, proposal decisions, sync and calendar exports |
| `/speech/transcriptions` | Transcribe a previously uploaded speech file by JSON reference |
| `/health`, `/health/ready` | Liveness and dependency readiness; neither proves every worker queue is draining |

Original uploads enter `/files/uploads` once; domain association APIs accept JSON
file IDs. Paper uploads prepare `pending_transcription` attempts until reviewed
and explicitly submitted. Asynchronous turns/jobs have dedicated status reads;
revision checks and domain replay keys protect writes. The deprecated `/chat`
route remains a compatibility endpoint; the workspace uses durable conversations.

## Updating the stack

```sh
docker compose build backend frontend
docker compose up -d --force-recreate --wait --wait-timeout 180
docker compose ps
```

Recreate containers after configuration changes; frontend API URL changes require
a frontend rebuild. Rebuild the backend after changing image-baked embeddings,
speech weights or optional reranker configuration. Embedding changes also require
a compatible Qdrant reindex. Ordinary updates do not require deleting volumes.
Hosted PostgreSQL remains external; `docker compose down -v` deletes optional
local named volumes and must not be used as a routine update step.

Check schema/dependency consistency after an update:

```sh
docker compose exec backend python -m alembic -c /app/alembic.ini current
docker compose exec backend python -m alembic -c /app/alembic.ini check
docker compose exec backend python -m pip check
```

Also inspect readiness, worker logs and representative product workflows. A
healthy API container alone does not establish that new frontend assets, paid
providers, original-file delivery or background jobs work end to end.

## Production deployment

Use the [production runbook](docs/production-readiness.md),
[private configuration template](.env.production.example),
[production Compose override](docker-compose.production.yml) and optional
[TLS proxy template](deploy/nginx.production.conf.template). Replace template
values with the actual chosen infrastructure; no hosting provider is prescribed.

After creating and filling a private `.env.production`, validate it:

```sh
python backend/scripts/validate_production.py --env-file .env.production
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml config --quiet
```

The Python preflight requires the backend dependencies. It is read-only/offline;
it checks configuration, not live provider/database access. The production override
requires versioned images, public HTTPS origins, secure cookies and reviewed
listeners/proxy trust. It requires Compose 2.24.4+ for its merge behavior.
Preserve existing Files namespace/suffix values when changing `APP_ENV`, and review
storage migration guards before upgrading populated legacy installations.

Backend/worker processes run as UID/GID 10001; the shared log directory must be
writable by that identity. The frontend has a read-only root filesystem and
temporary `/tmp`. Default Compose connection capacity is API five plus five
workers at one each, excluding migration/admin use and overlapping deployments.
Backups/restores, live capability checks and infrastructure-specific TLS remain
release responsibilities covered by the runbook.

## Architecture and documentation

Domain services own their contracts and persistence. Chat owns turns and
publication; Learner owns concepts/evidence/mastery; RAG owns ingestion/retrieval;
Events owns schedules; Notifications owns inbox delivery. Orchestration calls
public facades rather than writing another domain's tables. Shared Documents,
Vision and Speech capabilities keep local processing independent of the LLM.
Files owns original storage/delivery and typed bindings; domain services retain
authorization and processing rules. The summarizer coordinates two domain-owned
compaction queues rather than owning transcripts or memories.

| Location | Contents |
| --- | --- |
| `backend/app/` | Production domains, APIs, orchestration and shared processing/infrastructure |
| `backend/alembic/` | Versioned schema history and migration environment |
| `backend/scripts/`, `backend/testing/`, `backend/tests/` | Operator/preflight tools, isolated runtime fixtures/harnesses and automated regressions |
| `frontend/src/`, `frontend/tests/` | React workspace, domain API clients, local caches and browser tests |
| `docs/` | Current contracts/setup/runbooks and dated verification/design records |
| `deploy/`, root Compose files | Proxy template and local/production process configuration |
| `.github/workflows/` | Backend verification and migration gates |

The stack uses Pydantic/SQLAlchemy/Alembic for contracts and persistence,
LangChain/LangGraph for model/tool workflows, SentenceTransformers for retrieval
models, Faster Whisper for speech, and ReportLab for question PDFs. The browser
uses React Router, Tailwind, Markdown/Prism and KaTeX, with Playwright for browser
verification. Detailed model/library tables live in the backend atlas.

| Documentation | Scope |
| --- | --- |
| [Backend atlas](docs/Mentra_Backend_Map.md) | Module and file guide, feature dependencies, APIs, storage, and worker flows |
| [Setup](docs/SETUP.md), [identity/PostgreSQL](docs/identity-and-postgresql.md) | Environment, migrations, native development and identity |
| [Production runbook](docs/production-readiness.md), [dated release verification](docs/production-readiness-2026-10-25.md) | Deployment configuration, preservation, recovery and the scope of recorded checks |
| [Private files](backend/app/files/README.md) | Cloudinary originals, upload receipts, bindings, authenticated delivery and cleanup |
| [Persistent chat](docs/persistent-chat.md), [context summaries](backend/app/chat/SUMMARIES.md) | Storage, synchronization, attachments and model context |
| [Saved-chat search](docs/saved-chat-search.md), [rich content](docs/code-rendering.md) | Original exchange recovery, code and equation rendering |
| [History and memory](docs/history-management.md), [memory summaries](docs/memory-summaries.md) | Exact history recovery, durable user memories and supported background compaction |
| [Assessment engine](docs/Assessment_Engine.md), [recovery](docs/Assessment_Recovery.md), [mistake practice](docs/mistake-practice.md) | Papers/parts, answer-sheet review, question PDFs, grading/evidence, revision lineage and retries |
| [Chat assessments](docs/chat-assessments.md), [interactions](docs/chat-interactions.md) | Generation, local answers, submission and grading |
| [Learning Progress](docs/learning-progress.md), [Events](docs/events.md), [Notifications](docs/notifications.md) | Understanding, agenda, capture and reminder delivery |
| [Web search/research](docs/web-search.md), [voice](docs/voice-input.md) | Provider tools and CPU transcription |
| [RAG](docs/rag.md), [Documents](backend/app/documents/README.md), [Vision](backend/app/vision/README.md) | Source processing and retrieval |
| [LangChain](backend/app/langchain/README.md), [logging](docs/backend-logging.md) | Model/tool orchestration and diagnostics |
| [Prompt efficiency](docs/prompt-efficiency.md) | Prompt sizes, provider caching and validation evidence |
| [Tool cache](docs/Tool_Cache_Policy.md), [response feedback/style](docs/Chat_Feedback_and_Response_Style.md) | Freshness/authorization boundaries and teaching-response preferences |
| [Backend standards](backend/standards.md), [frontend standards](frontend/standards.md) | Contributor conventions |

Implementation plans and dated verification reports preserve design/rollout
history; they are not a current feature checklist or proof of the deployed state.
Direct backend pins live in `backend/requirements.txt`, resolved constraints in
`backend/requirements.lock`, and browser dependencies in the frontend package
manifest/lockfile. The backend image builds with constrained dependencies and
checks their consistency; local installed versions can differ.

## Verification

Use an explicit, disposable `TEST_DATABASE_URL`; tests never fall back to the
application database. Backend fixtures apply migrations in isolated schemas.
See the setup guide for test commands and limitations of image-only test runs.
Frontend checks include production build, `npm run check:theme`, and Playwright
mock/real API configurations. Dated `*-verification.md` reports describe their
original run and scope, rather than a continuously updated total test count.

For native frontend development/checks, run from `frontend/`:

```sh
npm ci
npm run dev
```

```sh
npm run build
npm run check:theme
npm run check:ui
npm run test:e2e
```

Choose the appropriate Playwright mock or real-API configuration and its required
fixtures before browser tests. Backend suites live in `backend/tests/`; real
model/provider probes in `backend/testing/` and `backend/scripts/` are opt-in and
may require additional infrastructure or provider credits. See the
[atlas test/script index](docs/Mentra_Backend_Map.md#support-files).

Combined service logs are available with:

```sh
docker compose logs -f backend rag-worker assessment-worker events-worker summarizer files-worker
```

Daily JSON diagnostics are persisted at `logs/backend/backend-YYYY-MM-DD.log`.
`LOG_PARAMETER_DETAILS=false` disables detailed parameter shapes.
Summary queue diagnostics are available with
`docker compose exec summarizer python -m app.summarization.worker --diagnostics`.
Inspect domain job/attempt state and dated verification evidence alongside logs;
do not treat API readiness as an end-to-end workload or quality benchmark.
