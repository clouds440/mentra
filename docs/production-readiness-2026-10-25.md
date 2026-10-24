# Production-readiness engineering record — 2026-10-25

**Assessment: ready with conditions.** Local builds, isolated persistence,
browser journeys, runtime startup and configured provider checks support this
assessment. Public production networking, capacity and disaster recovery still
need deployment-specific acceptance. Follow the [deployment runbook](production-readiness.md).
The launch-gate continuation below records additional recovery/load closure and
the precise external requirements. The user confirmed domains/hosting are not
configured yet; no public deployment is authorized or claimed.
No unit tests were run or added. No application database was migrated or reset.

## Scope and findings

| Area inspected | Result and changes |
| --- | --- |
| Architecture and Git | Started from clean `8fbf7a0`; retained domain facades, PostgreSQL authority, vector derivation, provenance and current standalone identity. Reviewed API registration, startup/shutdown, deployment, manifests, workers and important feature paths |
| Request abuse | Confirmed size checks were conditional on declared JSON even though FastAPI reads other body types. All non-upload bodies now receive the existing route budget; multipart originals keep their dedicated larger budget, including chunked transfer |
| Private delivery | Oversized numeric Range headers now return 416. Provider-acquisition failure/cancellation cleanup is shielded and nested so a failed provider close cannot leak the registry lease or transfer slot |
| Browser resilience | Optional tab messaging now tolerates a missing API or a constructor throwing SecurityError across auth, profile, chat, pages and memories |
| Upload correctness | Completed receipts and operation keys reset on owner changes, fence late responses, distinguish filenames and honor an already-aborted signal before returning cached success. Monotonic retry deadlines stay below server staging lifetimes; expired server receipts return 404 rather than falsely recovering success |
| Configuration and secrets | Production browser origins must be explicit HTTPS origins; malformed ports/paths, credentials and wildcard production origins fail startup. Valid trailing slashes normalize. Settings representations and validation strings omit secret inputs |
| Dependencies | Updated FastAPI/Starlette, multipart, PDF, dotenv, checkpoint adapter/core, model libraries, filelock, setuptools and pip to resolve scanner findings. Updated CPU Torch after separately checking its upstream advisories; kept the same E5 model/revision/dimensions |
| Reproducibility and builds | Added 129-package Linux Python 3.12 runtime constraints, used by Docker/CI. Added build-time `pip check`; kept the CPU wheel installation before dependency-file copies so manifest changes preserve its cached layer |
| Workers/resources | RAG/assessment workers validate and close private-storage clients; assessment shares one Files service with RAG. File cleanup retries emit sanitized diagnostics and files-worker logs persist with other services |
| Deployment | API/workers drop capabilities and prohibit privilege escalation. Added explicit host bind/proxy-trust settings and shared production origin settings. Added non-destructive `rag_admin initialize` for a new deployment's missing Qdrant collection |
| Auth and isolation | Reviewed session digests/expiry/revocation, current-password change fencing, cookie-origin checks, owner-bound routes, composite storage bindings and RAG candidate hydration/final authorization. Retired external identity exchange stays unavailable |
| AI/RAG and documents | Reviewed workflow deadlines, bounded admission/retries, durable publication/Stop, prompt/source trust boundaries, extraction subprocess/resource limits, authenticated originals, index identity and deletion/reconciliation. Preserved model choices and retrieval semantics |
| Data and operations | Rehearsed current migrations and metadata on disposable PostgreSQL. Updated stale setup/head/port/worker/session/sync documentation and supplied backup, migration, index provisioning and rollback procedures |

No schema revision was added. Existing storage migration `20261020_0028` still
refuses legacy originals rather than discarding them. Existing READY material
remains searchable; drain old ingestion jobs or explicitly reindex their material
because the parser dependency revision changes. Production origin validation is
an intentional new startup requirement for API and workers.

## Verification evidence

Commands below ran from the repository root unless noted. Docker checks used
isolated containers, a new local PostgreSQL database on port 15439 and Qdrant on
16335. Application `.env` was used only for real provider credentials/configuration;
database and vector endpoints were overridden to disposable services.

