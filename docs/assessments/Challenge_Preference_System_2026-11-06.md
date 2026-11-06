# Challenge preference from student choices and observed performance

Status: implementation design with an executable, tested reference policy. **The new mini-system is not wired into live personalization yet.** Existing mastery updates and difficulty buttons continue to work independently. The reference thresholds below are proposed controls, not empirically calibrated claims.

## Product behavior

Keep three distinct facts: what the student requests, how they perform on eligible work, and what mastery evidence supports. A request for harder work is an immediate choice for that request, not proof of ability. Successful independent work on harder variants can support a future challenge preference. Easy work done well can also be a valid preference; it need not mean low ability.

For repeated harder successes plus easier failures, retain the stronger observed harder performance and provisionally offer that challenge band. Flag the non-monotonic pattern for item/format/engagement and grading review. Do not declare that harder questions caused improvement or that easy-item failures prove lower mastery. Question difficulty labels remain heuristic until item and outcome validation supports them.

Students can override the suggestion on every assessment, reset a skill's preference, or disable this personalization. Current explicit choices always win. Show a short explanation such as “You requested harder practice and recently completed independent questions at that level.” Never claim a perfect compatibility score.

## Separate mini-system and durable contract

Implement a `ChallengePreferenceService` with its own policy version and derived state. It consumes typed events and emits bounded challenge suggestions; it never writes mastery directly.

1. **Choice requested:** owner, client operation UUID, conversation, exact owned draft/assessment ID and revision, `easier`/`harder`, canonical skill IDs, language and answer mode, source item family, baseline challenge and explicit requested step. Capture this from a structured UI action, not an LLM's paraphrase of chat. Validate ownership and revision server-side.
2. **Variant served:** successful durable generation ID, new paper/revision and served time, actual generated targets, private source links and unchanged-original assertion. Failed/canceled generation stays a choice observation but cannot count as a successful intervention. Repeated clicks, retries and lost responses coalesce by operation UUID.
3. **Outcome finalized:** attempt and grade revision, normalized per-skill raw correctness, independent item count, reported/observed assistance, first-exposure and family information, grading confidence, item-review state and effective-source revision. Consume from the existing post-result evidence outbox, never before showing results.
4. **Source withdrawn/corrected:** invalidate the effective outcome, retain the raw event, and recompute the affected projection. A stale worker cannot restore invalidated support. Trusted regrading replaces the effective grade revision once.

Use a compact immutable choice/served ledger and a versioned outcome ledger that refer to existing papers/attempts; do not duplicate answer sheets, private keys or chat history. One derived row per owner/context/canonical skill/language/answer-mode records the challenge offset, support counts, window version, anomaly flags and last event cursor. Repeated choices do not create concepts, topics or aliases.

## Testable first policy

The reference in `backend/testing/challenge_preference_reference.py` uses at most the latest 32 distinct item families for one exact scope. It requires three eligible families across at least two sessions, each with at least three independently answered items and grading confidence ≥0.8. This minimum is provisional and must be validated; one session or one repeated item cannot establish a preference.

- Three harder families averaging ≥0.8 support one provisional +0.1 challenge step.
- Three easier families support a −0.1 preference step; if average correctness is below 0.5, also offer a diagnostic/scaffolding rather than repeatedly simplifying indefinitely.
- Poor harder results do not establish higher readiness. Preserve an explicit harder request while offering support.
- Harder success plus easier struggle supports a provisional harder preference with an anomaly flag, not a new global mastery score.
- Explicit choice overrides this request without rewriting learned fit. Targets stay between 0.1 and 0.9; there is no cumulative increase from replaying the same evidence.

Exclude assisted/hinted work, copied or repeated families, low-confidence grading, invalidated questions, incomplete grading, failed generation and insufficient item counts from performance support. Preserve these events as observations. Strong support in Python lists must not silently change calculus, Arabic literacy, or an unseen written format. No semantic scope merge without the existing reviewed identity process.

The reference is a policy simulation, not a streaming database implementation or scientific proof. In particular, production projection reads must use an indexed `LIMIT 32` query; do not load a lifetime Python list as the reference does for fixture evaluation.

## End-to-end integration plan

