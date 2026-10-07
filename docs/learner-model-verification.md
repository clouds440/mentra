# Learner model behavioral audit

This audit separates correct execution from learner accuracy. The original 64-test
baseline verified many contracts, but did not establish accurate current-skill estimation.
The user selected synthetic trajectories because no real assessment history is
available for evaluation yet. Production accuracy remains unmeasured.

The [current full-stack verification report](student-profile-verification.md) records
the expanded PostgreSQL, identity, high-level profile, browser, and Docker checks. The
independent synthetic report below has been rerun against PostgreSQL; its results do
not validate the separate Student Profile assessment psychometrically.

## Reproduced defects before hardening

- A lifetime weighted average retains mastery **0.827** after 100 independent
  successes followed by 20 independent failures. Old performance dominates current skill.
- 200 easy, fully assisted chat successes produce mastery **0.879** and estimate
  confidence **0.65**. Assistance affects weight but not what capability was demonstrated.
- Difficulty changes weight, so enough easy successes eventually imply almost perfect
  general mastery. Attempted difficulty is treated as coverage even after failure.
- A failure resets retention to a high value and refreshes its timestamp. A later
  easy answer can clear verification after a failure on a harder task.
- Question totals are copied onto every tagged concept without concept-specific
  grading. This can invent knowledge or weakness on unrelated rubric dimensions.
- Item identity/diversity and spaced recall are absent; one repeated question can
  look like broad, stable knowledge under new source IDs.
- Query matches are limited alphabetically before ranking. Generic cross-domain
  links can introduce unowned or unrelated concepts; prerequisites are counted globally.
- Old policy projections are returned on reads until another observation arrives.
- Pending-transcription confirmation is not retry-safe, and grade revisions can be
  counted twice unless the caller manually supplies prior evidence IDs.
- Aliases ignore persisted confidence; discarded candidates can be reopened by
  repeated wording; normal English plurals such as `classes` normalize incorrectly.
- Context state transitions preserve the old relevance value rather than reflecting
  the new status, and backfilled historical assessments refresh present activity.
- Sorted JSON keys change eviction order for a recency dictionary, causing persistent
  live updates to diverge from pure replay after more than 64 distinct questions.
- Calibration returns fewer than the requested 3-5 probes for a small subject;
  unknown assistance is incorrectly reported as hint dependence; a weak misconception
  observation can inherit certainty from an old resolved claim.
- A shared recent window lets easy review reduce advanced mastery. Challenge evidence
  needs separate windows; easy activity also must not refresh old hard predictions.
- Legacy OCR rows are marked accepted during upgrade without applying extraction gates.

## Verification approach

Use deterministic independent learner trajectories, assisted/easy repetition,
ability changes in both directions, delayed recall, item reuse, grading revisions,
mixed concept-level scores, context goals/importance, identity ambiguity, ontology
changes, concurrent writes, and process restart. Evaluate predictions **before**
ingesting each outcome to prevent future-outcome leakage. Track error, Brier loss,
calibration, coverage, and subgroup results separately; synthetic behavior is not a
claim of measured real-world accuracy.

## Implemented hardening and verification results

`mastery-v2` uses separate bounded easy/medium/hard evidence windows. Independent
first attempts at known challenge levels establish skill; assisted, retry and unknown
observations remain practice. Repeated items are discounted, explicit item diversity
controls confidence, and chat-only history cannot establish demonstrated status.
Target performance exposes support and approximate uncertainty. Easy review preserves
demonstrated hard ability; new hard failures revise it. These scores and bounds are
heuristics, not empirically calibrated probabilities or credible intervals.

Retention depends on difficulty-matched successful demonstrations and distinct recall
days. Failures do not renew it. Two new independent successes at the disputed difficulty
are required to clear verification. Each challenge band's freshness is tracked separately.
All recency ordering is explicit and survives sorted JSON serialization and process restart.

