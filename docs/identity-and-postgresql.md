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

## Deploying schema updates from GitHub

The repository uses Alembic revisions in `backend/alembic/` as its only schema-change
source. `.github/workflows/supabase-migrations.yml` applies pending revisions to Supabase
after a `main` push that changes migrations or SQLAlchemy table metadata. It serializes
deployments and checks for schema drift after applying them. It does not mirror revisions
into Supabase CLI SQL migrations, which would create a second migration history.

To enable it, add a repository Actions secret named `SUPABASE_DATABASE_URL` containing the
PostgreSQL connection URL from the Supabase Dashboard's **Connect** dialog. Use the Direct
connection when the GitHub runner can reach its IP version; otherwise use the Session
Pooler URL on port `5432`. This migration runner acquires a session advisory lock, so do
not use the Transaction Pooler URL on port `6543`. Keep the URL in GitHub Secrets and do
not commit it to `.env.example` or the repository. The workflow can also be run manually
from GitHub Actions after setting the secret.

This deploys database schema only; the GitHub workflow runs Alembic against the Supabase
PostgreSQL endpoint. It does not require Supabase-specific APIs or SDKs. The separate
Supabase Dashboard GitHub integration expects SQL files under `supabase/migrations/` and
does not apply Mentra's Python Alembic revisions. Do not enable both migration deployers
for the same database. See Supabase's [connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres)
and [GitHub deployment guidance](https://supabase.com/docs/guides/deployment/managing-environments).

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
The repository head is `20261009_0008`: baseline learner/identity tables (`0001`),
persistent standalone browser sessions (`0002`), separate profile/calibration
(`0003`), Library/ingestion (`0004`), persistent conversations (`0005`), memory
(`0006`), Events foundation (`0007`) and additive reminder-ledger retention (`0008`).
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

`learner.id` is the internal UUID. It is independent of account IDs and external student
IDs. Every learner-owned table references it; composite ownership foreign keys prevent
cross-learner context, correction, decision, and account/session references.

| Endpoint | Request | Result |
| --- | --- | --- |
| `POST /api/v1/auth/register` | `username`, `password` | Creates account and learner; signs in |
| `POST /api/v1/auth/login` | `username`, `password` | Returns a session for the existing account |
| `POST /api/v1/auth/external` | `provider`, `token` | Verifies signed assertion, provisions/resolves identity, returns session |
| `GET /api/v1/auth/me` | Session cookie or `Authorization: Bearer <session>` | Authenticated internal identity |
| `POST /api/v1/auth/logout` | Session cookie or bearer header | Revokes that session and clears the browser cookie |

Standalone usernames are normalized to lowercase and are 3–64 ASCII letters/numbers/dots/
underscores/hyphens. Registration passwords are 12–256 characters, hashed with Argon2id.
Passwords are never logged or stored as plaintext. External login accepts no password.
Sessions are random 256-bit opaque tokens; only their SHA-256 digests are stored.
Logout revokes them, expiration is enforced on every authentication, and auth responses
have `Cache-Control: no-store`. Native clients receive bearer tokens by default, with
standalone sessions lasting `AUTH_SESSION_SECONDS` (default 3600).
The frontend requests cookie transport with `X-Mentra-Session: cookie`. Register/login
then return only internal identity, set a persistent HTTP-only cookie, and create a
standalone session without a server expiry. Cookie writes require an exact trusted
browser `Origin`; authenticated unsafe cookie requests enforce the same check.
`GET /me` renews the cookie's 400-day browser lifetime. Browser policies or clearing
site data can still remove cookies. Migration `20261007_0002` adds persistent standalone
sessions while preserving existing timed sessions. See [frontend auth](frontend-auth.md)
for HTTPS, SameSite, origin configuration, and browser tests.
External sessions expire no later than their signed assertion, so the hosting platform
must issue a new assertion when access expires. Use TLS for deployed endpoints.

HTTP adapters use `app.auth.dependencies.require_identity`. Pass its `learner_id` to
`LearnerService`, assessment adapters, RAG scope, and `create_learner_tools`. The Learner
Engine does not authenticate, verify tokens, or access accounts. Never take ownership
from an LLM argument or client-supplied learner UUID. Learner request contracts and vector
document ownership now use `learner_id`; there is no external `student_id` in learner state.
Global concept registry/curation operations remain trusted administrative operations.

The frontend provides `/login` and `/register`, restores cookie sessions, guards existing
workspace routes, and revokes sessions on sidebar sign-out. Mandatory high-level profile
onboarding is enforced separately; calibration is optional. Conversations and turns
are now persisted per account; see [persistent chat](persistent-chat.md). Manual
Events APIs are implemented while the Progress UI remains a placeholder;
granular learner API wiring and EduVerse's embedding/login UI are separate work. See
[Student Profile](student-profile.md) for signed EduVerse provisioning with an initial
profile, which can satisfy the required information step directly.

## Trusted external platforms

Configure `AUTH_EXTERNAL_PROVIDERS` as a JSON map. No external provider is trusted by
default. Example structure (replace the placeholder with a real PEM **public** key):

```json
{
  "eduverse": {
    "issuer": "https://your-eduverse-issuer.example",
    "audience": "mentra",
    "algorithm": "RS256",
    "public_keys": {"key-2026": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"},
    "subject_claim": "sub",
    "max_token_lifetime_seconds": 300,
    "clock_skew_seconds": 10
  }
}
```

In `.env`, put the compact JSON on one line inside single quotes. `RS256` requires an
RSA public key of at least 2048 bits; `ES256` requires a P-256 public key. Multiple keys
support rotation via `kid`; missing `kid` is accepted only when one key is configured.
The configured algorithm is authoritative. Embedded keys, key URLs, HMAC/shared secrets,
and unsigned tokens cannot establish trust. Mentra does not fetch token-specified URLs.

The platform signs a short-lived JWT using its own private key. Required claims are
`iss`, `aud`, `iat`, `exp`, and the configured subject claim. Set `sub` to the existing
student ID as a string, or configure `subject_claim: "student_id"` for an existing claim
(integer IDs are normalized to decimal strings). Issuer/audience/signature, time bounds,
maximum lifetime, and subject type are verified **before** any database provisioning.

First valid login atomically creates `learner` and
`external_identity(provider, external_subject_id, learner_id)`. Repeated and concurrent
logins use the same mapping. The unique provider/subject pair separates tenants from
different platforms; identical subject strings from different providers remain distinct.
Standalone accounts and external identities are not silently linked by username/email.
EduVerse students need no Mentra credentials, Mentra never receives their EduVerse
passwords, and no EduVerse student schema changes are required. This defines a generic
integration contract; EduVerse's token issuance and embedding UI are future work.

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
authentication/session routes, simultaneous provisioning, and invalid external assertions.
Synthetic scenarios validate learner behavior and replay; they are not real accuracy estimates.

Implementation references: [SQLAlchemy session transactions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html),
[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html),
[PyJWT verification](https://pyjwt.readthedocs.io/en/stable/api.html),
[Argon2 password handling](https://argon2-cffi.readthedocs.io/en/stable/howto.html),
and [JWT best practices, RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html).