| Command/check | Observed outcome |
| --- | --- |
| `npm run build` in `frontend` | TypeScript application/tool checks and production Vite build passed; final frontend Docker build also passed |
| `npm run check:theme`, `npm run check:ui` | Passed theme/bootstrap/storage/reduced-motion and shared-UI checks |
| `npm audit --omit=dev --audit-level=moderate`, then `npm audit --audit-level=moderate` | Zero reported production or build-time npm advisories. Initial sandbox DNS failure was rerun with network access |
| `python -m ruff check backend/app backend/scripts/verify_http_readiness.py backend/scripts/rag_admin.py --select E9,F63,F7,F82` | Passed targeted fatal syntax/name checks; all 394 application/script/migration Python files also parsed successfully with `ast.parse` |
| `git diff --check` and tracked working-tree credential-pattern scan | Passed whitespace check; no matches for the scanned private-key/AWS/OpenAI-token patterns. This was not an exhaustive secret-history audit |
| `docker compose config --quiet` | Passed. Additional production-mode parsed configuration checks confirmed HTTPS origins and capability restrictions reach all six backend services |
| `docker build -t mentra-readiness-backend:20261025 backend` | Final Python 3.12 production build passed with locked dependencies, CPU models/tokenizer baked offline and build-time `pip check` |
| `docker build -t mentra-readiness-frontend:20261025 frontend` | Production multi-stage build passed; Nginx unprivileged runtime served SPA deep links with no-cache HTML and security headers under read-only/capability restrictions |
| `python -m pip check` inside runtime | No broken requirements. The host Python 3.14 virtual environment initially reported an MCP/Starlette mismatch; it was not used to establish production compatibility |
| `python -m pip_audit --path /usr/local/lib/python3.12/site-packages --progress-spinner off` in disposable scanner containers | Initial image: 103 advisory records in ten packages, including duplicate feed records. Updated runtime: no known vulnerabilities among audited packages. CPU-tagged Torch is skipped by pip-audit; exact upstream Torch 2.14.1 PyPI metadata was checked separately and reported no advisory records |
| `python -m app.db.migrate`, `python -m alembic check` against disposable PostgreSQL | Upgrade to `20261021_0030` and metadata comparison passed. Also downgraded to `20261017_0027`, re-upgraded, repeated upgrade, preserved an unrelated synthetic learner and rechecked drift |
| Real PostgreSQL LangGraph checkpoint exercise | Saved a synthetic graph, reconstructed it through a new saver, read its state and deleted only that synthetic thread; passed with patched adapter/core |
| Disposable PostgreSQL `pg_dump -Fc`, `createdb`, `pg_restore --exit-on-error --no-owner` | Restored into a separate new database; migration head and synthetic learner survived. This does not establish production backup retention or coordinated external-original recovery |
| Expired-file persistence exercise and six affected browser reruns | Real disposable PostgreSQL rejected an expired upload receipt and cleaned its synthetic asset. Browser account/filename/expiry/abort handling and existing staged/failed-upload recovery passed (six scenarios, overlapping the 67 above) |
| `python -m scripts.verify_http_readiness` inside runtime | Real production ASGI stack passed declared/chunked oversized requests across five media types, small missing-content-type JSON validation, upload budget and huge Range rejection. Explicit provider/registry stand-ins exercised provider-close failure and cancellation cleanup; no external storage was represented as real by this check |
| `npx playwright test --config playwright.mock.config.ts --output .cache/readiness-mock-final-results` in `frontend` | 66 passed in the main final run; one outdated workspace-page fixture was corrected and its targeted rerun passed. Together all 67 distinct scenarios passed, including new missing/blocked messaging and receipt isolation checks |
| `npx playwright test --config playwright.mock.config.ts workspace-polish.spec.ts --grep 'workspace pages share responsive surfaces' --output .cache/readiness-workspace-results` | Passed with current page-response contracts. Earlier stale expectations were updated for the established 60rem chat/52rem composer, explicit chat-change sync and Review-result dialog, preserving their functional assertions |
| Browser integration config selecting `auth.spec.ts`, `files.spec.ts`, `events-notifications.spec.ts`, `student-profile.spec.ts` | 21 passed; one trace-artifact collision occurred because two runs shared output. The affected password-change journey passed separately with isolated output. All 22 distinct journeys passed against real disposable PostgreSQL with explicitly deterministic AI/storage/vector fixtures |
| Real API startup and HTTP smoke | Production-mode API ran as UID 10001 with capabilities dropped and no-new-privileges; liveness/readiness/OpenAPI returned 200, with 97 OpenAPI paths and database/AI/embedding/Qdrant checks ready |
| Configured AI provider | One small synthetic direct model request succeeded. This is connectivity evidence, not an exhaustive model-quality or outage simulation |
| `PYTHONPATH=/app python scripts/verify_files_cloudinary.py` with explicit disposable `TEST_DATABASE_URL` | 18 synthetic code/text/raster originals round-tripped byte-for-byte through real authenticated Cloudinary delivery. Only run-created verification assets were removed; its temporary schema was cleaned |
| Updated embedding/document runtime | Compared English, Urdu and Chinese query/passage vectors with the original image. Same model SHA, 384 dimensions and token counts; maximum coordinate difference with patched Torch was `5.960464477539063e-08`. Real isolated TXT/DOCX/PPTX reading, blank-PDF handling and image OCR passed |
| Offline speech runtime | Real baked CPU speech model warmed and its child process closed successfully |
| Operator initialization and workers | Non-destructive index provisioning and five worker entry points exercised against isolated services; see final runtime verification below |