1. Add typed choice metadata to the chat turn/action contract and server-owned revision request. The difficulty menu supplies source ID/revision, direction and idempotency UUID. Preserve chat-visible new-version delivery. Natural-language requests can be captured only when an exact current user quote and owned source have been verified; never invent an implicit click. Add two-user, stale-version, duplicate-click, stop/retry and failed-generation integration tests.
2. Persist requested/served events transactionally with generation enqueue/publication. Feed a bounded target plan to content generation. Require the same topic, count and delivery unless explicitly changed, preserve originals/attempts, and check substantive challenge changes in a blinded paired item review. Changing a numeric difficulty label alone must fail acceptance.
3. Process finalized outcomes and withdrawal/correction events through the existing durable evidence path. Commit cursor and projection atomically. Replays, out-of-order delivery, report races, owner deletion and worker crashes must produce the same final state as an ordered replay. Use existing assessment outcome/first-exposure provenance; do not fetch lifetime evidence.
4. Join challenge preferences into the existing bounded learner read. Keep the combined preparation gate at ≤8 SQL / ≤2 checkouts / zero commits and its measured p95 target. Do not add a request-time mutation, organizer pass, ledger replay or LLM call. Preserve the compact prompt budget and source-observation reservation. The deterministic target plan is authoritative; prompt prose cannot silently override it.
5. Use scoped challenge readiness to suggest an entry diagnostic or next practice level on a roadmap. Keep verified knowledge, learning priority and challenge preference separately visible. No demonstrated skill coverage means a provisional roadmap; preference is not a substitute for prerequisite evidence.
6. Add an optional background LLM assessor for bounded anomaly explanations: wrong-topic items, boredom, ambiguous wording, language/format effects or apparent non-monotonic performance. Store source-linked suggestions and uncertainty. It cannot approve its own items, mutate mastery, merge identities or override explicit choices. Timeouts leave the deterministic mini-system operational.
7. Provide the student controls and explanation, private operator diagnostics, source-safe export and a per-owner/skill projection rebuild. Keep one coalesced background job per affected scope. Archive superseded projections without deleting unique source evidence. Cleanup of unreferenced observations follows the existing reviewed retention policy.

## Acceptance and Plan B

| Gate | Required proof | Fallback |
|---|---|---|
| Integrity | Zero foreign/stale source binding, fabricated choices, lost answers or double-applied outcomes in replay/crash/race tests | Disable adaptation writes immediately; retain events |
| Choice precedence | Every explicit easier/harder request wins its own target; reset/disable works across reload and devices | Serve the explicit request using existing revisions |
| Quality | Blinded matched item review confirms a real challenge change while preserving scope/count/solvability; no new severe key defects | Reject the variant and use a reviewed item/template; preserve the original |
| Evidence validity | Assisted/repeated/invalidated/low-confidence work cannot establish higher readiness; source correction removes superseded support | Abstain and offer a diagnostic |
| Scale | ≤32 effective families per scope read; no lifetime ledger scan; no canonical-concept growth from clicks; repeat replay yields identical state | Use current learner targets with personalization off |
| Latency | No added foreground LLM calls; existing preparation DB limits and generation/display/grading gates still pass; ≤200 ms added p95 end-to-end in matched rated-load runs | Disable challenge personalization without disabling assessments |
| Fit | Predeclared prospective prediction and calibration holdouts compare existing targeting, choice-only targeting and choice+outcome targeting; report subgroup harm and abstention | Keep the learned preference in shadow mode |
| Experience | Blinded rubric plus student testing verifies useful control/explanations; a powered delayed-learning comparison is required for a learning-gain claim | Keep transparent manual choices; make no gain claim |

Roll out through `off → shadow → explicit opt-in → qualified default`, using a dedicated `LEARNER_CHALLENGE_ADAPTATION_ENABLED` setting when integration is implemented. The current code does not contain that switch or event integration yet. Stop immediately on integrity failure; stop promotion after a threshold breach or >20% regression in two adequately sampled matched windows. Keep the source ledgers and use the existing generation/learner Plan B paths. Do not ship an automatic “perfect compatibility” claim from this reference policy.

The design's unit simulations cover harder success, easier preference, the user's mixed-performance example, fresh override precedence, duplicate families, hints/assistance, low-confidence scores, invalidation/replay, language/skill/owner separation, bounded windows and insufficient support. Database integration, real challenge-change review and student learning effects remain acceptance work for implementation, not completed evidence.
