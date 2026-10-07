# Mentra

Mentra is a clean, monorepo-based foundation for an adaptive AI learning assistant. The current project is intentionally scoped to a working full-stack starter: a FastAPI backend, a React + TypeScript frontend, SQLite-ready persistence, and Docker-based orchestration.

## What Mentra currently contains

- FastAPI backend with health checks and modular route registration
- Centralized FastAPI error responses for application, HTTP, validation, and unexpected errors
- React + TypeScript + Vite + Tailwind CSS frontend with a responsive, routed learning workspace
- Local-first workspace shell with Chat, Library, Progress, Assessments, and Settings routes
- Server-backed AI chat with in-memory conversation context and Markdown responses
- Multi-stage frontend image serving the built app with Nginx
- SQLite-ready backend configuration and database layer
- Docker Compose setup for backend and frontend services
- Provider-independent LangChain chat model factory for OpenAI-compatible endpoints
- Local, image-baked BGE embeddings kept independent from chat models
- Remote Qdrant Cloud adapter with collection dimension and embedding-identity validation
- Environment-based configuration through `.env` values

## Project structure

```text
mentra/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   └── routes/
│   │   │       └── health.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── exception_handlers.py
│   │   │   ├── exceptions.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── database.py
│   │   │   └── models/
│   │   ├── schemas/
│   │   │   └── errors.py
│   │   ├── langchain/
│   │   │   ├── model_factory.py
│   │   │   └── README.md
│   │   ├── rag/
│   │   │   ├── embeddings.py
│   │   │   ├── qdrant_store.py
│   │   │   ├── vector_store.py
│   │   │   └── README.md
│   │   ├── __init__.py
│   │   └── main.py
│   ├── tests/
│   ├── bake_embedding_model.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .dockerignore
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/            # Chat message, composer, and empty state
│   │   │   ├── navigation/      # Responsive workspace sidebar
│   │   │   └── ui/
│   │   │       ├── Button.tsx
│   │   │       ├── Card.tsx
│   │   │       ├── Input.tsx
│   │   │       ├── Spinner.tsx
│   │   │       └── Textarea.tsx
│   │   ├── hooks/
│   │   ├── layouts/             # Shared routed application shell
│   │   ├── pages/               # Chat, Library, Progress, Assessments, Settings
│   │   │   └── chat/            # Isolated sample conversations
│   │   ├── services/
│   │   ├── styles/
│   │   ├── types/
│   │   ├── utils/
│   │   │   └── cn.ts
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── vite-env.d.ts
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── index.html
│   ├── nginx.conf
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── data/
├── .env.example
├── .dockerignore
├── .gitignore
├── docker-compose.yml
├── backend/standards.md
├── frontend/standards.md
└── README.md
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

The values configure the OpenAI-compatible chat endpoint, local embedding model, Qdrant Cloud collection, CORS, and SQLite path. Set `AI_MODEL`, `AI_BASE_URL`, and `AI_API_KEY` before starting. Set the Qdrant values for readiness to pass. `VITE_API_URL` is baked into the frontend bundle when its image is built, so it must be an address reachable from the user's browser (the default is `http://localhost:8000`).

## Run with Docker

```bash
docker compose up --build
```

## Frontend URL

- http://localhost:5173

The app opens directly in Chat; no Mentra login is required. Google Drive is a future optional backup/restore integration, not an access requirement. Chat turns are sent to the configured AI provider through the backend and kept only in frontend memory; they are not persisted.

## Workspace routes

- `/` — Chat
- `/library` — study material placeholder
- `/progress` — learning profile placeholder
- `/assessments` — practice and assessment placeholder
- `/settings` — local-first settings and optional backup placeholder

## Backend URL

- http://localhost:8000

## Swagger/OpenAPI URL

- http://localhost:8000/docs

## Health endpoint

- http://localhost:8000/api/v1/health
- http://localhost:8000/api/v1/health/ready (configuration and dependency diagnostics)

## Stop and rebuild

```bash
docker compose down

docker compose up --build
```

To rebuild without cache:

```bash
docker compose build --no-cache
```

## LangChain and RAG boundaries

- `backend/app/langchain/`: model factory for OpenAI-compatible chat endpoints; chat configuration does not control embeddings.
- `backend/app/rag/`: local embedding interface/implementation and Qdrant vector-store adapter. Ingestion, chunking, and retrieval workflows are not implemented yet.

Switch compatible chat providers by changing `AI_BASE_URL`, `AI_MODEL`, and `AI_API_KEY`. The local embedding model is baked into the backend image; changing it requires an image rebuild and Qdrant reindex. Readiness verifies configuration and Qdrant without invoking the chat model. Qdrant connectivity is checked by readiness rather than liveness, so an outage does not prevent the backend health endpoint from responding.

## Engineering standards

- [Backend contributor standards](./backend/standards.md)
- [Frontend contributor standards](./frontend/standards.md)
- [Teammate setup guide](./docs/SETUP.md)

The frontend shared API client is in `frontend/src/services/api.ts`. Backend errors use a consistent `{ "error": { "code": "...", "message": "..." } }` structure; validation errors may include field details.