Browser checks used current source and actual browser execution. Deterministic
external fixtures in browser integration are not claimed as real AI/Cloudinary
checks; the separate real provider checks above supply limited live evidence.
No `unittest`, `pytest`, or backend unit-suite command was executed.

## Optimizations and compatibility

| Change | Evidence/limit |
| --- | --- |
| Assessment worker private-storage sharing | Two separately constructed Files/provider clients become one shared client/pool; both workers close their owned clients on shutdown |
| Docker dependency layers | CPU runtime installation precedes manifest/lock copies; subsequent source-only rebuild reused model/dependency layers. No runtime latency gain is claimed |
| Embedding compatibility | Numerically checked rather than assuming a major library update is harmless; no model, dimension, collection identity or schema reset |
| Frontend size | Main JavaScript changed approximately 316.01 → 316.34 kB (100.83 → 100.98 kB gzip) with resilience fixes. No bundle or rendering performance improvement is claimed |

## Conditions before a real launch

This table records the initial hardening handoff. See the continuation below for
conditions subsequently closed through local launch-gate verification.

| Remaining condition | Required action |
| --- | --- |
| Actual public deployment | Configure HTTPS origins/API URL, TLS termination, trusted proxy addresses, firewall/listener exposure and certificate renewal; exercise them through the public browser origin |
| Existing data | Verify actual database head, take coordinated PostgreSQL/original-byte backups and rehearse restore. Preserve/backfill populated legacy originals before storage migration; drain/reindex old ingestion work as documented |
| Capacity and reliability | Run representative concurrent load on the real database/provider/network, review ten-connection default plus rollout overlap, CPU/memory and quotas; inspect durable job outcomes/failed queues |
| Disaster recovery | Verify actual provider backup retention and restoration. This run did not rehearse recovery of a production database plus Cloudinary originals |
| External coverage | No production Qdrant traffic, public proxy/TLS deployment, exhaustive AI quality/failure corpus, remote CI execution, operating-system vulnerability scan, or production load benchmark was performed |
| Dependency guarantees | Advisory databases are time-bounded and CPU Torch required a separate upstream lookup. The snapshot does not prove absence of unknown vulnerabilities; repeat scans at release |

Verified images were temporary local artifacts and were removed at the user's
request after verification. Rebuild with the actual public `VITE_API_URL` for
launch. Existing application containers, latest images, data and Git history
were preserved. Changes were uncommitted at that initial handoff; final commit
verification is recorded at the end of this document.

### Final runtime verification

The final production-mode API returned HTTP 200 from `/api/v1/health/ready`,
with database, AI, embedding and isolated Qdrant checks ready. All five worker
entry points ran for approximately seven minutes without failure logs and
exited with code 0 after SIGTERM. The final API also exited with code 0.
Non-destructive index initialization succeeded against the existing disposable
collection.

Verified final image identities (removed after checks):

- Backend: `sha256:00d12200aed814d5e54f2ec1c853256d0c9d7ba035f4fe5908f2448eb9b39ce4`.
- Frontend: `sha256:fdc79185ab57410f66de525bfce3ddf04b1b331e501111ca66e6a2e620af8116`.

