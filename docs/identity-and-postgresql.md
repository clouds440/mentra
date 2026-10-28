# PostgreSQL and identity foundation

Mentra uses SQLAlchemy 2.x with psycopg and Alembic. `DATABASE_URL` accepts a standard
`postgresql://` or `postgres://` URL, including PostgreSQL SSL/query options. There are
no provider-specific APIs. This is a fresh schema; no SQLite data-transfer tooling is needed.

## Setup and migrations

Copy `.env.example` to `.env` and set `DATABASE_URL` to your complete Supabase (or other
hosted PostgreSQL) connection URL. The backend runs migrations before serving requests.
Default Compose startup does not launch or wait for a local database.

For optional local development, run `docker compose --profile local-db up -d --wait postgres`
first. PostgreSQL 17 persists in the `mentra_postgres` named volume. Set `DATABASE_URL` to
`postgresql://mentra:mentra_local@postgres:5432/mentra` for Docker services, then start the
remaining services. Local credentials are never merged into a hosted connection URL.

## Applying schema updates

Alembic revisions in `backend/alembic/` are the only schema-change source. The backend
Dockerfile runs `python -m app.db.migrate` before starting the API. Migration failure
prevents API startup; the existing PostgreSQL advisory lock serializes concurrent starts.
Migrations run at container startup, so image builds need no live database credentials.

For an explicit manual run use `docker compose run --rm backend python -m app.db.migrate`.
Use a direct PostgreSQL or session-pooler connection for migrations; the transaction
pooler cannot retain the advisory lock. Keep database credentials in server configuration.

For native Python, use `127.0.0.1` and the published PostgreSQL port in `DATABASE_URL`.
From the repository root, after installing `backend/requirements.txt`:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.db.migrate
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

`app.db.migrate` serializes migration runners with a PostgreSQL session advisory
lock. It commits nonblocking acquisition probes before waiting, avoiding snapshot
deadlocks with concurrent index builds, and bounds acquisition to 300 seconds. Startup
checks the Alembic revision and fails clearly if migrations are missing; it never creates
tables. For subsequent changes, generate and review an Alembic revision, then upgrade.
The repository head is `20261021_0030`. Later revisions extend the original identity/profile/Library/chat/memory/Events foundations with proposals, notifications, assessment workflows, web search and private conversation summaries.
Compare the actual database revision with this head before starting the API;
repository migration files do not imply a database was already upgraded.
The initial revision includes native UUIDs, UTC timestamps, JSONB, unique/check/foreign-key
constraints, lookup indexes, and database triggers prohibiting evidence update/delete/truncate.

Learner repositories use short SQLAlchemy transactions. Evidence, decisions, state,
context activity, and audit changes commit together. Per-learner advisory locks serialize
the same learner's writes; different learners can write concurrently. Batch locks are
ordered to avoid deadlock. Shared ontology locks let normal work coexist; trusted ontology
changes take an exclusive lock. State writes also compare the persisted version before
accepting the next version. Raw observations remain immutable, including across grading corrections.
Locked batches reuse concept, context, and state lookups inside that transaction only;
writes refresh cached values, and commit/rollback discards them.

Chat, memory and Events use a separate shared owner-row coordination boundary in
`app.db.owner_transactions`, backed by the existing `chat_sync_state` row. It
preserves their current serialization; it does not replace the learner engine's
ontology/evidence locks. Acquire owner coordination before feature row locks and
keep model calls outside transactions. Events context lookup uses the public
learner facade plus composite ownership FKs. Completion/reminders do not submit
learner evidence. See [Events contracts](events.md).

## Identity and API contracts

`learner.id` is the internal UUID. It is independent of account IDs. Every learner-owned table references it; composite ownership foreign keys prevent
cross-learner context, correction, decision, and account/session references.

