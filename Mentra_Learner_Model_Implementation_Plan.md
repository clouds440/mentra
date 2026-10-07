# Mentra Learner Model --- Implementation Plan

**Status:** Learner Engine implemented and verified with synthetic end-to-end scenarios. Production accuracy remains unmeasured. External product workflows remain in their own implementation plans.\
**Audience:** Human developers and AI coding agents\
**Scope:** Learner Model / Learner Engine only\
**Architecture rule:** Other Mentra modules consume the Learner Engine
through stable public services/contracts. They must not directly depend
on its database tables, scoring formulas, or internal resolution logic.

------------------------------------------------------------------------

## Implementation progress

### Phase 0 — Contracts and Skeleton: COMPLETE

- [x] Added the `backend/app/learner` provider-independent package and public facade.
- [x] Defined typed request/response schemas, domain objects, repository protocols, and learner exceptions.
- [x] Added learner contract tests that run without LangChain or database initialization.
- [x] Documented the Learner Engine boundary in `backend/standards.md`.

### Phase 1 — Persistence Foundation: COMPLETE

- [x] Added a fresh PostgreSQL schema through SQLAlchemy 2.x and Alembic; startup verifies its revision through `backend/app/db/database.py`.
- [x] Added normalized canonical concepts, aliases, concept relations, student-scoped learning contexts, and many-to-many context/concept links.
- [x] Added learner state with separate mastery, estimate confidence, retention confidence, independent-success/hint/difficulty signals, and a state version.
- [x] Added immutable, provenance-bearing evidence with source idempotency constraints and indexed learner/concept/time lookup.
- [x] Added misconception and unresolved candidate-concept persistence.
- [x] Added uniqueness, foreign-key, value-range, and lookup constraints/indexes.
- [x] Added a database-agnostic repository protocol and modular PostgreSQL adapter with transaction support.
- [x] Added persistence tests for migration idempotency, canonical identity, aliases, student-scoped contexts, shared concepts, unique learner state, and evidence provenance/immutability.
- [x] Validated migrations, schema drift, transaction rollback, immutable history, concurrency, and ownership against PostgreSQL. The current full backend suite passes 114 tests.

### PostgreSQL and identity foundation: COMPLETE

- [x] Internal UUID `learner_id` for all learner-owned data; native ownership foreign keys prevent cross-user references.
- [x] Generic `DATABASE_URL`, SQLAlchemy 2.x repositories, and a fresh Alembic baseline. No data transfer was needed; obsolete SQLite code/import tooling was removed after dependency checks.
- [x] Per-learner transaction locks, sorted batch locks, ontology coordination, optimistic versions, and transaction-scoped lookup caches.
- [x] Separate standalone accounts with Argon2id passwords and hashed, expiring, revocable bearer sessions.
- [x] Generic public-key external-token verification with configured issuer/audience/algorithm and provider/subject mappings; concurrent first logins atomically provision one learner.
- [x] Authentication dependencies expose authenticated learner UUIDs; learner scoring/services remain independent of authentication. No EduVerse schema or password handling was introduced.
- [x] PostgreSQL test fixtures, migrations, Docker/configuration, dependencies, and setup documentation updated. Frontend production build passes; 1,200 synthetic observations retain identical scoring metrics and restart/replay behavior.

See [PostgreSQL and identity setup](docs/identity-and-postgresql.md). The existing chat UI remains anonymous; platform token issuance and embedded authenticated UI are future integration work.

### Phases 2-20 - Learner Engine implementation: COMPLETE

| Phase | Implemented capability |
| --- | --- |
| 2 | Canonical/alias normalization, bounded lexical suggestions, optional constrained semantic resolution, candidate review |
| 3 | Student-owned contexts, exclusive/multiple activation, activity, inactivity dormancy, explicit archive/reactivation |
| 4 | Validated immutable observations, pending decisions, source retries/conflicts, atomic batches and corrections |
| 5 | Replaceable mastery/confidence/retention heuristics, independent challenge windows, explicit uncertainty and retention-on-read |
| 6 | Contradiction detection, confidence reduction, verification ranking and two distinct difficulty-matched verification successes |
| 7 | Relevance-ranked bounded query/context/owned-graph packets with batched state and trusted misconception reads |
| 8 | Context-specific goals, importance, target difficulty, server-side study ranking and top-K results |
| 9 | Learner-owned RAG scope, document metadata and student/context/live-document Qdrant filtering |
| 10 | Typed assessment targets/results adapter with per-concept marks/difficulty, item/session identity and automatic grade revisions |
| 11 | Extraction gates, pending observations, trusted transcription confirmation and regraded corrections |
| 12 | Identity-bound LangChain tools usable by LangGraph; opt-in mutation with server-bound provenance |
| 13 | Progressive calibration targets; self-report guides difficulty without setting mastery |
| 14 | Internal evidence/state/context/lifecycle audit, state explanation and structured decision reasons |
| 15 | SQLite writer serialization, atomic updates, versioned state and retry deduplication |
| 16 | Persisted policy identities, explicit and stale-policy replay |
| 17 | Provenance-preserving merges, flattened redirects, preserved relations/aliases/contexts/misconceptions; uncertain split children |
| 18 | Behavioral, migration, concurrency and consumer tests, including real local Qdrant filters |
| 19 | Pre-outcome chronological evaluation, coverage/subgroup/Brier metrics, synthetic runner and injectable experimental policies; real-data calibration unvalidated |
| 20 | Concrete public facade, application startup wiring and documented consumer boundaries |