Cleanup removed all 15 mission-created containers, seven verification/pulled
images, the disposable PostgreSQL volume/databases, local screenshots, traces,
browser reports, build output, audit logs and scratch scripts. The real provider
check deleted its 18 synthetic originals; its empty verification folder was also
deleted. Existing application containers/images/volumes, original-byte backups,
model caches and intentional regression-check source files were preserved.
Docker's shared build cache was not globally pruned.

## Final launch-gate continuation — 2026-10-25

**Final assessment: ready with conditions.** Repository preparation and the
bounded local acceptance drills passed. Public deployment cannot be accepted
until the actual host/domains, TLS/network policy, production data recovery point,
provider limits and initial traffic envelope are supplied and checked. Nothing
was published, no DNS/live infrastructure changed, no credentials rotated, and
no existing application container or volume was modified.

### Conditions resolved locally

| Prior condition | Closure/evidence |
| --- | --- |
| Production configuration preparation | Added private-value template, offline preflight, production Compose override and optional host Nginx TLS template. Merged configuration preserved all seven application services, six production-mode backend processes, common storage settings and default ten-connection budget. Each HTTP service had exactly one loopback publication; no accidental retained wildcard listener |
| Release/rollback image selection | Added configurable `BACKEND_IMAGE` for API/five workers and explicit `FRONTEND_IMAGE`, with version/digest preflight. Production frontend builds reject localhost/non-HTTPS API origins; a synthetically configured HTTPS release build passed |
| Browser/proxy transport | Actual Chromium against production-mode API and built static frontend through Nginx TLS: registration/onboarding, Secure/HTTP-only/Lax cookie, refresh, credentialed cross-origin fetch, no-store identity response, SSE terminal success and SPA deep link passed. One-day self-signed certificate and local hostname resolution only; public certificate chain/renewal remain unverified |
| Database recovery | Custom-format dump restored into a separate new PostgreSQL database. All 85 table row counts matched, 24 tables were nonempty, head `20261021_0030` and all constraints validated. Four preserved sessions authenticated; nonempty owned conversation/message reads and two preserved original checksums passed. This covers synthetic account/session/profile/context/chat/job/file/binding/source relationships, not production retention |
| Original-byte recovery | Exported both synthetic private originals with SHA-256, deliberately deleted one, uploaded its saved bytes at the same authenticated provider ID, updated its registry provider receipt and verified the checksum. This used a manual synthetic export/restore, not Cloudinary's managed backup product |
| Vector recovery | Deleted only the disposable collection, initialized matching identity, queued explicit owned rebuilds from restored PostgreSQL/originals, and recovered both documents' retrieval. Two active generations/four chunks each; four successful jobs immediately after the rebuild |
| Migration prerequisites/rollback | Separate disposable schemas confirmed populated legacy source records block `20261020_0028` upgrade with provenance intact; populated registry blocks downgrade with its file record intact. Restored database also passed `alembic check`; no schema revision added |
| Image rollback compatibility | Prior existing backend image `946fef81485a` started against the restored current schema and passed readiness, saved-session authentication, document reads and real retrieval. This is backend compatibility evidence; a future public rollback must retain a paired frontend built for its actual API origin and matching prior configuration |
| Bounded capacity | Two 24-second read-load runs, concurrency 1/2/4/8, zero errors; detailed measurements below. Owner identity/context checks ran on every applicable response. Real PostgreSQL pool sampling stayed at five API connections with zero overflow |
| Dependency/fault recovery | Private HTTP AI fixture exercised quota failure, a two-second timeout, successful recovery and durable failed chat status. Real admission allowed two held workloads and rejected six with 429. Chat Stop preserved its stopped terminal state. Real Qdrant outage changed readiness to 503; recovery restored 200. Database outage changed readiness/authenticated API to 503 after the fix below; both returned 200 after restart |
| Durable worker recovery | Two newly queued rebuilds entered RETRY_WAIT while Qdrant was stopped, then succeeded after restart (six successful jobs total, maximum two attempts). A later PostgreSQL outage triggered three restarts under the configured restart policy; worker returned to running after recovery. No active admission leases remained |

### Additional defects fixed

