# Mentra

Mentra is an adaptive learning workspace built with FastAPI, React + TypeScript,
PostgreSQL, LangChain/LangGraph, local CPU embeddings, and Qdrant retrieval.
PostgreSQL owns conversations, attachments, assessments, learner evidence, events,
notifications and settings; browser caches accelerate navigation and synchronization.

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
  HTTP-only sessions, generic signed external SSO, EduVerse provisioning,
  mandatory profile onboarding, optional calibration, evidence-backed memories,
  and shared Light/Dark/System themes.
- **Diagnostics:** correlated request/job/tool/model traces with execution timing,
  supplied/skipped/defaulted parameter shapes and sanitized failures. Query and
  response bodies are not retained in logs.

## Quick start

Docker Desktop/Engine and Docker Compose are sufficient for the container setup.
Node.js 24 LTS and Python 3.12 are needed only for native development/testing.

```powershell
Copy-Item .env.example .env
```

Configure `DATABASE_URL` with a complete hosted PostgreSQL URL and its required
SSL options. Set `AI_MODEL`, `AI_BASE_URL` and `AI_API_KEY` for an OpenAI-compatible
provider. Configure `QDRANT_URL`, `QDRANT_API_KEY` and `QDRANT_COLLECTION` for RAG
readiness. `VITE_API_URL` is built into the frontend bundle and must be reachable
from the browser; its local default is `http://localhost:8000`.

```sh
docker compose up --build -d --wait --wait-timeout 180
```

Default services are `backend`, `frontend`, `rag-worker`, `assessment-worker` and
`events-worker`. Local PostgreSQL is optional:

```sh
docker compose --profile local-db up -d postgres
```

For that profile, set `DATABASE_URL=postgresql://mentra:mentra_local@postgres:5432/mentra`
for containers; native clients use the configured localhost port instead. The API
applies Alembic migrations before starting. The repository migration head is
`20261017_0027`; verify the actual database revision rather than assuming deployment.

| Address | Purpose |
| --- | --- |
| `http://localhost:5173` | Frontend |
| `http://localhost:8000/docs` | OpenAPI |
| `http://localhost:8000/api/v1/health` | Lightweight liveness |
| `http://localhost:8000/api/v1/health/ready` | Configuration, embeddings and Qdrant readiness; no paid model call |

Guests use `/login` or `/register`, then complete onboarding. Use the same hostname
for frontend/backend locally so cookie policy works.

## Workspace routes

| Route | Feature |
| --- | --- |
| `/`, `/chat/:conversationId` | New/saved chat |
| `/library`, `/library/new`, `/library/:documentId` | Materials and source views |
| `/assessments` | Saved practice, attempts and grading |
| `/progress` | Learning Progress; `?tab=events` opens the agenda |
| `/events` | Redirect to the Progress Events tab |
| `/notifications` | Notifications inbox |
| `/settings` | Profile, calibration, account/preferences; `?tab=memories` opens memories |
| `/onboarding`, `/calibration` | Profile setup and optional calibration |

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

## Architecture and documentation

Domain services own their contracts and persistence. Chat owns turns and
publication; Learner owns concepts/evidence/mastery; RAG owns ingestion/retrieval;
Events owns schedules; Notifications owns inbox delivery. Orchestration calls
public facades rather than writing another domain's tables. Shared Documents,
Vision and Speech capabilities keep local processing independent of the LLM.

| Documentation | Scope |
| --- | --- |
| [Backend atlas](docs/Mentra_Backend_Map.md) | Module and file guide, feature dependencies, APIs, storage, and worker flows |
| [Setup](docs/SETUP.md), [identity/PostgreSQL](docs/identity-and-postgresql.md) | Environment, migrations, native development and identity |
| [Persistent chat](docs/persistent-chat.md), [context summaries](backend/app/chat/SUMMARIES.md) | Storage, synchronization, attachments and model context |
| [History and memory](docs/history-management.md) | Exact history recovery and durable user memories |
| [Chat assessments](docs/chat-assessments.md), [interactions](docs/chat-interactions.md) | Generation, local answers, submission and grading |
| [Learning Progress](docs/learning-progress.md), [Events](docs/events.md), [Notifications](docs/notifications.md) | Understanding, agenda, capture and reminder delivery |
| [Web search/research](docs/web-search.md), [voice](docs/voice-input.md) | Provider tools and CPU transcription |
| [RAG](docs/rag.md), [Documents](backend/app/documents/README.md), [Vision](backend/app/vision/README.md) | Source processing and retrieval |
| [LangChain](backend/app/langchain/README.md), [logging](docs/backend-logging.md) | Model/tool orchestration and diagnostics |
| [Prompt efficiency](docs/prompt-efficiency.md) | Prompt sizes, provider caching and validation evidence |
| [Backend standards](backend/standards.md), [frontend standards](frontend/standards.md) | Contributor conventions |

Implementation plans and dated verification reports preserve design/rollout
history; they are not a current feature checklist or proof of the deployed state.
Pinned dependencies live in `backend/requirements.txt` and frontend manifests.

## Verification

Use an explicit, disposable `TEST_DATABASE_URL`; tests never fall back to the
application database. Backend fixtures apply migrations in isolated schemas.
See the setup guide for test commands and limitations of image-only test runs.
Frontend checks include production build, `npm run check:theme`, and Playwright
mock/real API configurations. Dated `*-verification.md` reports describe their
original run and scope, rather than a continuously updated total test count.

Combined service logs are available with:

```sh
docker compose logs -f backend rag-worker assessment-worker events-worker
```

Daily JSON diagnostics are persisted at `logs/backend/backend-YYYY-MM-DD.log`.
`LOG_PARAMETER_DETAILS=false` disables detailed parameter shapes.


Frontend containers serve on internal port **8080**, mapped to local **5173**, as
nonroot with a read-only root filesystem and a temporary `/tmp`. See the
[product hardening and deployment notes](docs/Product_Deployment_Hardening_2026-10-18.md)
and [saved-chat search contract](docs/saved-chat-search.md).