**Integration boundary:** This completes the Learner Engine and its executable consumer contracts. It does not implement the separate LangChain/LangGraph orchestration or RAG system plans, assessment generation/grading, OCR extraction, authentication, or onboarding UI. The current anonymous HTTP chat cannot identify a learner safely and does not automatically inject private history. Server orchestration can inject compact packets into `ChatService.reply` and bind the provided learner tools once trusted student identity exists. Assessment/OCR consumers submit typed graded observations; the learner does not generate questions or perform extraction.

**Modularity:** `repositories/sqlite.py` is a small composed adapter. Focused stores own concept, context, evidence, state, acceptance/audit, batched retrieval, connection/mapping and ontology lifecycle persistence. The `scoring/` package separates mastery, confidence, retention and diagnostics; `state.py` owns projection freshness and target predictions. Services remain independent of SQLite and providers.

**Policy limitation:** Baseline scores and intervals are versioned heuristics, not empirically calibrated probabilities or credible intervals. General mastery summarizes supported challenge coverage; target-level prediction exposes unknown coverage. Unknown assistance/difficulty cannot establish mastery. Personal importance comes from explicit goals with a neutral default. Split children start without inherited mastery; broad evidence stays on the parent until defensible reclassification is available. Synthetic labels cannot establish near-100% real-world accuracy.

**Verification:** 95 backend tests pass, including 72 learner tests. The 1,200-observation synthetic workflow covers eight trajectories, real SQLite persistence, restart/replay equality and context isolation. Chronological evaluation predicts before ingesting 1,050 eligible outcomes and reports 81.1% supported coverage, Brier score 0.134 versus neutral baseline 0.250, and subgroup errors. These values describe this synthetic fixture only. Further regressions cover independent imports, migrations, legacy OCR gates, corrections, concurrent writers/retries, assisted/reused items, skill changes, spaced recall, easy review, context goals, bounded prompts, LangChain tools, per-concept assessment/calibration, startup composition with mocked external infrastructure, and real local Qdrant filtering. See [behavioral audit](docs/learner-model-verification.md), [evaluation artifact](docs/learner-synthetic-evaluation.json), and `backend/app/learner/README.md`. Live LLM/OCR/grading and deployed infrastructure were not verified.

------------------------------------------------------------------------

## 1. Objective

Implement Mentra's Learner Engine as a reusable backend subsystem that
builds, maintains, queries, and verifies a computational model of a
student's knowledge.

The Learner Engine is not an LLM memory dump and is not a
`concept_name -> score` dictionary. It owns:

-   canonical concept identity;
-   concept aliases and relationships;
-   learning contexts and their lifecycle;
-   immutable learning evidence;
-   learner concept state;
-   mastery estimates;
-   estimate confidence;
-   retention confidence;
-   misconceptions and observations;
-   evidence aggregation;
-   context-aware learner retrieval;
-   study-priority ranking;
-   active mastery verification;
-   safe state updates from other Mentra modules.

The engine must remain useful if the LLM provider is replaced.

Core principle:

> **LLMs may propose semantic meaning and structured evidence. Mentra
> owns identity, state, policy, and persistence.**

------------------------------------------------------------------------

## 2. Module Boundary

Implement the Learner Engine as an independent backend domain module.

Recommended structure:

``` text
backend/app/
├── learner/
│   ├── __init__.py
│   ├── models/                 # domain objects, not ORM leakage
│   ├── schemas/                # public request/response contracts
│   ├── services/
│   │   ├── learner_service.py
│   │   ├── concept_service.py
│   │   ├── context_service.py
│   │   ├── evidence_service.py
│   │   ├── mastery_service.py
│   │   ├── recommendation_service.py
│   │   └── verification_service.py
│   ├── repositories/           # persistence interfaces + SQLite impl
│   ├── resolution/             # concept resolution pipeline
│   ├── scoring/                # mastery/confidence/retention policies
│   ├── ranking/                # recommendation / verification ranking
│   └── exceptions.py
│
├── db/
├── langchain/
├── rag/
├── assessments/
└── api/
```

Exact filenames may be adapted to the existing repository conventions.
Preserve the boundaries.

### Dependency direction

``` text
API ───────────────┐
LangChain ─────────┤
RAG ───────────────┤
Assessments ───────┼──► Learner Engine public services
Answer Sheet ──────┤
Onboarding ────────┘
                         │
                         ▼
                  Learner internals
                         │
                         ▼
                       SQLite
```

Other modules **must not**:

-   update learner tables directly;
-   invent concept IDs;
-   calculate mastery independently;
-   calculate retention independently;
-   decide whether an extracted concept is canonical;
-   read ORM entities and depend on their internal shape;
-   duplicate learner-ranking logic.

------------------------------------------------------------------------

# Phase 0 --- Contracts and Skeleton

