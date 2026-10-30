# Production deployment and recovery

This runbook follows the repository's Docker Compose deployment: a static Nginx
frontend, FastAPI API, five background workers, PostgreSQL, private Cloudinary
originals and Qdrant. No hosted application platform is prescribed. An optional
host Nginx TLS template is supplied in `deploy/nginx.production.conf.template`;
certificate issuance/renewal and installing it require the actual infrastructure.
See the [dated verification record](production-readiness-2026-10-25.md) for what was
actually checked locally and against configured providers.

## Required configuration

| Setting or resource | Release requirement |
| --- | --- |
| `APP_ENV` | `production` for security policy; storage namespace selection is independent through `FILES_ENVIRONMENT` |
| `FILES_NAMESPACE`, `FILES_ENVIRONMENT` | Original paths are `FILES_NAMESPACE/(FILES_ENVIRONMENT or APP_ENV)`. For a fresh database use `mentra/production`; for existing originals preserve their historical namespace/suffix explicitly before changing APP_ENV |
| `FRONTEND_ORIGIN`, `CORS_ORIGINS` | Explicit public HTTPS origins, without paths, credentials or wildcards; startup validates and canonicalizes host case, IDNA, default ports and trailing slashes for all API/worker processes |
| `VITE_API_URL` | Public HTTPS API origin reachable by browsers, with no path/query/fragment; changing it requires a frontend build |
| Cookie policy | Secure is automatic outside development/test; set `AUTH_COOKIE_SECURE=true` explicitly. Use `lax` for same-site deployment; `none` requires HTTPS and remains subject to browser third-party-cookie restrictions |
| Sessions | New bearer sessions default to one hour; new browser sessions default to an absolute 30-day lifetime. Existing session records are preserved |
| `DATABASE_URL` | Complete PostgreSQL URL and provider-required TLS settings; use a migration-capable role for deployment and least privilege compatible with application operations |
| `CLOUDINARY_URL` | Server-only authenticated storage credentials, shared by the API, RAG, assessment and file-cleanup workers; never put them in `VITE_*` |
| Qdrant | `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, matching distance/model/revision; provision before the launch gate |
| AI | Compatible `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`; sufficient quota and a small live synthetic check |
| Proxy trust | `FORWARDED_ALLOW_IPS` must identify the actual trusted proxy address. Never trust arbitrary client forwarding headers with `*` |
| Published ports | For a TLS proxy on this host, set `BACKEND_BIND_ADDRESS=127.0.0.1` and `FRONTEND_BIND_ADDRESS=127.0.0.1`. Otherwise restrict published ports with the actual network/firewall design |
| Logs | `./logs/backend` must be writable by UID/GID 10001. All runtime services use the shared directory; retain/ship diagnostics according to operational requirements |
| Pool capacity | Default Compose maximum is ten application connections: API five plus five workers at one each, excluding migration/admin connections. Budget for overlapping old/new deployments and other database consumers |

Keep `.env` private and out of source control. Settings representations and startup
validation errors omit secret inputs. Do not publish environment dumps, signed
download URLs, diagnostic payloads or database dumps.

The backend and workers run as UID/GID 10001, without Linux capabilities and with
privilege escalation disabled. The frontend runs unprivileged, with a read-only
root and temporary `/tmp`. The checked-in Python lock constrains the verified
Linux Python 3.12 runtime; review, regenerate and audit it alongside direct pins.
CPU Torch is installed from the official CPU wheel index. Builds perform `pip check`.

## Production configuration preparation

The domain/hosting setup has **not been selected**. Do not copy the synthetic
`launchgate.example.org` browser-drill addresses into a real deployment. Copy
`.env.production.example` to private `.env.production` and fill every empty
required value with the chosen infrastructure's values. Keep it mode 0600 or
equivalent host ACLs. A deployment secret manager can inject these same variables;
no secret belongs in frontend build arguments or Git. Shell variables override
the selected environment file, both in Compose and the offline preflight.

```sh
python backend/scripts/validate_production.py --env-file .env.production
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml config --quiet
```

The production override requires versioned API/frontend images, enables Secure
cookies, requires browser/API values, enables the frontend release-build guard,
and replaces both published listeners with loopback mappings. Requires Compose
2.24.4+ for `!override` ([Docker merge reference](https://docs.docker.com/reference/compose-file/merge/)); actual validation used Compose 5.6.0.
Do not omit the override for a public launch. A reviewed private proxy network
can use explicit listener IPs with the preflight's `--allow-network-bind` flag;
this flag does not configure a firewall.

The preflight is offline: it validates syntax, required values, TLS settings,
release tags, proxy trust and listeners. Database TLS must have exactly one secure
`sslmode`; conflicting duplicate modes are rejected. It cannot establish DNS ownership,
certificate validity, quotas, credentials, registrable-domain cookie policy or
remote reachability. The release guard rejects a localhost/non-HTTPS API URL.
The public `VITE_API_URL` is embedded at build time; API/workers consume runtime
variables. Browser API traffic uses credentialed fetch and durable SSE activity;
there is no WebSocket endpoint requiring an upgrade rule.

The supplied Nginx template assumes **distinct frontend/API hosts** with the same
registrable domain for `SameSite=lax` cookies, and a proxy on the Docker host.
Replace all template placeholders, install real certificates/renewal, adjust the
API port if changed, and run `nginx -t` before reload. It replaces incoming
forwarded headers, disables API buffering/cache and allows 130-second upstream
idle waits. The default 26 MiB proxy request cap accommodates 25 MiB originals
plus multipart overhead; adjust it with a larger application upload budget.
Different registrable domains require a separately verified cookie design
(`SameSite=None` remains subject to browser third-party-cookie restrictions).

`FORWARDED_ALLOW_IPS` identifies the source IP/CIDR **seen inside the API
container**, which can be a Docker bridge/gateway address even for a host proxy.
It is not necessarily `127.0.0.1`. Discover and restrict it on the chosen host;
never use `*` or trust arbitrary client-supplied forwarding headers. Nothing in
these templates opens a public listener, changes DNS, or provisions TLS.

Trace: browser → public frontend TLS proxy → static Nginx; credentialed browser
fetch/SSE → API TLS proxy → Uvicorn → authenticated owner-scoped PostgreSQL reads
and admission leases. Model work uses server-only AI credentials; originals use
authenticated Cloudinary. Durable jobs in PostgreSQL are consumed by the five
workers; RAG reads private originals, runs local extraction/E5 and writes derived
Qdrant points. All worker/API instances share database, storage namespace and
matching embedding/index settings.

## Preserve data before deployment

1. Record the running image digests, configuration and actual Alembic revision.
2. Take a PostgreSQL backup/snapshot and verify recovery into a separate database.
   A logical backup can use `pg_dump --format=custom --file=mentra-before-release.dump`
   with PostgreSQL connection variables and a private `PGPASSFILE`; keep credentials
   out of command histories. Restore only into a newly created disposable database
   with `pg_restore --exit-on-error --no-owner --dbname=mentra_restore_check mentra-before-release.dump`.
3. Retain the Cloudinary originals and registry/binding metadata for the same
   recovery point. A PostgreSQL backup alone cannot reconstruct externally stored
   original bytes. Verify provider backup/retention and a representative private
   original restore. Qdrant is derived and can be rebuilt from preserved sources.
   Freeze writes/ingestion for the coordinated release recovery point. Take it
   immediately before migration/deployment; a stale development dump is not a
   launch backup. Separately agree the ongoing maximum data-loss window (RPO),
   recovery-time target (RTO), schedule, retention, off-host encryption and restore
   owner. None has been selected by this engineering run.
   A logical dump contains account/session hashes, learner state, ownership,
   immutable evidence, conversations, job state, file registry/bindings and source
   provenance; it does not contain Cloudinary bytes, roles/provider settings,
   application secrets, certificates or model images. Retain configuration and
   compatible image/model digests privately alongside the recovery plan.
4. If the database is older than `20261020_0028`, inspect legacy records:

```sql
SELECT count(*) FROM chat_attachment;
SELECT count(*) FROM rag_document_version;
SELECT count(*) FROM assessment_attempt WHERE source IS NOT NULL;
```

Run these queries only against the pre-storage schema where those columns exist.
The storage migration refuses to proceed if any count is nonzero. A populated
legacy installation needs a reviewed preservation/backfill procedure before
upgrade. Never delete original records merely to make the migration pass. No
general legacy-byte backfill tool is supplied by this change.

For a current storage schema, inventory namespace suffixes before enabling
production mode (counts only; do not publish the output):

```sql
SELECT environment, split_part(public_id,'/',1) AS namespace,
       split_part(public_id,'/',2) AS suffix, count(*)
