# Learner Engine

`LearnerService` is the public structural interface; `LearnerEngine` implements it.
Neither imports LangChain, a model provider, database configuration, authentication, or a database
adapter. Alembic migrates the PostgreSQL schema; application startup checks its revision and installs an engine
at `app.state.learner_service`. Other modules inject that service and import
schemas from `app.learner`, rather than querying learner tables.

## Basic workflow

```python
from app.learner import (
    ResolveLearningContextRequest, EvidenceSubmissionRequest,
    LearnerContextRequest, StudyRecommendationsRequest, LearningGoalRequest, PerformancePredictionRequest,
)

# learner = application.state.learner_service
# learner_id = authenticated_identity.learner_id (internal UUID, never an LLM argument).
context = learner.resolve_learning_context(ResolveLearningContextRequest(
    learner_id=learner_id, name="Database Systems", activate=True,
))

# Registry operations are trusted curation/bootstrap operations.
concept = learner.register_concept("Transitive Dependency", aliases=("TD",))
learner.link_context_concept(learner_id, context.context_id, concept.id)
learner.set_learning_goal(LearningGoalRequest(
    learner_id=learner_id, context_id=context.context_id, concept_id=concept.id,
    importance=0.9, target_difficulty=0.8,
))

result = learner.submit_evidence(EvidenceSubmissionRequest(
    learner_id=learner_id, concept_id=concept.id, context_id=context.context_id,
    source_type="QUIZ", source_id="assessment-42:question-3:attempt-1",
    item_id="question-bank:dependency-3", session_id="assessment-42", attempt_number=1,
    result="PARTIAL", score=2, max_score=4,
    difficulty=0.6, independence=1, occurred_at=graded_at,
))
packet = learner.get_relevant_context(LearnerContextRequest(
    learner_id=learner_id, query="Explain transitive dependency", max_concepts=8,
))
recommendations = learner.get_study_recommendations(
    StudyRecommendationsRequest(learner_id=learner_id, limit=5),
)
prediction = learner.predict_performance(PerformancePredictionRequest(
    learner_id=learner_id, concept_id=concept.id, difficulty=0.8,
))  # supported=False means insufficient evidence at this challenge level.
```

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `engine.py` | Facade and trusted registry/lifecycle operations |
| `concepts.py`, `normalization.py` | Exact identity/alias resolution, bounded suggestions, candidate review |
| `contexts.py` | Ownership, activation, activity, inactivity, explicit transitions |
| `evidence.py` | Validation, idempotency, atomic acceptance, confirmation, corrections, replay |
| `scoring/` | Separate mastery, confidence, retention policies and evidence diagnostics |
| `state.py` | Fresh policy projections and challenge-specific performance estimates |
| `ranking.py`, `retrieval.py` | Study/verification targets and bounded context packets |
| `calibration.py`, `assessment.py` | Initial targets and typed graded-question integration |
| `evaluation.py` | Chronological offline prediction, calibration, coverage and Brier metrics |
| `repositories/protocols.py` | Internal database-independent persistence port |
| `repositories/postgres.py` | Small composed SQLAlchemy PostgreSQL adapter |
| `repositories/postgres_parts/` | Session/mapping, concept, context, evidence, state, decision, retrieval, lifecycle queries |
| `repositories/tables/` | PostgreSQL tables, ownership constraints, and indexes |
| `repositories/migrations.py` | Atomic additive migrations; version 1 databases upgrade without losing evidence |

## Identity and context

Canonical IDs are stable UUIDs. Unicode/case/whitespace normalization and conservative
plural forms are lookup aids. Exact aliases resolve locally; ambiguous aliases remain
ambiguous. Lexical similarity provides suggestions, never automatic merges. Unknown
labels create candidates with stable IDs and occurrence counts; trusted review can
promote, merge, or discard them. Registering an existing alias reuses its identity.

An optional `SemanticResolver` can search and choose from a small existing candidate
set. Returned IDs must belong to that set, and confidence must meet 0.9. No provider
is required for the engine, and no embedding/model calls occur on exact lookups.

Explicit activation makes the previous active/related contexts dormant by default;
pass `exclusive=False` to retain multiple active contexts. Inactivity of 60 days
causes lazy dormancy on the next context-aware request. Activity records do not
silently reactivate dormant or archived contexts. Evidence and mastery survive every
context transition. Default recommendations consider active/related contexts;
explicitly requested owned contexts may include dormant/archived ones. Query terms
and graph relationships can recover relevant dormant knowledge. Archived contexts
require explicit selection. Ordinary packets contain at most 50 concepts (default
8), 20 context IDs, and three misconceptions per concept.

