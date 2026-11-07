# Mentra difficulty and assessment release — 2026-11-07

The typed difficulty route, durable preference/outcome worker, learner-context integration, student controls, assessment admission/repair checks and integrated frontend are implemented. Collection is enabled; learned offsets require explicit per-skill opt-in. The system does not promote a choice to mastery or claim a perfect student model.

## Measured results

| Measure | Observed result | Scope |
|---|---|---|
| Historical failed six-part revision | About 70 seconds end to end, zero parts published | Retained production trace; chat20.5s, queue about14s, generation41.7s |
| Final harder exact-template replay | 37.232 seconds; six parts; original unchanged | Same question template, disposable DB/current provider; includes factual repairs and two-stage checking |
| Easier replay | 14.487 seconds; six parts; original unchanged | Small smoke sample, not a production percentile |
| Ready-to-use frontend p95 | Desktop30.1ms; mobile4×CPU41.5ms | 30 samples each, compiled bundle |
| Local interaction p95 | Desktop34.4ms; mobile32.7ms | 124 interactions per device; zero navigation writes |
| Blocking hydration reads | Zero | Direct generation-result handoff |
| Active learner preparation | Seven queries, one checkout, zero commits | Existing query budget retained; profile-combined path eight queries |
| Added preference preparation p95 | 2.824ms | Thirty off/on reads over40,000 synthetic family rows; indexed32-row window |

The before/after timings are different environments and sample sizes; they do not establish a matched percentage improvement. The extra quality work is deliberate: earlier fast samples contained factual errors. The configured provider can still produce unsuitable questions; checks reject them and preserve the original instead of silently publishing a defective fallback.

## Quality and learner usefulness

The known-defect control rejected all three deliberately incorrect choice items and retained the valid control. Blind public-only solving was added for mixed difficulty revisions after review exposed false written premises and confused keys. Deterministic checks now enforce option limits, matching selectable lists, exact canonical concept attribution, and Unicode letters/joins/diacritics. Rejected positions are repaired; correct content is retained and checked again. This is model cross-checking and executable admission, not independent human adjudication.

Choice grading remains deterministic and does not call an LLM. The mini-system consumes finalized eligible evidence in its own durable worker after results are served. Existing question/grading quality and withdrawal tests passed; there is no new matched live written-grading latency claim.

Learner fit uses32 distinct root families within90days; direction support requires3 families,6 eligible items and2 sessions. Assisted, repeated, known-exposure, low-confidence, invalidated and unqualified-language work abstains. Reports, corrections, reset and deletion withdraw effective support; duplicate replay cannot restore it. Difficulty clicks cannot create concepts or aliases. Roadmap context receives provisional challenge preference separately from knowledge, retention and priorities. Calibration and learning benefit still require prospective student evaluation; default per-skill use stays off.

## Acceptance and fallback

Engineering acceptance covers ownership/revision fences, idempotency, crash/lease recovery, scoped controls, original preservation, no private keys in public handoff, bounded indexed reads, immediate frontend handoff and the existing grading response budget. The companion implementation document lists the full edge-case matrix and operational switches.

Disable LEARNER_CHALLENGE_ADAPTATION_ENABLED to remove learned offsets without disabling manual revisions or assessments; disable capture separately if needed. Retain additive migration0050 on rollback. Source/history downgrade guards intentionally refuse destructive rollback of populated ledgers. Rejected generation preserves the original and offers a bounded retry; it never pretends an unfinished variant is done.

Testing uses all129 backend modules with corrective reruns and additional regressions, plus the complete browser-case inventory across development journeys, compiled UI and isolated performance tests. The local-only TLS launch test requires its separate deployment and is outside this localhost release. Detailed final verification counts and deployed revision are recorded at release completion.

## Completed local release verification

All 1,303 backend tests across 129 modules and all 528 applicable browser cases passed through the complete runs and documented corrective reruns. Candidate deployment replaced all seven application containers; frontend/backend are healthy and API readiness reports database, workers, AI, embeddings and Qdrant ready. Schema is 20261106_0050; effective chat output reserve is 4000. Difficulty capture/adaptation flags are enabled, with automatic offsets still subject to per-skill student opt-in. Public TLS launch verification remains outside this localhost deployment.