## Goal

Create the module boundaries before implementing algorithms.

## Tasks

1.  Create the `learner` domain package.
2.  Define repository interfaces.
3.  Define public service interfaces.
4.  Define typed request/response schemas.
5.  Define learner-specific exceptions.
6.  Add unit-test structure.
7.  Do not implement LLM calls in the learner core.
8.  Do not expose ORM/database models as public contracts.

## Initial public facade

Prefer one high-level facade for external modules:

``` python
class LearnerService:
    def resolve_concept(...): ...
    def submit_evidence(...): ...
    def get_concept_state(...): ...
    def get_relevant_context(...): ...
    def get_study_recommendations(...): ...
    def get_verification_candidates(...): ...
    def activate_learning_context(...): ...
    def get_active_contexts(...): ...
```

Specialized internal services may exist behind this facade.

## Acceptance criteria

-   Other modules can import learner contracts without importing
    SQLite/ORM internals.
-   Learner unit tests can run without LangChain.
-   Learner core can run without an LLM provider.

------------------------------------------------------------------------

# Phase 1 --- Persistence Foundation

## Goal

Create the minimum data model required to preserve identity, evidence,
learner state, and context.

## Required entities

### `learning_context`

Represents a current or historical area of study.

Suggested fields:

``` text
id
name
description
status
relevance_score
created_at
last_activity_at
activated_at
dormant_at
archived_at
```

Supported lifecycle states:

``` text
ACTIVE
RELATED
DORMANT
ARCHIVED
```

Do not treat context status as mastery.

------------------------------------------------------------------------

### `concept`

Canonical concept registry.

Suggested fields:

``` text
id
canonical_name
description
status
created_at
updated_at
```

`id` must be stable and independent of wording.

------------------------------------------------------------------------

### `concept_alias`

``` text
id
concept_id
alias
normalized_alias
source
confidence
created_at
```

Aliases may include pluralization, abbreviations, alternative
terminology, or provider-specific wording.

------------------------------------------------------------------------

### `concept_relation`

Support relationships such as:

``` text
PARENT_OF
PREREQUISITE_OF
RELATED_TO
```

Suggested fields:

``` text
id
source_concept_id
target_concept_id
relation_type
confidence
created_at
```

------------------------------------------------------------------------

### `context_concept`

Many-to-many relationship between concepts and learning contexts.

A concept may be relevant to more than one context.

------------------------------------------------------------------------

### `learner_concept_state`

Derived/current learner belief.

Suggested fields:

``` text
student_id
concept_id
mastery
estimate_confidence
retention_confidence
evidence_count
independent_successes
hint_dependency
difficulty_tested
last_evidence_at
last_verified_at
updated_at
version
```

Do not store only one generic `score`.

------------------------------------------------------------------------

### `learning_evidence`

Evidence should be durable and auditable.

Suggested fields:

``` text
id
student_id
concept_id
context_id
source_type
source_id
result
score
max_score
difficulty
independence
hint_count
attempt_number
evidence_confidence
extraction_confidence
occurred_at
created_at
metadata_json
```

Potential `source_type` values:

``` text
CHAT
QUIZ
MOCK_EXAM
HANDWRITTEN_ASSESSMENT
EXERCISE
CALIBRATION
MANUAL_CONFIRMATION
```

Evidence should preferably be immutable after acceptance. Corrections
should be represented explicitly rather than silently rewriting history.

------------------------------------------------------------------------

### `misconception`

Suggested fields:

``` text
id
student_id
concept_id
context_id
description
confidence
status
first_observed_at
last_observed_at
resolved_at
```

------------------------------------------------------------------------

### Candidate concepts

Unresolved concepts must not immediately enter the canonical registry.

Create a candidate representation:

``` text
candidate_concept
├── id
├── proposed_name
├── normalized_name
├── context_id
├── first_seen_at
├── last_seen_at
├── occurrence_count
├── resolution_status
└── metadata
```

## Database constraints

Add constraints/indexes for:

-   canonical concept identity;
-   normalized aliases;
-   learner + concept state uniqueness;
-   evidence lookup by learner/concept/time;
-   active context queries;
-   context/concept relationships;
-   source provenance.

## Acceptance criteria

-   Duplicate learner state cannot exist for the same learner/concept
    pair.
-   Evidence can be traced to its source.
-   Concepts use stable IDs.
-   Historical evidence remains available after aggregate state changes.

------------------------------------------------------------------------

# Phase 2 --- Canonical Concept Registry

## Goal

Prevent LLM wording from becoming learner-model identity.

Example problem:

``` text
database
databases
DBMS
database systems
```

These must not automatically become four independent learner keys.

## Resolution pipeline

Implement concept resolution in stages:

``` text
raw extracted concept
        ↓
normalize
        ↓
canonical/alias exact match
        ↓
lexical/fuzzy candidate search
        ↓
semantic candidate search
        ↓
optional constrained LLM disambiguation
        ↓
existing canonical concept
        OR
candidate concept
```

### Stage 1 --- normalization

Normalization may include:

-   trim whitespace;
-   case normalization;
-   Unicode normalization;
-   safe punctuation normalization;
-   conservative singular/plural handling where appropriate.

