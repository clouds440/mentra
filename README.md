# Mentra

Mentra is a clean, monorepo-based foundation for an adaptive AI learning assistant. The current project is intentionally scoped to a working full-stack starter: a FastAPI backend, a React + TypeScript frontend, SQLite-ready persistence, and Docker-based orchestration.

## What Mentra currently contains

- FastAPI backend with health checks and modular route registration
- Centralized FastAPI error responses for application, HTTP, validation, and unexpected errors
- React + TypeScript + Vite + Tailwind CSS frontend with a responsive, routed learning workspace
- Local-first workspace shell with Chat, Library, Progress, Assessments, and Settings routes
- Sample-only chat preview with Markdown content, composer keyboard behavior, and honest empty states
- Multi-stage frontend image serving the built app with Nginx
- SQLite-ready backend configuration and database layer
- Docker Compose setup for backend and frontend services
- Clear separation for future LangChain orchestration and RAG work
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
│   │   │   └── README.md
│   │   ├── rag/
│   │   │   └── README.md
│   │   ├── __init__.py
│   │   └── main.py
│   ├── tests/
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

The values are used for the backend and frontend configuration, including CORS and the SQLite path. `VITE_API_URL` is baked into the frontend bundle when its image is built, so it must be an address reachable from the user's browser (the default is `http://localhost:8000`).

## Run with Docker

```bash
docker compose up --build
```

## Frontend URL

- http://localhost:5173

The app opens directly in Chat; no Mentra login is required. Google Drive is a future optional backup/restore integration, not an access requirement. Chat content in this starter is local preview data and is not sent to an AI service or persisted.

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

- `backend/app/langchain/`: reserved for LLM orchestration, prompt management, model/provider abstractions, and future agent orchestration logic.
- `backend/app/rag/`: reserved for ingestion, chunking, embeddings, vector retrieval, and document intelligence workflows.

These are intentionally separated so future work can evolve independently without mixing concerns.

## Engineering standards

- [Backend contributor standards](./backend/standards.md)
- [Frontend contributor standards](./frontend/standards.md)
- [Teammate setup guide](./docs/SETUP.md)

The frontend shared API client is in `frontend/src/services/api.ts`. Backend errors use a consistent `{ "error": { "code": "...", "message": "..." } }` structure; validation errors may include field details.