| Endpoint | Request | Result |
| --- | --- | --- |
| `POST /api/v1/auth/register` | `username`, `password` | Creates account and learner; signs in |
| `POST /api/v1/auth/login` | `username`, `password` | Returns a session for the existing account |
| `GET /api/v1/auth/me` | Session cookie or `Authorization: Bearer <session>` | Authenticated internal identity |
| `POST /api/v1/auth/logout` | Session cookie or bearer header | Revokes that session and clears the browser cookie |

Standalone usernames are normalized to lowercase and are 3–64 ASCII letters/numbers/dots/
underscores/hyphens. Registration passwords are 12–256 characters, hashed with Argon2id.
Passwords are never logged or stored as plaintext.
Sessions are random 256-bit opaque tokens; only their SHA-256 digests are stored.
Logout revokes them, expiration is enforced on every authentication, and auth responses
have `Cache-Control: no-store`. Native clients receive bearer tokens by default, with
standalone sessions lasting `AUTH_SESSION_SECONDS` (default 3600).
The frontend requests cookie transport with `X-Mentra-Session: cookie`. Register/login
then return only internal identity, set a persistent HTTP-only cookie, and create a
standalone session with a 30-day default server expiry. Cookie writes require an exact trusted
browser `Origin`; authenticated unsafe cookie requests enforce the same check.
`GET /me` refreshes the cookie for the remaining server session lifetime. Browser policies or clearing
site data can still remove cookies. Migration `20261007_0002` adds persistent standalone
sessions while preserving existing timed sessions. See [frontend auth](frontend-auth.md)
for HTTPS, SameSite, origin configuration, and browser tests.
Use TLS for deployed endpoints.

HTTP adapters use `app.auth.dependencies.require_identity`. Pass its `learner_id` to
`LearnerService`, assessment adapters, RAG scope, and `create_learner_tools`. The Learner
Engine does not authenticate, verify tokens, or access accounts. Never take ownership
from an LLM argument or client-supplied learner UUID. Learner request contracts and vector
document ownership now use `learner_id`; there is no external `student_id` in learner state.
Global concept registry/curation operations remain trusted administrative operations.

The frontend provides `/login` and `/register`, restores cookie sessions, guards existing
workspace routes, and revokes sessions on sidebar sign-out. Mandatory high-level profile
onboarding is enforced separately; calibration is optional. Conversations and turns
are now persisted per account; see [persistent chat](persistent-chat.md). Events APIs, semantic chat capture, proposals, reminder delivery, Notifications and Learning Progress are implemented. See [Student Profile](student-profile.md) for required onboarding information.

## Retired platform compatibility

Platform sign-in and profile provisioning are removed. Mentra authenticates only local
accounts, including when a previously issued platform session is presented. Historical
identity mappings, session columns, and profile provenance remain in PostgreSQL so no
learner data is deleted and existing Alembic upgrade/downgrade paths stay compatible.
There is no runtime adapter, provider trust configuration, or endpoint using them.

## PostgreSQL verification

Tests require an explicit dedicated `TEST_DATABASE_URL`; they never use `DATABASE_URL`.
Each test migrates a unique temporary schema and drops that schema on completion. Use a
test database where its role can create schemas. With local Compose PostgreSQL:

```powershell
docker compose up -d postgres
docker compose exec postgres createdb -U mentra mentra_test
$env:PYTHONPATH = 'backend'
$env:TEST_DATABASE_URL = 'postgresql://mentra:mentra_local@127.0.0.1:5432/mentra_test'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
.\.venv\Scripts\python.exe backend/scripts/verify_learner.py --output docs/learner-synthetic-evaluation.json
```

The suite checks migration upgrade/downgrade/idempotency/schema drift, immutable history,
ownership constraints, transaction rollback, optimistic versions, concurrent ingestion,
authentication/session routes, concurrent registration, and retired-session rejection.
Synthetic scenarios validate learner behavior and replay; they are not real accuracy estimates.

Implementation references: [SQLAlchemy session transactions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html),
[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html),
[Argon2 password handling](https://argon2-cffi.readthedocs.io/en/stable/howto.html).