Question/session/attempt identity blocks duplicate graders and stale revisions.
Assessment revisions atomically replace prior effective grades while retaining immutable
history. Multi-concept questions require separate marks, with component difficulty overrides.
Pending confirmation is retry-safe and cannot overwrite a newer accepted grade. Additive
schema version 3 retains evidence and applies extraction/grade gates to uncertain legacy rows.

Context-specific goals supply importance and target difficulty. Neutral defaults remain
explicit assumptions; zero importance excludes default recommendations. Query relevance
precedes limits, owned trusted graph links can expand scope, and foreign curriculum links
cannot inflate prerequisite importance. Strong current misconception claims enter packets;
uncertain claims remain available internally. Reads refresh stale policy/configuration
projections, and context selection reuses batched ownership/activity reads.

The original hardening audit passed **95 backend tests, including 72 learner tests**.
The current expanded suite and Docker checks are recorded in the linked full-stack
verification report. Compilation succeeded in the original audit.
Tests exercise transactional rollback, concurrent writers/retries, migrations, grading/OCR
boundaries, skill changes, item reuse, small-subject calibration, goals, context switching,
restart/replay equality, bound LangChain tools, mocked chat-provider composition, application
startup with mocked embedding/vector constructors, and real local Qdrant filtering.

The [saved synthetic report](learner-synthetic-evaluation.json) uses seed 47291 and eight
independently generated latent-ability trajectories: strong, novice, learning, regression,
mixed, guided, easy-only and repeated-item. The evaluator predicts before each label updates
its isolated states; the persistent workflow uses a separate temporary PostgreSQL schema.

| Measurement | Synthetic result |
| --- | --- |
| Total observations | 1,200 |
| Eligible independent outcomes evaluated | 1,050 |
| Guided observations excluded from independent prediction metrics | 150 |
| Predictions supported by challenge/item evidence | 852 (81.1%) |
| Brier score (all eligible outcomes, lower is better) | 0.134 |
| Neutral 0.5 baseline Brier score | 0.250 |
| Mean absolute prediction error | 0.275 |
| Binned calibration error | 0.023 |
| Supported-subset mean absolute error | 0.223 |
| Persistent restart/replay equality | All eight trajectories |

The saved report includes current PostgreSQL ingestion and retrieval timings.
These local measurements on a small fixture are indicative, not production benchmarks.
Ordinary ingestion maintains bounded sufficient statistics without scanning evidence
history; corrections, old arrivals and policy changes replay only the affected concept.

Reproduce from the repository root:

```powershell
$env:PYTHONPATH = 'backend'
# Set TEST_DATABASE_URL to a dedicated PostgreSQL test database first.
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
.\.venv\Scripts\python.exe backend/scripts/verify_learner.py --output docs/learner-synthetic-evaluation.json
```

## Remaining accuracy limits

Synthetic coverage is not real learner accuracy. Actual concept mapping, rubric grading,
difficulty estimates, independence provenance and assessment representativeness determine
what the engine can infer. This implementation cannot discover unobserved skills or personal
importance with near-100% accuracy. Real anonymized question histories, chronological
holdouts, subgroup evaluation and empirical calibration are needed before making an accuracy
claim or tuning policies for real students. No live model, live OCR/grader, deployed graph,
or granular learner integration into the authenticated product was evaluated in this
original audit. PostgreSQL persistence, authentication, and the separate high-level
profile now have full-stack checks in the linked verification report.
The other consumers have working typed boundaries and remain in their own implementation plans.

## Research context

Model choice and calibration must be evaluated on the intended data; a complex model
is not automatically more accurate. See [Gervet et al., JEDM 2020](https://jedm.educationaldatamining.org/index.php/JEDM/article/view/451).
Multi-concept answers need concept-specific observations rather than one undifferentiated
correct/incorrect label. See [EDM 2024 multi-knowledge-component evaluation](https://www.educationaldatamining.org/edm2024/proceedings/2024.EDM-short-papers.25/).