## Evidence and policy

Every submission needs a stable source ID and a timezone-aware occurrence time.
The same `(student, channel, source, canonical concept)` is a retry, not new evidence.
Retry payloads must match the original observation, including time and JSON metadata;
reuse of an ID for changed content raises `InvalidEvidenceError`. Preserve the original
timestamp when retrying. Batch ingestion is atomic and supports up to 2,000 observations
(including a 100-question assessment with 20 concept components per question).

`item_id` identifies the underlying question across reuse; `session_id` identifies the
assessment/practice session. Different grader source IDs cannot count the same item,
session, channel, concept and attempt twice. Reusing an item in another session is
practice with discounted contribution, not another independent item. Supply an actual
question-bank identity when a question appears in multiple assessments; the assessment
adapter otherwise uses assessment/question identity and cannot infer reused wording.

Evidence rows are immutable. Acceptance decisions are stored separately. Low extraction
confidence (below 0.8), missing handwritten extraction confidence, or grading confidence
below 0.5 produces a pending observation without changing state. `UNKNOWN` observations
are auditable without implying demonstrated mastery. Metadata cannot bypass these gates.
The ordinary OCR workflow should confirm/regrade text before submitting accepted
evidence. The engine's pending path is defense in depth for uncertain submissions.

`confirm_evidence(ConfirmEvidenceRequest(...))` is a trusted operation for an unchanged,
confirmed transcription. It records confirmation provenance and replays with confirmed
extraction confidence while preserving the original row. It cannot override uncertain
grading. A corrected transcription must be regraded and submitted as a new observation;
it must not confirm a grade calculated from different text. Confirmation retries are
idempotent, and stale pending revisions cannot overwrite an accepted newer grade.

To correct previously accepted grading, supply a new source ID and
`supersedes_evidence_id`. Both observations remain stored, and only the correction
contributes to recomputation. Corrections must refer to accepted evidence for the same
student and canonical concept, preserving known item/session/attempt identity.
`AssessmentObservations.revision` automatically supersedes the accepted earlier grade
for each item/session/attempt. A `supersedes_evidence_ids` mapping remains available for
explicit corrections. Older/equal revisions cannot replace a newer accepted grade.
New attempts use distinct source IDs and preserve
`attempt_number` and hint usage.

The `mastery-v2` baseline is a conservative evidence heuristic with a neutral prior;
its outputs and uncertainty bounds are **not empirically calibrated probabilities or
credible intervals**. Mastery is a summary of the highest supported challenge level,
not a probability of answering any arbitrary question correctly. Easy successes support
basic ability without implying advanced proficiency. `predict_performance` estimates a
normalized first-attempt score at a requested difficulty; it exposes support and broad
uncertainty when challenge coverage is missing. Packets include that target estimate.

Only explicitly independent first attempts (independence >= 0.8, no hints) at a known
difficulty update skill. Guided/retry/unknown-independence answers remain practice
observations; an entirely assisted history has `mastery=None`. Unknown assistance does
not imply hint dependence. Confidence requires distinct explicit item identities;
chat-only evidence cannot establish demonstrated status. Quality/channel, consistency,
and diverse items affect confidence separately from mastery.

Each easy/medium/hard challenge band maintains at most 12 effective observations.
New evidence revises current estimates at its own challenge level, so lifetime successes
cannot overwhelm recent failure and easy review cannot erase advanced demonstrations.
Caches of recent items, item coverage and recall days are bounded. This is a heuristic
tradeoff, not a learned forgetting or item-response model. Contradictions require two
new high-quality independent successes at the disputed difficulty to clear verification;
one easy success or repeated item cannot clear a harder concern.

Retention decays from the last demonstrated state, with slower decay after repeated
independent successes. Time never directly lowers mastery. Retention is calculated on
read, so no daily write job is needed. Spaced recall uses distinct UTC days; many answers
in one exam do not manufacture spaced practice. Failures never renew the successful
retention anchor, and easy answers do not renew harder demonstrations. Challenge-specific
prediction freshness uses that band's last observation, so recent easy activity cannot
hide stale advanced evidence. Policy versions are persisted with state;
confidence policy identity is retained in sufficient statistics. Inject new
`MasteryPolicy`, `ConfidencePolicy`, `RetentionPolicy`, or `RankingPolicy` implementations
for experiments. Change policy versions whenever their meaning changes, and explicitly
recompute historical state when switching policies. Reads and ingestion detect stale
policy identities (including configuration) and refresh affected projections lazily.

