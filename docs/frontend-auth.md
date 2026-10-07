# Frontend authentication

`/login` and `/register` accept only username and password. Registration creates the
account and learner and signs in immediately. All existing workspace routes require a
session. A protected deep link is restored after login or registration. The sidebar's
Sign out action revokes the current server session and clears its browser cookie.

Registration now proceeds through mandatory Student Profile information and optional
calibration before entering the protected workspace. The profile gate is separate from
authentication. See [Student Profile](student-profile.md) for onboarding, editing, and
the signed EduVerse provisioning endpoint that can supply an initial profile.

The pages reuse Mentra's shared fields, button, card, spinner, logo, semantic theme
tokens, and typography. They support field validation, backend errors, loading states,
password visibility, keyboard access, mobile layouts, and reduced motion.

## Session transport and boundaries

`services/auth.ts` calls the real `/api/v1/auth` routes with credentials and
`X-Mentra-Session: cookie`. Login/register return identity only. The backend stores the
opaque session token in the `mentra_session` HTTP-only cookie at `/api/v1`; only its hash
is persisted in PostgreSQL. JavaScript does not read or persist tokens.

`AuthProvider` restores identity with `/auth/me` on initial load, focus, and tab return.
Standalone identity responses include the account username for the sidebar account
drawer; external identities use their configured provider label.
Tab messages trigger a fresh server check. Network failures offer retry or preserve an
already verified identity; a 401 redirects to login. Logout waits for server revocation,
and a failed request keeps the workspace available for retry. Changing learner identity
remounts the workspace to discard the previous learner's in-memory client state.

Standalone browser sessions have no server timeout and remain valid until revoked.
The cookie lasts 400 days and `/me` renews that lifetime on visits. Browsers impose their
own storage limits; removing cookies or site data requires signing in again. Native
bearer sessions keep their configured timeout, and external sessions remain bounded by
the trusted platform's signed assertion. The Learner Engine and repository boundaries
are unchanged.

Apply migrations through the current head, `20261007_0003`, before running the backend.
Revision `0002` supplies persistent standalone sessions; `0003` supplies profiles and
calibration. Compose upgrades to head automatically; native setup uses
`python -m app.db.migrate` with `PYTHONPATH=backend`.

## Local and deployed configuration

- Use the same hostname locally for frontend and API: both `localhost`, or both
  `127.0.0.1`. Ports may differ. Set `VITE_API_URL` to the API's browser-reachable URL.
- List the exact frontend origin in `FRONTEND_ORIGIN` / `CORS_ORIGINS`. Unsafe cookie
  requests require a trusted `Origin`, independently of CORS.
- Default `AUTH_COOKIE_SAME_SITE=lax` works for same-site frontend/API deployments.
  Production must use HTTPS; `APP_ENV=production` automatically enables secure cookies.
  Set `AUTH_COOKIE_SECURE=true` explicitly when testing with HTTPS.
- A deployment that requires cross-site cookies can set `AUTH_COOKIE_SAME_SITE=none`
  with HTTPS and secure cookies. Browser third-party-cookie policies still apply;
  serving the frontend and API under the same site is preferable.

There is no email, verification, recovery, or OAuth UI. Generic external identity and
public-key verification remain available to future platform integrations.

## Verification

Install backend requirements in the repository `.venv`, then install frontend packages
and Chromium. `PYTHON_EXE` can select a different Python environment. Tests require an
explicit dedicated PostgreSQL test database whose role can create schemas; they never
use the application `DATABASE_URL`.

From the repository root in PowerShell, after creating that database:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://mentra:mentra_local@127.0.0.1:5432/mentra_test'
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
Set-Location frontend
npm ci
npx playwright install chromium --only-shell
npm run build
npm run check:theme
npm run test:e2e
```

`test:auth` and `test:profile` select individual suites. Playwright starts a temporary
frontend on port 15173 and an auth/profile backend on 18003.
That backend uses the production auth/profile routes, services, password hashing,
repositories, question banks, scoring, and Alembic migrations in a unique PostgreSQL
schema. It excludes AI/embedding/Qdrant startup; profile AI evaluation uses a predictable
test double. Auth responses are not mocked. The schema
is dropped explicitly by suite teardown (and on graceful server shutdown), and browser traces/screenshots are written to ignored
`frontend/test-results/`. Network failures are deliberately injected only in error-path
tests.

Backend tests cover cookie flags, origin checks, persistent sessions, expiry for bearer
and external sessions, revocation, and migration preservation. Browser tests cover
registration, login, session restoration across refresh and return visits, protected
routes, tab synchronization, validation/errors, logout/retry, mobile navigation, both
themes, and reduced motion. Profile checks also cover mandatory information, resumed
drafts, provider outages/retry, lost autosave responses, and conflicting edits.

See the [current verification report](student-profile-verification.md) for the full
suite results, Docker verification, and the live-provider limitation.

Cookie implementation references: [FastAPI response cookies](https://fastapi.tiangolo.com/advanced/response-cookies/)
and [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