Normalization is for lookup, not identity.

### Stage 2 --- exact alias lookup

If a normalized alias maps uniquely to a concept, return the canonical
concept immediately.

No LLM call is needed.

### Stage 3 --- fuzzy candidate lookup

Return a small ranked candidate set.

Do not automatically merge merely because strings look similar.

### Stage 4 --- semantic lookup

Use embeddings if required to find semantically similar concepts.

The concept registry may maintain semantic representations for
resolution.

### Stage 5 --- constrained semantic/LLM resolution

If ambiguity remains, an LLM may choose among a **small existing
candidate set** using the surrounding educational context.

The LLM is resolving meaning, not assigning database identity.

### Stage 6 --- unresolved concept

If confidence remains below threshold:

``` text
DO NOT create canonical concept
        ↓
create/update candidate concept
        ↓
collect repeated evidence
        ↓
later promote / merge / discard
```

## Public contract

``` python
resolve_concept(
    label: str,
    context_id: str | None,
    surrounding_text: str | None,
) -> ConceptResolution
```

Suggested response:

``` json
{
  "status": "resolved",
  "concept_id": "c_004",
  "canonical_name": "Transitive Dependency",
  "confidence": 0.96,
  "method": "alias"
}
```

Possible statuses:

``` text
resolved
ambiguous
candidate
rejected
```

## Acceptance tests

-   `Transitive Dependency` and `transitive dependencies` resolve
    identically.
-   A new provider using different wording does not create duplicate
    learner state.
-   Ambiguous phrases do not silently create concepts.
-   Candidate concepts can later be promoted or merged.

------------------------------------------------------------------------

# Phase 3 --- Learning Context Manager

## Goal

Make Mentra focus on what the student is learning now without deleting
old knowledge.

### Critical distinction

Mentra tracks three separate dimensions:

``` text
mastery
= how well the student demonstrated the concept

retention confidence
= how confident Mentra is that the knowledge is still retained

context relevance
= whether the concept matters to what the student is currently studying
```

Never collapse these into one score.

## Context behavior

Example:

``` text
Python
status: ACTIVE
last_activity: today

Database Systems
status: DORMANT
last_activity: five months ago
```

Database knowledge remains stored but should not pollute ordinary Python
tutoring or recommendations.

## Context activation signals

Context relevance may use:

-   explicit user goal;
-   recent questions;
-   recent assessments;
-   recently used/uploaded materials;
-   recent concept activity;
-   repeated interactions in the domain.

Explicit user intent has high priority.

Example:

``` text
"I have a database exam next week."
```

should be capable of reactivating the database context immediately.

## Dormancy

Contexts with no meaningful activity may become dormant.

Do not delete their concepts, evidence, assessments, or RAG documents.

## Cross-context access

Dormancy is not a hard wall.

Example:

``` text
"Is a Python dictionary similar to a database table?"
```

The learner/retrieval layer may temporarily use relevant dormant
database knowledge.

## Public contracts

``` python
activate_learning_context(...)
record_context_activity(...)
get_active_contexts(...)
resolve_learning_context(...)
get_related_contexts(...)
transition_context_state(...)
```

## Acceptance tests

-   Switching from databases to Python removes database concepts from
    default recommendations.
-   Explicit database questions reactivate or temporarily access the
    database context.
-   Historical database mastery remains intact.
-   A concept can belong to multiple contexts.

------------------------------------------------------------------------

# Phase 4 --- Evidence Ingestion

## Goal

Create one safe path through which every module contributes learning
evidence.

Other modules submit **observations**, not mastery values.

Bad:

``` python
learner.mastery["3nf"] = 0.91
```

Correct:

``` python
learner.submit_evidence(
    concept_id=...,
    result=...,
    difficulty=...,
    independence=...,
    ...
)
```

The Learner Engine decides the state update.

## Evidence input contract

Create a typed schema similar to:

``` python
class EvidenceSubmission:
    student_id: str
    concept_id: str
    context_id: str | None
    source_type: EvidenceSource
    source_id: str | None

    result: EvidenceResult
    score: float | None
    max_score: float | None

    difficulty: float | None
    independence: float | None
    hint_count: int
    attempt_number: int

    evidence_confidence: float
    extraction_confidence: float

    occurred_at: datetime
    metadata: dict
```

Possible results:

``` text
CORRECT
PARTIAL
INCORRECT
UNKNOWN
```

## Evidence weighting factors

The eventual state update may consider:

``` text
correctness
+ partial correctness
+ difficulty
+ independence
+ hints
+ attempts
+ recency
+ evidence confidence
+ extraction confidence
+ assessment channel
+ repeated consistency
```

A difficult independent handwritten answer should generally be stronger
evidence than a chat answer obtained after several hints.

## Safety rules

-   Low-confidence extraction must not silently mutate mastery.
-   Evidence with unresolved concepts must not update canonical learner
    state.
-   Evidence must have provenance.
-   Repeated evidence should matter more than isolated events.
-   One anomalous failure should not instantly erase stable mastery.

## Public contract

``` python
submit_evidence(evidence: EvidenceSubmission) -> EvidenceResult
```