| Change | Why/compatibility |
| --- | --- |
| `backend/app/db/errors.py` | Real connection refusal previously produced generic HTTP 500. Psycopg client-side OperationalError without SQLSTATE and explicit server shutdown/connectivity states now map to the existing 503 DATABASE_BUSY response. Write-outcome recovery instructions remain intact; server-reported authentication/SQL errors are not broadly reclassified |
| `FILES_ENVIRONMENT` in settings/provider/Compose | Original paths previously followed APP_ENV directly, so enabling production mode could make retained development originals inaccessible. An explicit stable storage suffix now preserves paths independently of security policy. Empty retains historical behavior. A production-mode real-provider read with the preserved suffix passed; an unconfigured mismatched namespace still failed closed. No cross-environment fallback or data migration was introduced |

No runtime throughput optimization is claimed in this continuation. Image
selection, configuration checks, namespace preservation and repeatable acceptance
drivers are operational improvements rather than new learner-facing features.

### Measured local load and limits

Environment: Docker Desktop Linux, 12 CPUs, 15.58 GiB available memory;
Python 3.12 production image, local PostgreSQL 17/Qdrant 1.15.5 on a private
Docker network, four synthetic authenticated learners. API pool five/overflow
zero; RAG worker pool one. Each row is a six-second closed-loop stage. The mixed
read paths were identity, recent conversations, paginated learning contexts and
the documents page. This is a small, warm local data set without hosted-database
network latency, a long soak, or production-scale users.

| Concurrency | Requests / RPS, first run | p50 / p95 / p99 ms, first run | Requests / RPS, monitored rerun | p50 / p95 / p99 ms, rerun | Errors |
| --- | --- | --- | --- | --- | --- |
| 1 | 912 / 151.91 | 6.57 / 9.29 / 10.48 | 880 / 146.55 | 6.70 / 9.79 / 12.40 | 0 |
| 2 | 894 / 148.85 | 12.88 / 19.39 / 23.23 | 819 / 136.29 | 13.18 / 24.87 / 27.38 | 0 |
| 4 | 776 / 129.12 | 29.38 / 46.16 / 49.18 | 677 / 112.51 | 31.75 / 61.91 / 74.10 | 0 |
| 8 | 756 / 125.47 | 61.19 / 95.82 / 104.84 | 699 / 115.93 | 61.52 / 113.66 / 125.09 | 0 |

First run: 3,338 reads in ~24 seconds. Monitored rerun: 3,075 reads in ~24
seconds; 238 database samples at 100 ms intervals, maximum five application
connections and one sampled active query (monitor excluded). Samples can miss
short activity spikes; configured pool capacity is not a measured active-query
peak. Throughput declined as concurrency rose, so these measurements support
a conservative controlled rollout, not an assumption of linear scaling.

Twelve Docker resource snapshots during the first read/ingestion drill observed
API peak 127.72% CPU / 965.7 MiB; RAG worker 228.40% / 854.8 MiB;
PostgreSQL 9.45% / 60.91 MiB; Qdrant 2.53% / 79.77 MiB. Docker CPU percentages
can exceed 100% across cores. These are sampled container peaks, not host-wide
or instantaneous worst-case bounds, and do not represent all five workers under
simultaneous heavy load.

Four concurrent actual chat API operations completed in 1.25 seconds through the
deterministic private OpenAI HTTP fixture (100 ms normal delay, zero external AI
calls); one used the permitted 4,000-character content limit. An oversized
2 MiB + 1 byte ordinary request returned 413. Two small real Cloudinary originals
ingested with real E5/Qdrant in 2.782/3.021 seconds from job creation to completion;
ownership denial returned 404. Large 25 MiB provider transfers and concurrent
heavy OCR/assessment workloads were not benchmarked. No external provider was
stress-tested, and these values do not establish real AI throughput or cost.

The private provider adapter observed quota failure in 0.008 seconds, timeout in
2.004 seconds, then success in 0.108 seconds. Durable chat failures were recorded
without exposing fixture/provider diagnostics. Admission peak was two, with six
of eight held workloads receiving bounded 429 responses. Safety limits were
concurrency ≤16, stage duration ≤30 seconds, ≤2,000 requests/stage (at most
in-flight overshoot), and abort on >5% errors or p95 >5 seconds. Executed load
stopped at concurrency eight; no production capacity target has been chosen.

### Exact verification entry points

All Docker resources used the `mentra-launchgate-*` names/private network; all
published drill access bound only to `127.0.0.1:19443`. Backend testing sources
were mounted read-only at `/app/testing`; they are not shipped in the runtime
image. `TEST_DATABASE_URL` explicitly named `mentra_launchgate`, never the
application's configured database. The recovery drivers fence the database,
vector collection and storage suffix before any mutation.