FROM file_asset GROUP BY 1,2,3;
```

Set `FILES_NAMESPACE` and `FILES_ENVIRONMENT` to the preserved values, identically
for API and file/RAG/assessment workers. Do not rename original provider IDs.
Mixed historical namespaces require a reviewed consolidation/recovery plan;
there is no automatic cross-environment fallback.

Drain pending ingestion before replacing workers: the PDF safety update changes
the recorded parser revision. Existing READY material remains searchable, but an
older queued/running generation deliberately refuses a different parser config.
Inspect `SELECT state, count(*) FROM rag_job GROUP BY state;`; if old work cannot
drain, preserve the job/records and explicitly reindex that material with the new
runtime. No vector reset is needed for the validated embedding-library updates.

## Build, migrate and provision

For production, use the complete file selection on **every** command below.
On a POSIX deployment shell this helper avoids accidentally dropping the override:

```sh
dc() { docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml "$@"; }
```

Use `dc` instead of `docker compose` in the following sequence for production.
The bare commands remain usable for local development.

```sh
docker compose config --quiet
docker compose build backend frontend
docker compose run --rm --no-deps backend python -m pip check
docker compose run --rm --no-deps backend python -m app.db.migrate
docker compose run --rm --no-deps backend python -m alembic current
docker compose run --rm --no-deps backend python -m alembic check
docker compose run --rm --no-deps backend python -m scripts.rag_admin initialize
docker compose up -d --force-recreate --wait --wait-timeout 180
docker compose ps
```

Repository head is `20261021_0030`. The migration runner serializes upgrades with
a bounded advisory lock; API startup also verifies the revision. The `initialize`
operator command creates a missing collection and payload indexes and validates
existing embedding identity; it does not reset an existing collection. An
incompatible collection requires a separately planned reindex. Preserve E5 model
identity/revision and 384 dimensions. Readiness validates the collection and does
not create it. Do not use `reset-embeddings --apply` for ordinary deployment.

Compose starts `backend`, `frontend`, `rag-worker`, `assessment-worker`,
`events-worker`, `summarizer` and `files-worker`. `--wait` checks container liveness,
not whole-product readiness or worker job throughput. The optional local PostgreSQL
profile is for an explicitly configured local database; hosted PostgreSQL remains
external. Never use `docker compose down -v` as an update step.

## Launch gate

| Check | Required evidence |
| --- | --- |
| HTTP | Public HTTPS frontend, API liveness, `/api/v1/health/ready` HTTP 200, SPA deep-link refresh and correct frontend API URL |
| Identity | Register/login/onboard, HTTP-only Secure cookie, refresh, logout, password change, and another-account access denial |
| Chat/AI | One synthetic completed response, Stop/recovery, saved history after refresh; live credentials/quotas checked separately from readiness |
| Files/RAG | Synthetic private upload/download, ingestion to ready, owner-scoped retrieval/citation, deletion and eventual provider/index cleanup |
| Durable work | Grading and evidence, reminders/notifications, summary queues and file cleanup progress; inspect retry/failed queues rather than relying on container status |
| Operations | Proxy preserves streaming and has suitable request/idle deadlines; upload limits permit configured multipart overhead; logs rotate/persist; database and storage backups have a demonstrated restore |
| Resources | Representative concurrent load measured against deployment database connection limits, CPU/memory, provider quotas and actual network latency |

Set browser/public URLs to the deployment's actual origins. Production is not
verified by tests using deterministic model/storage fixtures, nor by a successful
local Docker health check. The project does not ship a TLS terminator; configure
and verify the chosen proxy, certificate renewal, firewall and access policy.

## Failure recovery and rollback

| Symptom | Action |
| --- | --- |
| API exits on startup | Inspect sanitized logs, database connectivity/head, private-storage configuration and production browser origins. Do not disable validation to launch |
| Liveness succeeds but readiness fails | Inspect individual database/model/embedding/Qdrant checks. Provision a missing collection with `initialize`; never erase an incompatible one without a reindex plan |
| Browser login seems lost | Verify public origins, HTTPS cookie flags, hostname/site consistency and browser cookie policy; inspect safe HTTP status/code |
| Jobs stop progressing | Inspect queue state/leases and corresponding worker logs. Restart the failed worker after fixing configuration; preserve operation IDs/receipts to avoid duplicate effects |
| File deletion is deferred | Leave the durable registry intact. Correct provider/network errors and let `files-worker` retry after its fenced lease/backoff; original bytes may remain externally until successful deletion |
| Application rollback | Restore prior compatible API/frontend/worker images together and retain configuration. These fixes add no schema revision. Do not downgrade a database containing newer incompatible records |
| Storage-schema rollback | `20261020_0028` downgrade refuses populated registries. Use a coordinated verified database/original-byte restore or reviewed reverse export; schema downgrade cannot recreate deleted bytes |

Use existing durable retry controls and inspect unknown outcomes before repeating
writes. Database ownership, immutable evidence and provenance remain canonical.
Do not infer mastery from a confirmation, a queued job, or a successful HTTP send.

## Ordered first-release acceptance and recovery

1. Choose the host and public frontend/API origins; configure network policy,
   certificate renewal, trusted proxy source addresses, provider credentials and
   quotas. Review database connection allowance: API five + five workers one each,
   plus deployment/admin clients and any rollout overlap.
2. Fill the private release environment, preserve existing storage suffixes, run
   offline preflight and merged Compose validation. On a Linux host prepare
   `logs/backend` for UID/GID 10001 with a restricted writable directory.
3. Record prior compatible image digests and private configuration. Quiesce writes
   and drain ingestion if retaining existing data. Take and verify a coordinated
   database/original-byte recovery point; resolve any legacy migration refusal.
4. Build/version API and frontend with the actual HTTPS API origin. Use the
   validated commands above to migrate to `20261021_0030`, check drift, and
   initialize the collection without resetting it. Use a migration-capable
   credential for DDL; supply the intended runtime credential for service startup.
5. Start API/frontend/workers with the production override. Install/test the TLS
   proxy on the chosen host only with deployment authorization. Confirm readiness,
   Secure/HTTP-only cookie login/refresh/logout/password change, denied foreign
   owner access, and streamed chat Stop/recovery through the real public origin.
6. Verify one private original, ingestion, retrieval/citation, deletion/cleanup and
   durable worker queues. Check actual pool/CPU/memory/provider metrics; apply a
   conservative workload on the real deployment and approve an initial traffic
   limit. Local 1–8 concurrency measurements are not a production capacity claim.
7. For an application rollback, stop/drain workers and pause writes, restore the
   prior private configuration and compatible **paired** frontend/API image
   references, validate, then run `dc up -d --no-build --force-recreate --wait`.
   Check readiness, identity, sources and queue progress. Do not rebuild old tags
   from new source and do not run `down -v`. A previous image unaware of
   `FILES_ENVIRONMENT` needs its matching historical APP_ENV/configuration;
   verify namespace compatibility before choosing it as a rollback target.
8. For data loss, restore into a new database first, verify counts/constraints and
   actual domain reads, restore missing originals at their preserved public IDs,
   verify SHA-256 and byte counts and reconcile provider `asset_id`/`version`
   receipts. Keep the registry, bindings, Cloudinary environment and namespace
   aligned. Cut over only after recovery acceptance; never overwrite the source
   database to experiment.
9. If only Qdrant was lost, fence ingestion and provision a new compatible empty
   collection with `rag_admin initialize`. For each explicit preserved learner,
   run `python -m scripts.rag_admin rebuild --learner-id <owner-uuid> --run-id <stable-run-uuid> --apply`.
   Reuse the run UUID for uncertain retries. Start ingestion and wait for complete
   owned generations; inspect `rag_admin health`, queue state and real retrieval.
   This reconstructs vectors from preserved sources, not missing original bytes.
   Do not use global `reset-embeddings --apply` as a routine recovery shortcut.
