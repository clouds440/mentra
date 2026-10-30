# Follow-up review: prompt and tool optimization

27 October 2026. Review of the uncommitted implementation, followed by fixes and regression checks. No additional paid model calls were made.

## Findings fixed

| Priority | Gap | Fix and verification |
|---|---|---|
| High | The assessment title shortcut could finish a quiz request while an additional required web/domain lookup was still missing | Shortcut now requires no additional required domains; regression preserves the card while refusing unverified external completion |
| High | Any operation in a domain counted toward completion; reading an agenda could satisfy a reminder, and recalling memory could satisfy a requested memory write | Relevant planned operation required; memory writes also require a mutation action. Invalid-argument receipts do not satisfy completion |
| High | An unrelated profile/preparation warning disabled the native assessment completion guard | Warning no longer authorizes a prose substitute; only a real card or a truthful deferred/failure result completes the turn |
| High | Failed generation could still be followed by a prose-only quiz | A failed/uncertain generation without a card yields a truthful failure response and does not retry the write |
| Medium | Completion repair always offered the compact generator, even when explicit marks required advanced generation | Repair retains the requested generator and avoids binding both schemas; regression verifies marks reach the domain service |
| Medium | Completion guard could force calls with missing arguments after the model created a genuine clarification control | New durable clarification cards defer lookups with a canonical pending message; unverified success prose is discarded |
| Medium | Short-path eligibility did not reject marks/timing instructions if they were only in the instruction text | Those instructions retain the full design path, preserving requested structure over the one-call optimization |
| Medium | Early hydrated assessment Refresh reused the original payload after an error | Refresh now reads the authoritative owned endpoint; browser test verifies the extra read and retained answer |
| Medium | Saved early cards lost their conversation ID, hiding conversation actions | Preview carries its validated conversation context; browser test verifies actions remain present and disabled while the turn runs |
| Low | Personal references to test results could trigger semantic event extraction | Non-temporal event capture now requires announcement evidence; explanations and unit-test failures do not qualify |
| Low | New evaluator had an unused import and could silently zip mismatched cohorts | Removed import, assert matching complete cohorts, and add optional `--check` gate for complete scripted task cost regressions |

Early cards are keyed by reference identity to avoid showing a previous card during reference changes. The browser regression also confirms answers survive the early-card-to-canonical-message transition. Profile immediate saves, blocked-BroadcastChannel fallback, coalesced refresh and concurrent-edit conflict protection still pass.

## Verification and costs

| Check | Current result |
|---|---|
| Expanded backend suite | 184 run: 135 passed, 49 skipped |
| Full mocked browser regression suite | 40 passed |
| Final focused smart-tools browser suite | 9 passed, including one additional saved-card case; 41 distinct browser cases across runs |
| Frontend production build, theme and UI checks | Passed |
| Application/new evaluator/new regression unused-code checks | Passed (`F401,F811,F841`) |
| Whitespace check | Passed |
| Offline complete-task cost gate | Passed: 42 snapshots and five scripted workflows |
| Additional paid model calls | Zero; earlier implementation probes remain four total |

The five scripted workflow improvements remain unchanged: estimated input reductions of 32.1% for history, 33.0% for preferences, 50.9% for agenda, 14.7% for Library, and 8.4% for web. The first three retain the reduction from three model rounds to two. These are controlled synthetic costs, not production timings. See [raw evidence](verification/General_Tool_Optimization_Evidence_2026-10-26.json).

A broader attempted run produced 26 errors because no dedicated `TEST_DATABASE_URL` was configured; database fixtures correctly refused to use the application database. These are unverified integration checks, not passes. The selected offline suite above completed successfully. A repository-wide unused-code scan also found three pre-existing issues in untouched test/helpers (`testing/rag_real.py`, `tests/test_memory_summaries.py`, `tests/test_saved_chat_search.py`), verified against HEAD; these remain outside the optimization change.

## Further improvement priorities

| Order | Improvement | Why it remains useful |
|---|---|---|
| 1 | Run isolated PostgreSQL integration checks and coordinated deployed-image smoke checks | Mocked services cannot establish real persistence, queue, transaction or deployed frontend/backend compatibility |
| 2 | Measure actual time to usable UI with preparation, provider, queue, persistence and rendering timings separated | Token savings and single-call timings do not establish end-to-end latency or tail behavior |
| 3 | Expand offline routing cohorts across languages, unfamiliar paraphrases, negations, ambiguous references and multiple actions in one domain | Current hints are inexpensive heuristics with model discovery fallback; they do not provide exhaustive semantic intent understanding |
| 4 | Represent compound completion as individual requested operations and their receipts rather than only domain-level obligations | Current guards distinguish selected operations and important read/write cases, but do not prove every subtask of an arbitrary compound request |
| 5 | Extend contextual actions to more supported outcomes using small validated domain action sets | Source practice and visible starters are a foundation, not exhaustive discovery coverage for every feature |

Keep future routing improvements model-free unless evaluation demonstrates that another call pays for itself in total successful-task cost. Keep provider probes bounded and synthetic. Do not add broad profile/history/learner reads or all schemas back into routine requests to improve candidate recall. No deployment was performed in this review.