| Command/check | Outcome |
| --- | --- |
| `python backend/scripts/validate_production.py --env-file .cache/launchgate/synthetic-production.env` | Passed with synthetic values; an empty production template failed with configuration names only. This did not connect to those synthetic domains |
| `docker compose --env-file .cache/launchgate/synthetic-production.env -f docker-compose.yml -f docker-compose.production.yml config --quiet` and parsed `config --format json` | Passed with Compose 5.6.0; checked one loopback mapping per HTTP service, production mode and correct image/pool inheritance |
| `MENTRA_RELEASE=true VITE_API_URL=http://localhost:8000 node frontend/scripts/validate-release.mjs` | Rejected with exit 1; explicit synthetic HTTPS origin accepted offline |
| `docker build -t mentra-launch-backend:20261025 backend` | Final production build and `pip check` passed |
| `docker build --build-arg MENTRA_RELEASE=true --build-arg VITE_API_URL=https://api.launchgate.example.org:19443 -t mentra-launch-frontend:20261025 frontend` | Final release-mode TypeScript/Vite/container build passed with an explicitly synthetic browser-drill API URL; rebuild for real launch |
| `docker exec mentra-launchgate-proxy nginx -t` | Rendered template syntax passed; local TLS/browser path verified separately |
| `MENTRA_LAUNCH_HTTPS=true npx playwright test --config playwright.launch.config.ts --output .cache/launchgate-browser-final-results` from frontend | Passed against final built frontend and production-mode API, preserved storage suffix, restored database and actual local TLS proxy |
| `docker exec mentra-launchgate-api python -m testing.launch_load --seconds 6 --concurrency 1 2 4 8` | Bounded read/upload/ingestion/chat/Stop integration passed |
| `docker exec mentra-launchgate-api python -m testing.launch_load --reuse --seconds 6 --concurrency 1 2 4 8` | Read-only monitored capacity rerun passed; no extra cloud uploads/model requests |
| `docker exec mentra-launchgate-api python -m testing.launch_faults` | Real HTTP provider adapter rate/timeout/recovery plus PostgreSQL admission and durable API failures passed |
| `python -m testing.launch_recovery archive`, `validate`, `restore-original`, `rebuild`, `application`, `namespace-promotion` inside the fenced drill runtime | Two originals archived; new database counts/constraints/domain reads verified; one original restored; isolated vectors rebuilt; production storage promotion passed |
| `docker exec mentra-launchgate-postgres pg_dump -U postgres -d mentra_launchgate -Fc -f /tmp/launchgate.dump`, then `createdb -U postgres mentra_launchgate_restore`, then `pg_restore -U postgres --exit-on-error --no-owner -d mentra_launchgate_restore /tmp/launchgate.dump` | Passed; source database remained intact |
| `docker exec mentra-launchgate-api python -m testing.launch_migrations` | Both populated migration refusal checks passed; unique schemas removed. Initial assertion compared UUID object to text; corrected the fixture comparison and reran successfully |
| `python -m alembic check` with DATABASE_URL explicitly overridden to the disposable restored database | No new upgrade operations |
| `python -m testing.launch_dependencies database-down`, `qdrant-down`, `recovered`, around stopping/starting only named disposable services | Expected 503/200 transitions passed; PostgreSQL outage rechecked on final production-mode image |
| `python -m testing.launch_recovery queue-retry` plus real RAG worker and temporary isolated Qdrant shutdown | Durable retry observed; all six jobs eventually SUCCEEDED, no active admission claims |
| `docker exec mentra-launchgate-api python -m scripts.verify_http_readiness` | Existing non-unit body/media/Range/failure cleanup checks passed in final runtime |
| `python -m ruff check ... --select E9,F63,F7,F82`, Python AST parsing, `git diff --check` | Changed Python sources passed fatal/static checks and diff whitespace validation |

No unit tests were added or run. Initial startup sequencing caused one load
attempt before the API listener was ready; the actual measured run began after
readiness. The isolated Qdrant requires a nonempty configured API-key value even
without server authentication; the fixture uses a synthetic key over its private
network. Neither issue was represented as a production-provider failure.

### External requirements and final handoff