The response should identify:

-   accepted/rejected/pending;
-   affected canonical concept;
-   resulting learner-state version;
-   whether verification was triggered.

------------------------------------------------------------------------

# Phase 5 --- Mastery and Confidence Engine

## Goal

Compute learner beliefs from evidence.

## Required state dimensions

### Mastery

The current estimate of demonstrated capability.

### Estimate confidence

How certain Mentra is that the mastery estimate is accurate.

This depends on evidence amount, quality, consistency, and coverage.

### Retention confidence

How certain Mentra is that previously demonstrated knowledge is still
retained.

This may decline when evidence becomes stale.

## Critical rule

Do **not** implement:

``` text
mastery = mastery * 0.99 every day
```

Time passing is not evidence that the student became worse.

Instead:

``` text
mastery remains the last evidence-based estimate

retention_confidence
    ↓ as evidence becomes stale
```

## Retention decay inputs

Design the policy so it can later account for:

``` text
time since evidence
evidence count
repeated successful recall
difficulty demonstrated
independence
historical stability
```

A concept demonstrated independently many times should lose retention
confidence more slowly than a concept answered correctly once.

## Policy abstraction

Do not hard-code formulas throughout services.

Create replaceable policies:

``` python
class MasteryPolicy(Protocol):
    def update(...): ...

class RetentionPolicy(Protocol):
    def calculate(...): ...

class ConfidencePolicy(Protocol):
    def calculate(...): ...
```

This allows future comparison between:

-   initial heuristic;
-   Bayesian Knowledge Tracing;
-   custom probabilistic model;
-   research variants.

## Recomputability

Prefer designs where learner state can be recomputed from accepted
evidence.

Store derived state for performance, but keep evidence as the durable
source.

## Acceptance tests

-   Time alone changes retention confidence, not mastery.
-   Strong repeated evidence produces greater estimate confidence.
-   Hinted success contributes less than independent success.
-   State updates are deterministic for the same evidence and policy
    version.

------------------------------------------------------------------------

# Phase 6 --- Contradiction Handling and Active Mastery Verification

## Goal

Mentra should actively verify uncertain beliefs instead of treating
every answer as absolute truth.

Example:

``` text
Existing mastery: 0.91
Existing confidence: high

Student suddenly fails one question
        ↓
do not collapse mastery
        ↓
mark contradiction
        ↓
reduce certainty where appropriate
        ↓
schedule targeted verification
```

## Verification candidates

A concept becomes a verification candidate when:

-   mastery is high but contradictory evidence appears;
-   estimate confidence is low;
-   retention confidence is low and the concept is relevant again;
-   evidence is inconsistent;
-   the concept is important as a prerequisite.

## Public contract

``` python
get_verification_candidates(
    student_id: str,
    context_ids: list[str] | None,
    limit: int,
) -> list[VerificationCandidate]
```

Return enough information for the Assessment Engine to generate an
appropriate question.

Example:

``` json
{
  "concept_id": "c_004",
  "reason": "contradictory_evidence",
  "mastery": 0.88,
  "estimate_confidence": 0.51,
  "retention_confidence": 0.73,
  "recommended_difficulty": 0.70
}
```

## Integration

The Assessment Engine consumes this API.

The Learner Engine does not need to generate the natural-language
question itself.

------------------------------------------------------------------------

# Phase 7 --- Context-Aware Learner Retrieval

## Goal

Never dump the entire learner model into an LLM prompt.

Even with hundreds or thousands of concepts, prompt size should depend
mainly on current relevance.

## Retrieval pipeline

``` text
user request
    ↓
resolve learning context
    ↓
resolve concepts
    ↓
expand small concept-graph neighborhood if useful
    ↓
fetch learner state for those concepts
    ↓
fetch relevant misconceptions / evidence summaries
    ↓
construct compact learner-context packet
```

## Public API for LangChain

This is a major integration surface.

``` python
get_relevant_context(
    student_id: str,
    query: str,
    context_ids: list[str] | None = None,
    max_concepts: int = 8,
) -> LearnerContextPacket
```

Example result:

``` json
{
  "active_contexts": ["Database Systems"],
  "concepts": [
    {
      "concept_id": "c_004",
      "name": "Transitive Dependency",
      "mastery": 0.34,
      "estimate_confidence": 0.88,
      "retention_confidence": 0.91,
      "misconceptions": [
        "Confuses transitive dependency with partial dependency"
      ]
    },
    {
      "concept_id": "c_003",
      "name": "Functional Dependency",
      "mastery": 0.79,
      "estimate_confidence": 0.84
    }
  ]
}
```

LangChain can serialize this compact packet into the LLM context.

LangChain must not query learner tables itself.

## Optional structured retrieval modes

The API may support intent-specific modes:

``` text
TUTORING
EXPLANATION
ASSESSMENT
RECOMMENDATION
REVIEW
```

Different modes may select different learner information without
changing the public architecture.

------------------------------------------------------------------------

# Phase 8 --- Study Recommendation Engine

## Goal

Answer questions such as:

``` text
"What should I study?"
"What are my weakest points?"
"What should I revise before the exam?"
```

