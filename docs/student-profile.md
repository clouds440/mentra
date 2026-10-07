# Student Profile and onboarding calibration

`app.student_profile` answers **Who am I teaching?** The separate `app.learner`
module answers **What specific concepts does this learner know?** Profile calibration
never registers concepts or writes learning evidence/concept mastery.

## Ownership and scope

The learner controls education level, field/major, primary goal, learning preference,
and explanation depth. `ProfileDetails` is the only public write contract for these
fields. AI output has a different strict schema containing only five broad estimates:
overall proficiency, reasoning, quantitative reasoning, comprehension, and domain
familiarity. It cannot include factual fields or preferences. Profile evidence is a
trusted server integration contract, not a client-accessible scoring endpoint.

Estimates carry value/confidence, counts, effective evidence weight, source counts,
last evidence time, and a short rationale. Applied evidence stores the validated AI
output, resulting estimates, context, and policy version. Unknown means a null value
and zero confidence. Values are provisional heuristics relative to the stated education
level, not calibrated probabilities, IQ, grades, or detailed curriculum mastery.

An eight-question screening assessment is intentionally limited. Its confidence is
capped at 0.55 overall and lower for sparsely sampled dimensions. The English v1 banks
are authored screening content, not psychometrically validated tests. Real learner
evaluation and broader evidence are needed before making stronger accuracy claims.

## Mandatory flow

1. An authenticated learner without a profile must provide all profile details.
   Blank/invalid information cannot be bypassed by skipping calibration or by calling
   chat directly. Existing accounts and future external identities use the same gate.
2. The profile is persisted, and Mentra offers a recommended 1–2 minute calibration.
   The learner may skip this assessment; estimated fields remain unknown.
3. Each selected answer is saved immediately. Refresh/login resumes the first
   unanswered question. Back navigation permits edits while the attempt is in progress.
4. Completing all eight answers stores deterministic evidence and completes onboarding
   before requesting AI evaluation. If the provider is unavailable, answers remain
   saved, estimates stay unknown, and the learner can enter Mentra and retry in Settings.

Settings provides profile viewing/editing, estimates with uncertainty, later calibration,
and evaluation retry. Changing education level resets broad estimates and invalidates
old calibration scope. Changing major resets domain familiarity and invalidates the
old calibration scope. Editing goals/preferences/depth preserves estimates. Changing
only the field's letter case does not reset scope. AI never invokes these factual edits.

## Controlled assessment and evaluation

`calibration/blueprints.py` contains seven genuinely distinct level banks: Primary,
Middle School, High School/Secondary, College/Intermediate, Undergraduate, Graduate,
and Other. `calibration/domains.py` supplies controlled familiarity variants for
computing, STEM, business, humanities, and health at the four advanced levels. Unmatched
fields use general academic/scientific reasoning; primary/middle and Other keep their
appropriate general banks. There are eight MCQ/true-false items per attempt, two per
sampled dimension. Overall proficiency uses the full set without duplicating items.

Blueprint IDs include content version, education level, and domain. Options are shuffled
for each attempt; the versioned private questions/keys/context are snapshotted in
PostgreSQL. APIs never expose keys or accept client-supplied scores. Publish a new
blueprint version when content/keys change; old attempts remain pinned to their snapshots.

`calibration/scoring.py` validates completeness and choices and deterministically
extracts per-item correctness, dimension, difficulty, prompt, and selected response.
`langchain/profile_evaluator.py` sends these items, dimension summaries, current
estimates, and the explicit profile context through the same application-shared
`MentraLLM` used for chat. It selects the registered `student_profile_evaluation`
source; each source has its own prompt module under `langchain/prompts/`. The shared
component binds LangChain tool-based structured output and validates it with Pydantic,
including numeric bounds. Profile policy then validates evidence references. Malformed,
unsupported, or fact-mutating output cannot be applied. Source selection stays in trusted
service code and is never supplied by the client.

`policy.py` centralizes updates. It anchors proposals to accumulated scored results,
requires sufficient evidence for an initial estimate, discounts interaction evidence,
caps each subsequent value shift at 0.08 (less for small interactions), and caps confidence
movement in either direction at 0.05. One textbook discussion cannot change a Primary
learner's education level or selected preferences. Unsupported dimensions stay unknown;
future estimates need stable provenance and independently meaningful observations.

## Service and persistence boundaries

`StudentProfileService` owns profile details and composes `CalibrationService` and
`ProfileEvidenceService`. Repository ports separate them from SQLAlchemy stores. All
rows/queries are scoped to the authenticated internal UUID `learner_id`. Per-learner
transactions serialize profile writes, and versions reject conflicting edits/answers.

The AI request runs outside the database transaction. A short claim lease prevents
duplicate requests from applying twice and permits recovery after a restart. Final
application rechecks ownership, context version, and claim identity under the lock.
An education/major edit during evaluation supersedes the old result. Database triggers
protect private calibration snapshots, finished answers, raw observations, and applied
evaluations. Composite foreign keys prevent cross-learner attempt/evidence references.

Alembic revision `20261007_0003` creates `student_profile`,
`student_calibration_attempt`, and `student_profile_evidence`. It does not change or
populate granular learner state. Compose runs migrations before backend startup.

Future trusted adapters can feed evidence without coupling profile updates to chat:

