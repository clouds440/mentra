# Semantic orchestration: verification and optimization

Date: October 28, 2026. Includes the explicitly approved automatic-memory work.

## Evidence

| Check actually executed | Result |
| --- | --- |
| Configured `deepseek-flash` semantic corpus: 40 scenarios plus repeated critical cases; real model, simulated domain effects | 64/64 episodes passed. No student data used. |
| Semantic outcomes, protocol, grouped questions, latency/concurrency and recovery | 81 tests passed. |
| Semantic outcomes, persisted chat and pause/resume | 56 tests passed. |
| Context preparation, RAG admission, images and assessment intent | 48 tests passed. |
| Shared ranking-read regression and grading/evidence latency checks | 16 tests passed. |
| Final public outcome, partial-result and pause/resume regressions | 28 tests passed. |
| Browser assessment discussion/revision, typed and uploaded answers, desktop/mobile grouped questions, legacy batch questions and composer job retry | 6 tests passed. |
| Real configured-model generation and grading through actual domain services in a disposable schema | One written question generated and graded successfully; generation 15.259s, complete check 17.433s. This is one sample, not an SLO. |
| Real configured-model automatic memory capture in a disposable schema | One supported preference saved from its canonical opted-in source; job completed; second run did not duplicate it. |
| Frontend production build and backend fatal static checks | Passed. Existing optional diagram chunk-size warnings remain. |
| Built backend dependency consistency | `pip check` passed. |
| Candidate container migration on a fresh disposable database | Passed through `20261028_0036`. |
| Recovery rehearsal | Full backup preserved privately. Application schema restored in isolated PostgreSQL 17 and upgraded; checked conversation/message/turn, assessment/attempt, evidence/state and memory row counts unchanged. Supabase-managed extensions require the managed environment; only the application schema was restored locally. |
| Coordinated local backend/frontend/worker update | Readiness passed for database, model configuration, embeddings and Qdrant; all Compose services started. Actual database reached `20261028_0036`; checked application row counts unchanged. |

Test groups overlap; their counts must not be added as a unique-test total. An earlier repository-wide Windows discovery run was stopped before completion and is **not** a passing full-suite result. Earlier diagnostic failures were used to find and correct gaps; only the listed completed successful checks are acceptance evidence.

## Optimization results

| Path | Observed model work in the final synthetic corpus | Interpretation |
| --- | --- | --- |
| English correction containing “current” | One invocation; no tools; 6,673 input tokens; 1.627s in one sample | Words no longer force web retrieval. |
| Visible artifact rewrite | One invocation; no history retrieval | Full available original retained; no separate router/reviewer. |
| Agenda | Two invocations; one actual agenda operation; 13,480 total input tokens | Earlier diagnostic candidate needed three invocations. |
| Recommendations | Two invocations, with selected independent learner reads together; 13,575 total input tokens | Earlier diagnostic candidate needed three invocations. |
| Grouped onboarding | One questionnaire holding all five questions; usually two invocations | Empty typed native handoff supports one invocation, but provider uptake is not guaranteed. |
| Background-only Resume | No new response-model invocation | Resume the existing owned job and reuse delivered content/receipts. |
| Uploaded assessment answers | Automatic preparation no longer exhausts the interactive call allowance | Server preparation has a separate bounded read allowance; model action/write limits unchanged. |
| Assessment selection | Recommendations and verification share one ranking read; profile overlaps other reads | Snapshot is local to selection, never reused across concept mutations. |

The 64-episode mixed synthetic median was 2.976s. Domain tools were simulated and local verification/builds overlapped: this is not production end-to-end latency, a controlled before/after comparison, or p95 evidence. Real question generation still has meaningful domain-model latency, as the written-question check shows.

Ordinary input allowance is 12,288 tokens and recovery 13,824, constrained by the configured context/output reserves. They are ceilings, not padded targets. Keep useful originals, bounded learner context, source evidence and artifact IDs even when they increase input: fewer repair/discovery/retrieval rounds matter more than a small first-call prompt saving.

## Deployment boundaries

The release was verified locally. Public DNS/TLS/proxy configuration and production traffic latency were not tested. No production p95 guarantee is made. Continue collecting preparation/provider/tool/publication/first-useful-content and background-completion timings separately. Preserve backups and private recovery state; do not revert to old keyword code after new semantic writes or delete outcome columns to roll back.