`recompute_learner_state` uses accepted, non-superseded evidence in occurrence order,
breaking equal-time ties by durable decision sequence. Older arrivals trigger replay;
ordinary chronological/equal-time updates stay incremental. PostgreSQL advisory locks
serialize writes for each learner and coordinate trusted ontology changes, with evidence, decisions, state, context activity, and audit committed
or rolled back together. Recommendations use batched reads and top-K selection over
eligible context concepts, without loading their evidence histories. Prompt size is
bounded independently of total learner history.

`set_learning_goal` stores context-specific importance and target challenge. Unspecified
importance defaults to neutral 0.5; it is not inferred personal value. Zero importance
excludes default study recommendations. Query/explicit context selection raises transient
relevance without modifying long-term knowledge. Prerequisite importance is scoped to
the learner's selected curriculum and trusted relations. Strong misconception claims
(confidence >= 0.8) enter prompt packets; uncertain claims remain internal observations.

## Consumer integrations

- **LangChain/LangGraph:** `app.langchain.learner_tools.create_learner_tools` returns
  structured tools usable in a `ToolNode` or chain. Identity is bound by server
  orchestration. Read tools are default; evidence recording requires explicitly bound
  `ObservationProvenance`. Tools cannot choose student identity, source provenance,
  extraction confidence, or mastery, and cannot confirm OCR or curate the ontology.
  `ChatService.reply(..., learner_context=packet)` accepts the compact typed packet.
- **RAG:** `app.rag.learner_scope.resolve_retrieval_scope` returns owned context IDs and
  selected concepts. Its Qdrant filter constrains student, context, and live document
  status; `LearnerDocumentMetadata` defines document provenance. Empty context scope
  matches no documents. Dormancy is evaluated from the learner service at retrieval
  time rather than duplicated into document records.
- **Assessments/OCR:** `LearnerAssessmentAdapter` exposes study, verification, and
  calibration targets and atomically maps typed `AssessmentObservations`/`GradedQuestion`
  results to evidence, preserving assessment/question/revision/rubric provenance. It
  applies the same extraction gate as every other producer. Multi-concept questions
  require `concept_grades` with separate `ConceptGrade` marks for every component;
  optional component difficulty overrides the question difficulty. Total marks are
  never copied onto every concept. Grade confidence and difficulty must come from the
  grading workflow; the learner cannot independently validate their correctness.
- **Calibration:** request 3–5 progressively difficult targets from a linked subject;
  self-report adjusts question difficulty only. Submit actual graded answers through
  the calibration evidence channel.

These are implemented and tested integration boundaries. The repository's current
anonymous HTTP chat has no trusted student identity and therefore does not automatically
attach learner history or record inferred answers. Authenticated/session-scoped graph
orchestration, document retrieval/ingestion, assessment generation/grading, OCR, and
onboarding screens are separate product workflows; they must call these contracts when
implemented. No unrestricted student-ID HTTP mutation routes are introduced.

## Lifecycle, audit, and evaluation

`merge_concepts` retains original concept/evidence identities, flattens redirects,
preserves aliases and context links, redirects relationships, combines misconceptions,
and replays affected learners. Overlapping source observations contribute once.
`split_concept` links new children to the broad parent and its contexts; children begin
without copied mastery. Parent evidence stays on the parent until a defensible
reclassification is implemented, avoiding invented knowledge on each child.

`explain_state` provides internal state statistics, accepted evidence IDs, and recent
audit events. Resolution responses include method, confidence, candidates, and alternatives;
recommendations/verification include reasons; context transitions retain their cause.
Keep this internal output out of ordinary prompts. `evaluate_predictions` reports MAE,
RMSE, and binned calibration error. `evaluate_observations` predicts before each outcome
updates isolated states and reports supported coverage, subgroup errors, neutral baseline,
and Brier/log loss for binary labels. It rejects unordered data and raw correction histories;
use canonical effective observations and avoid future regrade leakage in real evaluations.
Synthetic results verify behavior, not actual student proficiency or production accuracy.

Run from the repository root:

```powershell
$env:PYTHONPATH = 'backend'
# Set TEST_DATABASE_URL to a dedicated PostgreSQL test database first.
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/learner -v
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\python.exe backend/scripts/verify_learner.py --output docs/learner-synthetic-evaluation.json
```

The learner suite covers identity/candidates, context lifecycle/isolation, retention,
hints/confidence/contradictions, OCR gating, replay/version changes, migration upgrades,
corrections, concurrent writers/retries, merge/split behavior, bounded retrieval,
LangChain tools, compact chat context, assessment/calibration, RAG filtering, and metrics.

Persistence and identity setup: [PostgreSQL and authentication foundation](../../../../docs/identity-and-postgresql.md).