```python
profile_service = application.state.student_profile_service
evidence_id = profile_service.evidence.record(authenticated_learner_id, evidence_input)
updated_profile = await profile_service.evidence.evaluate(authenticated_learner_id, evidence_id)
context = profile_service.prompt_context(authenticated_learner_id)
```

Use stable source/item IDs on retries. A source cannot silently replace earlier results.
The compact prompt packet contains explicit details and bounded estimate/confidence
pairs. Future prompt consumers must treat its text as data, not instructions. The
current chat only enforces onboarding; automatic chat evidence extraction and persistent
profile prompt injection are intentionally not added here.

## Authenticated profile APIs

All routes are under `/api/v1/student-profile` and use the existing bearer/session-cookie
dependency. Cookie writes retain trusted-origin enforcement. Ownership never comes from
a request body.

| Method/path | Contract |
| --- | --- |
| `GET /student-profile` | Current profile, onboarding state, estimates, and version |
| `PUT /student-profile/details` | `{expected_version, details: ProfileDetails}` |
| `GET /student-profile/calibration` | Resumable/current assessment or null; no answer keys |
| `POST /student-profile/calibration` | Start or resume the current assessment |
| `PATCH /student-profile/calibration/{id}/answers` | `{expected_version, question_id, option_id}` |
| `POST /student-profile/calibration/{id}/complete` | `{expected_version}`; returns profile and evidence ID |
| `POST /student-profile/calibration/skip` | `{expected_version}`; requires complete information |
| `POST /student-profile/calibration/evaluate` | Retry saved calibration evaluation |

## EduVerse profile provisioning

`POST /api/v1/integrations/eduverse/students` accepts EduVerse's existing student ID,
its short-lived signed assertion, and a complete high-level profile:

```json
{
  "student_id": "existing-student-123",
  "token": "<EduVerse-signed JWT for this student>",
  "profile": {
    "education_level": "undergraduate",
    "field_of_study": "Computer science",
    "learning_goal": "Build confidence in problem solving",
    "learning_preference": "examples_first",
    "explanation_depth": "standard"
  }
}
```

Configure `AUTH_EXTERNAL_PROVIDERS.eduverse` with issuer, audience, algorithm, and
trusted **public** keys as described in [identity setup](identity-and-postgresql.md).
The signed subject (or configured `subject_claim`) must match `student_id` before any
provisioning. String and integer IDs are supported; booleans and whitespace-padded IDs
are rejected. No username, email, Mentra password, EduVerse password, or client-selected
learner UUID is accepted. No provider SDK, shared frontend secret, or EduVerse schema
change is required.

The first valid call creates/resolves the external mapping and initializes the profile
from the supplied explicit fields. It returns `201`, `profile_initialized: true`, the
internal learner UUID, current profile, and authenticated session. These fields satisfy
the mandatory information step, so the learner proceeds directly to the optional
calibration offer. Estimates remain unknown until scored evidence is evaluated.

Repeated calls return `200`, the same learner, and `profile_initialized: false`. They
preserve the student's existing facts, manual preferences, onboarding/calibration state,
and estimates. This is an initialization endpoint, not an automatic profile-sync API.
Native callers receive a bearer token; browsers requesting `X-Mentra-Session: cookie`
with a trusted origin receive only identity/profile and an HTTP-only cookie. External
sessions retain the signed assertion's expiry. A standalone Mentra account/password is
not created for an EduVerse student.

Identity mapping and profile initialization are each transactional and idempotent.
The HTTP adapter hands off a session only after profile initialization commits, so a
failure can be retried without overwriting or duplicating the learner/profile. This
establishes Mentra's API contract; EduVerse token issuance and its UI are not implemented.

## Verification

Use an explicit dedicated `TEST_DATABASE_URL` as in [PostgreSQL setup](identity-and-postgresql.md).

```powershell
$env:PYTHONPATH = 'backend'
$env:TEST_DATABASE_URL = 'postgresql://mentra:mentra_local@127.0.0.1:5432/mentra_test'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
Set-Location frontend
npm run build
npm run check:theme
npm run test:e2e
```

`test:auth` and `test:profile` run the respective browser subsets. Browser tests use real
auth/profile APIs, migrations, question banks, deterministic scoring, and PostgreSQL
persistence. Only the external AI evaluator uses a predictable test double (and an
explicit outage double); production always uses the configured model factory. Backend
tests also exercise the real model factory, LangChain tool schema, and structured parser
with controlled HTTP transport. Live-provider checks require usable provider balance.

Tests cover mandatory information, skip/unknown state, every bank/field variant,
resumption, malformed AI output, outages/retry, no granular mastery writes, conservative
evolution, ownership/immutable history, concurrency/leases, stale contexts, schema drift,
EduVerse subject/signature validation, repeated provisioning/manual-edit preservation,
mobile layouts, and Light/Dark/System themes.

Recovery checks also cover a committed answer whose HTTP response is lost, optimistic
conflicts from another editor, and a persistence failure during final estimate application.
The profile/evaluation transaction rolls back together; an expired claim can be retried
without counting the same evidence twice. See the [dated verification report](student-profile-verification.md)
for observed results and Docker image/startup checks.

Structured-output reference: [LangChain ChatOpenAI structured output](https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/with_structured_output).
