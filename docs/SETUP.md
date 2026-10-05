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

No credentials are required for the current application. The Compose defaults are ready to run. `.env` is ignored by Git; commit changes to `.env.example`, never local secrets.

The supported settings in `.env.example` are:

| Variable | Default | Current use |
| --- | --- | --- |
| `APP_ENV` | `development` | Backend environment setting |
| `BACKEND_HOST` | `0.0.0.0` | Backend listener address in its container |
| `BACKEND_PORT` | `8000` | Backend listener and published host port |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Primary allowed browser origin |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins |
| `SQLITE_DB_PATH` | `/data/mentra.db` | SQLite file path; keep it under `/data` so the Compose mount persists it |
| `LLM_PROVIDER` | `none` | Reserved backend configuration; no LLM service is started |
| `VECTOR_DB_PROVIDER` | `none` | Reserved backend configuration; no vector database is started |
| `VITE_API_URL` | `http://localhost:8000` | Frontend build-time API URL; must be reachable by the browser |

The frontend port is currently fixed at host port `5173` (container port `80`). If you change `BACKEND_PORT`, also update `VITE_API_URL` and the CORS origins to match the ports/origin you use.

## 4. Start Mentra

From the repository root:

```sh
docker compose up --build
```

Compose builds and starts services `backend` and `frontend`. The backend container is `mentra-backend`; the frontend container is `mentra-frontend`. The frontend waits for the backend health check before starting.

## 5. Verify the app

- Open the workspace: http://localhost:5173
- Open the backend: http://localhost:8000
- Open Swagger/OpenAPI: http://localhost:8000/docs
- Check API health: http://localhost:8000/api/v1/health
- View service status: `docker compose ps`

The health endpoint is `GET /api/v1/health` and currently returns `{"status":"ok","service":"mentra-api"}`. The Compose backend health check uses this endpoint; the frontend health check requests its root page.

Current workspace routes are `/`, `/library`, `/progress`, `/assessments`, and `/settings`. Chat responses and recent conversations are preview-only; the current backend does not provide chat, upload, account, assessment, progress, or backup APIs.

## 6. Stop or update

Stop the containers while preserving the local SQLite data:

```sh
docker compose down
```

Pull the latest project changes and rebuild/restart:

```sh
git pull --ff-only
docker compose up --build
```

SQLite is bind-mounted from the repository's `data/` directory. Do not delete that directory or its database file if you want to retain local data.

## Troubleshooting

- **Docker connection error:** Start Docker Desktop or the Docker Engine, then retry `docker compose up --build`.
- **Port already in use:** Free ports `5173` and `8000`. If changing the backend port, update `BACKEND_PORT`, `VITE_API_URL`, and the CORS origins in `.env`, then rebuild.
- **Backend not healthy:** Check logs with `docker compose logs backend`; confirm `SQLITE_DB_PATH` stays under `/data`.
- **Frontend is stale after configuration changes:** Rebuild with `docker compose up --build`; `VITE_API_URL` is embedded at frontend build time.

For code conventions, see [frontend/standards.md](../frontend/standards.md) and [backend/standards.md](../backend/standards.md).