| Still open | Classification and precise action |
| --- | --- |
| Domains/host/proxy/firewall/TLS renewal | External deployment prerequisite: user has not chosen them. Supply actual HTTPS frontend/API origins, host/network layout and trusted proxy source addresses, provision certificates and verify publicly only after deployment authorization |
| Production credentials/provider policies | External configuration: populate private `.env.production` or inject equivalent secrets, database TLS/role settings, AI/Cloudinary/Qdrant account/collection/quotas; no secret values were invented or committed |
| Production data and backup policy | External operational acceptance: inspect actual head/namespace and legacy prerequisites, approve RPO/RTO/retention/off-host encrypted backup ownership, and verify a fresh coordinated production recovery point. The synthetic manual original restore does not establish the account's managed Cloudinary backup entitlement or retention |
| Deployment capacity/traffic cap | Environment-specific acceptance: repeat conservative representative load on the chosen host and actual database/network/provider limits. Verify overlap/admin connection allowance and all-worker heavy workloads; do not infer a public traffic limit from these small local runs |
| Release evidence refresh | Release recommendation: run remote CI and current dependency/OS-image scans at release; previous advisory results remain a dated snapshot. Exhaustive AI quality/failure coverage remains outside this bounded operational drill |

Use the ordered acceptance/rollback sequence in the updated runbook. This
continuation modifies deployment templates, image selection, frontend release
validation, database failure mapping, explicit storage suffix configuration,
standards and reusable non-unit launch drivers. It preserves the preceding
uncommitted hardening and regression sources. At that continuation handoff no new
migration, commit, push or public deployment had been performed. The subsequent
authorized final verification/commit is recorded below.

Verified final image identities (temporary tags, removed after acceptance):

- Backend: `sha256:a6b03e3b8a8f911bbec80412c845ef635613023d141105c1fee5ccf22c2af8af`.
- Frontend: `sha256:6bd588520ea11c8521cf9a3113611626ae2919a50ab10200ba2cf5f01dd6ec76`.

Final cleanup verified: both synthetic Cloudinary originals and their namespace
folder deleted; all ten continuation-created containers, the disposable database
volume, private network and verification images removed. The API and restored
RAG worker exited with code 0. Temporary certificates/private keys, synthetic
account state, original-byte exports, database dumps, logs, load/resource output,
browser traces/results and scratch/cache directories were removed. Docker now
contains only the original seven application containers, original two latest
application images and the two pre-existing volumes; original-byte backups and
model caches remain. Shared Docker build cache was not globally pruned.
Intentional acceptance/regression source files and this evidence summary remain.

## Final verification and commit review — 2026-10-25

The complete intended diff from both engineering rounds was reviewed before
staging. Final review corrected three configuration edge cases: browser origins
now canonicalize DNS case, IDNA, IPv6 spelling and default ports before CORS and
cookie-origin comparison; the production preflight rejects ambiguous duplicate
PostgreSQL sslmode values; and release URL validation rejects private/loopback,
wildcard and reserved local hostnames, including dotted localhost spellings.
The preflight's stale APP_ENV/storage diagnostic was also corrected.

A real PostgreSQL-backed HTTP exercise registered/authenticated with a mixed-case
HTTPS frontend origin containing explicit :443, verified the canonical CORS
response and Secure/HTTP-only cookie, and rejected a foreign cookie origin with
403. No new unit-test source was added for these checks.

