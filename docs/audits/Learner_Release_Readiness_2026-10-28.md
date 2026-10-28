# Learner release readiness — October 28, 2026

The learner/topic/subskill release and shared Send/Pause/Resume/Retry control are implemented, reviewed and running in the local Docker stack. The public deployment configuration still needs the installation's actual domains, HTTPS proxy and certificates. This record does not claim public deployment or measured student learning gains.

## Final review fixes

| Gap | Resolution |
| --- | --- |
| Browser disconnect during Resume admission | A service-owned admission task finishes safely, matching Send behavior. |
| Pausing an older background assessment after newer chat messages | Preserve the conversation sequence; accept a repeated pause while the source response remains failed. |
| A stale assessment-card Stop racing a newer Resume | Fence the acknowledgement with the job revision and roll back stale requests. |
| Resuming expired assessment batches while the sweeper is unavailable | Enforce expiry during owned Resume admission as well as worker cleanup. |
| Resume exceeding the owner's background queue budget | Include pending resumed work in the transactional capacity check. |
| Typing during background assessment generation | The shared control becomes Send; clearing the draft restores Pause. Paused/failed work similarly restores Resume/Retry. |
| Release observability and provenance | Production defaults to JSON logs with parameter details disabled; both images accept an OCI source-revision label. |

## Verification evidence

| Check | Result |
| --- | --- |
| Final focused backend suite | 68 passed, including the race fixes, ownership, durable continuation, topic persistence and assessment targeting. |
| Browser flows | Nine passed, including authenticated assessment creation and grading, topic navigation/selection and response controls. Four final desktop/mobile composer checks also passed after the background-draft fix. Counts overlap previous suites. |
| Build and static checks | TypeScript/Vite production build, theme/UI checks, targeted Ruff and whitespace checks passed. The existing large-bundle advisory remains. |
| Production frontend dependency audit | Zero reported vulnerabilities with development dependencies omitted; this is not a full application security audit. |
| Large synthetic history and migration round trip | [Storage evidence](topic-storage-verification.json): 10,000 subskills, bounded detail/candidate packets, preserved synthetic learners through downgrade/reupgrade. These timings are not a production latency guarantee. |
| Configured-model behavior | [Topic organization](topic-organization-live-verification.json), [continuation classification](response-continuation-live-verification.json), and [production-image runtime](learner-release-runtime-verification.json) used synthetic records only. |
| Production-image HTTP checks | Declared/chunked body limits across five media types, small JSON, upload budgets, huge Range rejection and provider-close/cancellation lease release passed. |
| Production-mode runtime | Readiness passed for database, AI, embeddings and Qdrant. Generated an actual question, paused/resumed it, rejected stale Stop, published owned topics, withheld private grading keys and created no mastery from generation. Secure/HttpOnly cookie and foreign-origin rejection passed. |
| Local migration | [Preservation evidence](learner-release-migration-verification.json): `20261025_0031` → `20261027_0034`; all 84 existing application-table row counts unchanged. |
| Local stack | Seven Compose services running; backend/frontend healthy, API ready, frontend HTTP 200 with `nosniff`, all five workers at zero restarts during acceptance. |

## Preservation and cleanup

The private, ignored `data/backups/learner-release-20261028/` directory contains a checked PostgreSQL archive and manifest with checksum and pre-migration counts. It also contains the previous frontend's saved assets/configuration. Rollback images are `mentra-backend:pre-learner-20261028` and `mentra-frontend:pre-learner-20261028`; the frontend rollback image was reconstructed from the previous running container because its original image content was unavailable. These are retained recovery assets.

Temporary test containers, their disposable PostgreSQL volume, browser result directories and this task's scratch helpers/logs are removed after verification. Regression tests, synthetic audit evidence, existing application logs, student data, storage and recovery assets are retained. No global Docker or filesystem purge is part of the cleanup.

## Public release procedure

Use the existing [production runbook](../production-readiness.md) and private `.env.production.example` template. Populate real HTTPS browser/API origins, trusted proxy addresses and deployment credentials; preserve the existing file-storage namespace. The current local frontend targets the local API and must be rebuilt for the public origin. Set `MENTRA_REVISION` to the source commit; choose versioned backend/frontend image tags, rather than `latest`, in the private production environment.

```powershell
python backend/scripts/validate_production.py --env-file .env.production
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml build backend frontend
```

Take and verify a fresh deployment-database backup, stop old writers, run the explicit migration command, then start all services together:

```powershell
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml stop backend rag-worker summarizer assessment-worker events-worker files-worker
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml run --rm --no-deps backend python -m app.db.migrate
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml up -d --no-build --wait
```

Verify public DNS/TLS, proxy forwarding, browser login/secure cookies, authenticated assessment pause/resume, uploads/downloads and worker readiness through the actual HTTPS origins. The isolated production-mode check used a reserved synthetic origin; it does not verify those public infrastructure properties.

For rollback, stop writers and preserve the database/checkpoints before changing application images. Prefer rolling forward for in-flight paused work: older code does not understand its continuation semantics. Keep the additive schema; destructive downgrades intentionally reject populated memberships or retained continuation receipts. Restoring the pre-release database loses later writes and requires an explicit recovery decision.

## Deliberate boundaries

Time reduces projected recall support, not historical mastery. Retention remains an explainable heuristic requiring calibration. Broad topics organize independently scored subskills without inventing syllabus coverage. Ordinary-chat automatic private learner-context prefetch remains disabled following the automatic approval review rejection; existing authorized on-demand retrieval remains available. See the implementation report for teaching-effectiveness, taxonomy-recall and ranking-scale evaluation limits.