without sending the entire learner model to an LLM.

## Candidate filtering

Start with:

``` text
ACTIVE contexts
+ explicitly requested contexts
+ relevant RELATED contexts
```

Dormant/archived contexts are excluded by default.

## Ranking inputs

A configurable ranking policy may consider:

``` text
low mastery
low retention confidence
low estimate confidence
prerequisite importance
current context relevance
recent goals
assessment performance
contradictory evidence
```

Illustrative only:

``` text
priority =
    weakness
    + retention_risk
    + uncertainty
    + prerequisite_importance
    + context_relevance
```

Do not freeze arbitrary weights as architectural truth.

## Public contract

``` python
get_study_recommendations(
    student_id: str,
    context_ids: list[str] | None,
    limit: int = 5,
) -> list[StudyRecommendation]
```

Example:

``` json
[
  {
    "concept_id": "c_021",
    "name": "Recursion",
    "reason": "low_mastery",
    "priority": 0.91
  },
  {
    "concept_id": "c_004",
    "name": "Third Normal Form",
    "reason": "retention_uncertain",
    "priority": 0.76
  }
]
```

The LLM may explain the recommendations conversationally.

The LLM must not perform the raw ranking over the entire learner model.

------------------------------------------------------------------------

# Phase 9 --- RAG Integration

## Goal

Allow the Learner Engine and RAG Engine to cooperate without becoming
coupled.

The Learner Engine owns learning contexts and concept identity.

The RAG Engine owns document ingestion, chunks, embeddings, retrieval,
and source provenance.

## Required RAG metadata

Documents/chunks should be capable of carrying:

``` text
document_id
learning_context_id
concept_ids where known
status
created_at
last_used_at
source provenance
```

RAG lifecycle should align with learner context lifecycle:

``` text
ACTIVE context
→ search heavily

RELATED context
→ search when useful

DORMANT context
→ exclude by default

ARCHIVED
→ exclude unless explicitly requested
```

## Integration contract

The RAG module should be able to ask:

``` python
learner_service.resolve_learning_context(...)
learner_service.resolve_concept(...)
learner_service.get_active_contexts(...)
```

The Learner Engine should not perform vector retrieval itself.

The orchestration layer may combine:

``` text
Learner Context Packet
+
RAG Retrieved Material
+
Current User Request
        ↓
LLM
```

## Cross-context retrieval

A dormant context may be temporarily included when:

-   the user explicitly references it;
-   the query compares two domains;
-   semantic relevance is unusually strong;
-   it is a prerequisite/related concept useful for teaching.

------------------------------------------------------------------------

# Phase 10 --- Assessment Integration

## Goal

Make assessments both consumers and producers of learner intelligence.

## Assessment Engine consumes

``` python
get_study_recommendations(...)
get_verification_candidates(...)
get_relevant_context(...)
```

These allow it to select:

-   weak concepts;
-   uncertain concepts;
-   retention-risk concepts;
-   prerequisite concepts;
-   occasional strong control concepts.

## Assessment Engine produces

After grading:

``` python
submit_evidence(...)
```

for every relevant concept/question.

Generated assessment metadata should preserve:

``` text
assessment_id
question_id
concept_ids
difficulty
marks
rubric
```

This allows evidence to be mapped precisely back to canonical concepts.

------------------------------------------------------------------------

# Phase 11 --- Handwritten Answer / OCR Integration

## Goal

Use handwritten assessments as an independent evidence channel.

Pipeline:

``` text
Mentra-generated assessment
        ↓
student answers on paper
        ↓
upload image/scan
        ↓
OCR
        ↓
question/answer mapping
        ↓
grading
        ↓
concept-level evidence
        ↓
Learner Engine
```

## OCR safety gate

If OCR confidence is below threshold:

``` text
DO NOT submit durable learning evidence
        ↓
show extracted answer
        ↓
student confirms/corrects
        ↓
grade confirmed text
        ↓
submit evidence
```

The Answer Sheet Engine must never directly update mastery.

It only submits evidence through the Learner Engine.

------------------------------------------------------------------------

# Phase 12 --- LangChain / Agent Tool Integration

## Goal

Expose learner intelligence as explicit tools instead of injecting raw
database state into every chain.

Recommended tools:

``` text
get_active_learning_contexts
get_relevant_learner_context
get_student_weaknesses
get_study_recommendations
get_verification_candidates
resolve_student_concept
record_learning_evidence
```

### Read tools

Read tools should be safe for normal chains/agents:

``` python
get_relevant_learner_context(query)
get_study_recommendations(...)
get_active_learning_contexts()
```

### Mutation tools

Mutation must be more constrained.

An LLM should not be given a generic:

``` text
set_mastery(concept, 0.9)
```

tool.

Instead:

``` text
record_learning_evidence(...)
```

with validation and provenance.

The Learner Engine then determines the state mutation.

## Tool-output principle

Return structured, compact data.

Do not return hundreds of learner records unless explicitly required by
an internal administrative/debugging operation.

------------------------------------------------------------------------

# Phase 13 --- Onboarding / Initial Calibration

## Goal

Bootstrap the learner model when SQLite contains no meaningful learner
evidence.