| Final check | Result |
| --- | --- |
| Full tracked diff plus all new source/configuration/documentation files | Reviewed; prior user changes preserved |
| `npm run build`, `npm run check:theme`, `npm run check:ui` | Passed TypeScript/Vite, theme and UI static checks |
| Backend and release-mode frontend Docker builds | Passed against final runtime/configuration changes; synthetic HTTPS API origin used only for the local build check |
| Ruff `--select E9,F63,F7,F82 --no-cache` over application and changed verification scripts; AST parsing | Passed; 426 Python application/script/migration/testing files parsed |
| `npm audit --audit-level=moderate` | Zero reported vulnerabilities, including development/build dependencies |
| `pip_audit --path /usr/local/lib/python3.12/site-packages` in a separate final-image container | No known vulnerabilities among audited packages; CPU-tagged Torch skipped by scanner. Exact Torch 2.14.1 upstream PyPI advisory metadata separately returned zero records |
| Production preflight/release CLI configuration matrix | Accepted canonical synthetic HTTPS origins/public IPv6; rejected wildcard, private/loopback/reserved hosts, ambiguous TLS modes and unrestricted proxy trust |
| Base and merged production Compose validation | Passed; six backend services retain production mode/capability restrictions and both HTTP services have exactly one loopback listener |
| `python -m scripts.verify_http_readiness`, `python -m pip check` in final image | HTTP body/media/Range/lease cancellation checks passed; no broken requirements |
| `python -m testing.launch_migrations` against a newly created in-memory-filesystem PostgreSQL container | Legacy-upgrade/populated-downgrade refusal checks passed and their unique schemas were removed; existing database/volumes were not used |
| `playwright.mock.config.ts` browser regression selection | 63 passed initially; four initial failures involved page loading or the 18-route traversal budget. Three targeted reruns passed unchanged; the traversal passed in 47.7 seconds after marking only that multi-page case slow and allowing 10 seconds for each header. All 67 distinct scenarios passed across these runs; functional assertions remain intact |
| `npx playwright test --config .cache/final.integration.config.ts --output .cache/final-verification-integration` | All 22 auth/files/events/profile journeys passed in one run against real disposable PostgreSQL, with deterministic AI/storage/vector fixtures |
| Intended-file secret/artifact scan; local Markdown links; `git diff --check` | Passed configured-secret comparison and credential-pattern scan, artifact-path exclusion, link resolution and whitespace checks; not an exhaustive repository-history secret audit |

No unit tests were executed or added. Existing unit-suite CI commands were not
invoked locally, and this commit does not publish or trigger remote workflows.
Public HTTPS/DNS/firewall, production credentials/quotas, coordinated production
backup policy/restore acceptance and deployment-host capacity remain external
launch conditions. Previous live-provider and local TLS/recovery/load evidence
above remains dated evidence; this final pass did not repeat paid AI/Cloudinary
calls, public deployment, remote CI, an OS-image scan, or a production benchmark.
Public-environment checks cannot run without the chosen domains/host and deploy
authorization. Remote workflows were not triggered because no push is authorized;
Trivy/Grype were not installed for an OS-image scan. Those exclusions do not
change the bounded dependency-audit coverage described above.

### Files included in the final commit

The 56 intended paths below include application changes, non-unit verification sources, dependency constraints, deployment configuration and documentation.


```text
.env.example
.env.production.example
.github/workflows/backend-tests.yml
.github/workflows/supabase-migrations.yml
.gitignore
backend/app/assessments/worker.py
backend/app/core/config.py
backend/app/core/http_limits.py
backend/app/db/errors.py
backend/app/files/delivery.py
backend/app/files/provider.py
backend/app/files/README.md
backend/app/files/service.py
backend/app/langchain/repositories/checkpoint_tables.py
backend/app/rag/embeddings.py
backend/app/rag/worker.py
backend/Dockerfile
backend/requirements.lock
backend/requirements.txt
backend/scripts/rag_admin.py
backend/scripts/validate_production.py
backend/scripts/verify_http_readiness.py
backend/standards.md
backend/testing/launch_dependencies.py
backend/testing/launch_faults.py
backend/testing/launch_load.py
backend/testing/launch_migrations.py
backend/testing/launch_provider.py
backend/testing/launch_recovery.py
deploy/nginx.production.conf.template
docker-compose.production.yml
docker-compose.yml
docs/identity-and-postgresql.md
docs/persistent-chat.md
docs/production-readiness-2026-10-25.md
docs/production-readiness.md
docs/SETUP.md
frontend/.dockerignore
frontend/Dockerfile
frontend/playwright.launch.config.ts
frontend/playwright.mock.config.ts
frontend/scripts/validate-release.mjs
frontend/src/components/auth/AuthProvider.tsx
frontend/src/components/memories/MemoriesSettings.tsx
frontend/src/components/student-profile/StudentProfileProvider.tsx
frontend/src/services/files.ts
frontend/src/services/pageCache.ts
frontend/src/stores/chatStore.ts
frontend/src/utils/broadcastChannel.ts
frontend/standards.md
frontend/tests/chat-cache.spec.ts
frontend/tests/launch-https.spec.ts
frontend/tests/quiz-local.spec.ts
frontend/tests/readiness.spec.ts
frontend/tests/workspace-polish.spec.ts
README.md
```
