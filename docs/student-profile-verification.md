# Mentra full-stack verification — 2026-10-07

This report covers the current worktree: PostgreSQL persistence and migrations,
identity/authentication, the separate Student Profile/calibration system, EduVerse
profile provisioning, the granular Learner Engine, frontend flows, and Docker builds.
It records execution checks, not a claim of measured learner-estimation accuracy.

## Automated checks

| Check | Observed result |
| --- | --- |
| Full backend suite on PostgreSQL 17 | 145 tests passed |
| Full Chromium browser suite | 18 tests passed |
| Frontend TypeScript and Vite production build | Passed |
| Light/Dark/System theme checks | Passed |
| Independent granular learner simulation | 1,200 observations; restart/replay equality passed |
| Alembic schema drift | Checked by the PostgreSQL tests; current head `20261007_0003` |
| Docker images | `mentra-backend:latest` and `mentra-frontend:latest` rebuilt successfully |
| Running Compose stack | PostgreSQL, backend, and frontend all healthy |
| Live container schema/dependencies | Revision `20261007_0003`; no schema drift or broken Python dependencies |
| Live local API/UI probe | Liveness `ok`; auth, profile, EduVerse routes present; frontend returned HTTP 200 |
| Fresh Compose database | Zero learners, profiles, or profile-evidence rows |

Built image IDs at verification: backend `sha256:421f2b7fb8e5825b7ff674962face489520ebed2ca7fba0111251013a2ad447c`;
frontend `sha256:7f574c457f6a2fa842613fc17d8ff26932656ae6093264170bfbf1be002539ce`.
The Compose startup created a new local PostgreSQL volume and initialized the empty
database through the current migration head. It found no existing local learner/profile
data to migrate.

The backend suite includes upgrade/downgrade/idempotency, constraints and immutable
history, learner ownership, transaction rollback, optimistic versions, concurrent
writes, and external identity provisioning. Student Profile checks include all seven
education banks and controlled field variants, item-level scoring, strict AI output
validation, unsupported evidence rejection, failure/retry, context changes during AI
evaluation, duplicate/expired claims, conservative updates, and user-field ownership.
Profile calibration leaves granular concept/evidence tables untouched.

EduVerse checks use real signed RSA assertions, PostgreSQL repositories, and production
routes. They verify issuer/audience/subject validation before provisioning, complete
profile validation, rejection of passwords/client-selected learner UUIDs, numeric IDs,
simultaneous first logins, stable mappings, cookie handoff, expiry, and preservation of
manual profile edits on repeated platform calls.

Browser checks exercise real authentication/profile endpoints and PostgreSQL. They
cover mandatory information, optional calibration, saved progress across refresh/login,
profile edits, lost autosave responses, conflicting draft answers, provider outages and
retry, protected routes, logout/revocation, tab synchronization, network errors, and
320/768/1440px Light/Dark layouts with reduced motion. Only the external AI evaluator
uses a test double in browser tests. A separate backend test uses the real model factory,
ChatOpenAI tool schema, HTTP serialization, and structured parser with controlled HTTP
transport.

The final application transaction also has a failure-injection check: failing after
saving estimates but before saving the applied evidence rolls both changes back.
Expired-claim recovery applies the original eight results once, preserving completed
answers without double counting.

## Live AI provider

A fresh synthetic eight-question calibration was sent through the configured production
model factory and evaluator. The provider returned **HTTP 402 (Insufficient Balance)**.
Observed recovery: onboarding completed, eight answers remained saved, evaluation was
marked failed, and all five estimated dimensions remained unknown. No deterministic
test output is substituted for AI output in production.

Successful live AI estimates remain unverified until provider balance is available.
Retry evaluation from Settings after restoring provider access; the saved assessment
does not need to be taken again. Eight selected-response questions support provisional
screening estimates only. The question banks and profile confidence are not yet
psychometrically validated against real students.

## Reproduce checks

Create a dedicated PostgreSQL test database with permission to create temporary schemas.
Tests never fall back to the application's `DATABASE_URL`.

```powershell
$env:PYTHONPATH = 'backend'
$env:TEST_DATABASE_URL = 'postgresql://mentra:mentra_local@127.0.0.1:5432/mentra_test'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
.\.venv\Scripts\python.exe backend/scripts/verify_learner.py --output docs/learner-synthetic-evaluation.json
Set-Location frontend
npm ci
npx playwright install chromium --only-shell
npm run build
npm run check:theme
npm run test:e2e
```

See [Student Profile contracts](student-profile.md), [identity/PostgreSQL setup](identity-and-postgresql.md),
[frontend authentication](frontend-auth.md), and [Docker setup/update commands](SETUP.md).

## Scope boundaries

Student Profile is separate from concept mastery. Its compact context packet and
trusted evidence service are ready for future prompt/interaction adapters; automatic
chat evidence extraction and profile prompt injection are not implemented. Chat is
still held in memory. Library, granular Progress, curriculum Assessments, and backup
remain frontend placeholders. EduVerse token issuance and its student interface are
external integration work; Mentra's signed identity/profile API is implemented.