Flow:

``` text
minimal student/education context
        ↓
selected subject/topic
        ↓
3–5 progressively targeted questions
        ↓
evidence submissions
        ↓
initial concept states
        ↓
normal adaptive learning begins
```

Self-reported proficiency may guide calibration but must not be treated
as equivalent to demonstrated mastery.

The exact onboarding questions are intentionally not frozen in this
plan.

------------------------------------------------------------------------

# Phase 14 --- Observability, Auditability, and Debugging

## Goal

Make learner decisions explainable during development and evaluation.

Provide internal/debug facilities for:

``` text
Why does Mentra think this concept has mastery 0.72?
Which evidence contributed?
Why is this concept recommended?
Why was this context activated?
Why did this concept resolve to c_004?
Why was verification requested?
```

Recommended internal explanation objects:

``` python
StateUpdateTrace
ConceptResolutionTrace
RecommendationTrace
ContextTransitionTrace
```

These are invaluable for both debugging and research evaluation.

Do not expose sensitive/raw internals unnecessarily to normal LLM
prompts.

------------------------------------------------------------------------

# Phase 15 --- Concurrency and State Versioning

## Goal

Prevent lost updates when multiple modules submit evidence close
together.

At minimum:

-   add a version/revision field to derived learner state;
-   update state transactionally;
-   make evidence insertion and state aggregation atomic where
    practical;
-   ensure duplicate evidence submission can be detected when a stable
    source ID exists;
-   design `submit_evidence` to be idempotent where possible.

Example:

``` text
Quiz grader submits evidence
Chat evaluator submits evidence
        ↓
both must survive
        ↓
no last-write-wins mastery corruption
```

Do not allow callers to send an entire replacement learner-state object.

------------------------------------------------------------------------

# Phase 16 --- Policy Versioning and Recalculation

## Goal

Allow Mentra's learner algorithm to improve without making historical
data unusable.

Store the version of the scoring policy used to produce derived state.

Example:

``` text
mastery_policy_version = "v1"
retention_policy_version = "v1"
```

Because evidence is retained, a future migration can:

``` text
load accepted evidence
        ↓
apply policy v2
        ↓
recompute learner state
```

Do not make today's heuristic impossible to replace.

------------------------------------------------------------------------

# Phase 17 --- Concept Merge / Split Support

## Goal

Prepare for ontology corrections.

### Merge

Example:

``` text
"DB Normal Forms"
and
"Database Normalization"

later determined to represent the same canonical concept
```

A merge operation must:

-   preserve aliases;
-   redirect relationships;
-   preserve evidence;
-   migrate learner state safely;
-   preserve provenance;
-   avoid duplicate counting;
-   mark old concept identity as redirected/deprecated rather than
    silently deleting history.

### Split

A broad concept may later need subdivision.

Example:

``` text
Normalization
        ↓
1NF
2NF
3NF
BCNF
```

Do not blindly copy the parent's mastery to all children.

Historical evidence should be re-associated only where defensible;
otherwise children begin with uncertain/insufficient evidence.

This phase may be implemented after the initial MVP, but earlier schema
decisions must not make it impossible.

------------------------------------------------------------------------

# Phase 18 --- Testing Strategy

## Unit tests

Test deterministic learner logic without LLM calls:

-   normalization;
-   alias matching;
-   context transitions;
-   mastery updates;
-   confidence calculation;
-   retention decay;
-   recommendation ranking;
-   contradiction detection;
-   evidence validation;
-   idempotency;
-   policy versioning.

## Integration tests

Test:

``` text
Assessment → evidence → learner state
Chat/LangChain → relevant learner context
RAG → learning context filtering
OCR confirmation → evidence
Context switch → recommendation changes
```

## Required scenario tests

### Scenario A --- Duplicate terminology

``` text
LLM emits "database"
later emits "databases"
```

Expected: same canonical concept where semantically appropriate.

### Scenario B --- Forgotten but historically mastered

``` text
mastery = high
five months without evidence
```

Expected:

``` text
mastery remains historical
retention confidence decreases
```

### Scenario C --- Old irrelevant subject

Student switches from Database Systems to Python.

Expected:

-   database context becomes dormant;
-   database concepts disappear from ordinary recommendations;
-   historical learner data remains intact.

### Scenario D --- General recommendation

Student has 100+ concepts.

Expected:

-   Learner Engine ranks active candidates;
-   LLM receives only selected concepts;
-   prompt size does not grow linearly with total learner history.

### Scenario E --- Cross-context question

Student asks:

``` text
"How is a Python dictionary different from a database table?"
```

Expected: relevant dormant database context may be included.

### Scenario F --- Contradictory evidence

High-mastery concept receives one failure.

Expected:

-   no catastrophic mastery collapse;
-   confidence may change;
-   targeted verification may be scheduled.

### Scenario G --- Low OCR confidence

Expected: no mastery update until transcription is confirmed.

### Scenario H --- Provider swap

Expected: learner identity, evidence, state, context, ranking, and
verification continue working.

------------------------------------------------------------------------

# Phase 19 --- Research/Evaluation Hooks

Do not tightly couple these to production behavior, but preserve the
ability to measure:

``` text
predicted mastery vs actual assessment performance
weakness prediction accuracy
random questioning vs active mastery verification
base retrieval vs context-aware retrieval
retention prediction
effect of handwritten independent evidence
concept-resolution accuracy
```

Possible metrics:

``` text
prediction error
calibration error
accuracy/F1 where applicable
information gained per assessment question
concept-resolution precision
retrieval Recall@K / MRR / nDCG
OCR CER / WER
```

The learner engine should make experimental policies swappable where
feasible.

------------------------------------------------------------------------

# Phase 20 --- Final Integration Contract

The Learner Engine is considered properly integrated when every external
module follows this pattern:

``` text
External Module
      │
      │ structured request
      ▼
LearnerService
      │
      ├── resolves identity
      ├── applies context
      ├── validates evidence
      ├── executes learner policy
      ├── persists state
      └── returns structured result
```

Never:

``` text
External Module
      ↓
learner SQLite tables
      ↓
manual score changes
```

------------------------------------------------------------------------

# Public API Summary

The exact Python signatures may evolve, but equivalent capabilities must
exist.

``` python
# Concept identity
resolve_concept(...)
get_concept(...)
get_related_concepts(...)

# Learning contexts
resolve_learning_context(...)
activate_learning_context(...)
record_context_activity(...)
get_active_contexts(...)
get_related_contexts(...)

# Evidence / mutation
submit_evidence(...)

# Learner state
get_concept_state(...)
get_concept_states(...)
get_relevant_context(...)

# Adaptive decisions
get_study_recommendations(...)
get_verification_candidates(...)

# Internal/admin lifecycle
merge_concepts(...)
split_concept(...)
recompute_learner_state(...)
```

Mutation APIs must be stricter than read APIs.

------------------------------------------------------------------------

# Implementation Order

Agents should implement in this order unless an existing repository
dependency requires a small adjustment:

``` text
1. Module contracts / facade
2. Persistence entities + migrations
3. Canonical concept registry
4. Concept resolver
5. Learning context manager
6. Evidence ingestion
7. Mastery / estimate confidence policies
8. Retention-confidence policy
9. Contradiction detection
10. Context-aware learner retrieval
11. Study recommendation ranking
12. Active mastery verification
13. LangChain tools
14. RAG integration
15. Assessment integration
16. OCR / handwritten evidence integration
17. Calibration
18. Audit/debug traces
19. Concurrency/idempotency
20. Policy versioning/recomputation
21. Concept merge/split lifecycle
22. Research/evaluation hooks
```

Each phase should include:

``` text
implementation
+ migration if required
+ unit tests
+ integration tests where applicable
+ public contract documentation
```

Do not implement later phases by bypassing unfinished earlier contracts.

------------------------------------------------------------------------

# Architectural Invariants --- Do Not Violate

1.  **Raw LLM concept text is never a durable learner-state key.**
2.  **Canonical concept identity belongs to Mentra.**
3.  **Other modules submit evidence; they do not set mastery.**
4.  **Mastery, estimate confidence, retention confidence, and context
    relevance are different variables.**
5.  **Time alone does not directly lower mastery.**
6.  **Old knowledge becomes dormant; it is not automatically deleted.**
7.  **Dormant knowledge may be reactivated when genuinely relevant.**
8.  **The entire learner model is not dumped into normal LLM prompts.**
9.  **General study recommendations are computed by Mentra before LLM
    wording.**
10. **RAG retrieval respects learning-context lifecycle.**
11. **Low-confidence OCR/extraction cannot silently mutate learner
    state.**
12. **Evidence retains provenance.**
13. **Derived learner state should be reproducible from accepted
    evidence where practical.**
14. **LLM/provider replacement must not remove Mentra's learner
    intelligence.**
15. **External modules depend on Learner Engine contracts, not its
    database internals.**
16. **Scoring policies must be replaceable/versionable.**
17. **One contradictory observation must not automatically erase a
    stable learner belief.**
18. **Deterministic logic is preferred before LLM reasoning when it can
    solve the task reliably.**

------------------------------------------------------------------------

# Definition of Done

The first complete Learner Model implementation is done when:

-   canonical concepts cannot be duplicated merely because an LLM
    changed wording;
-   all learner changes flow through evidence;
-   mastery, estimate confidence, and retention confidence are
    represented separately;
-   old subjects can become dormant without data loss;
-   active learning context controls normal recommendations and learner
    retrieval;
-   relevant dormant knowledge can still be intentionally recovered;
-   LangChain can request a compact learner-context packet;
-   RAG can consume learner context without reading learner tables;
-   assessments can request targets and submit results as evidence;
-   handwritten/OCR workflows cannot corrupt state through uncertain
    extraction;
-   recommendations and verification candidates are generated by Mentra
    logic;
-   the learner engine works independently of a specific LLM provider;
-   deterministic learner logic is covered by tests;
-   state changes can be traced back to evidence;
-   future scoring-policy changes can recompute state from historical
    evidence.

At that point the learner model is not merely storage behind a chatbot.
It is a reusable intelligence subsystem that other Mentra modules can
query and contribute evidence to through controlled contracts.
