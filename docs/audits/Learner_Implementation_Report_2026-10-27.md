# Learner, concepts and assessments implementation

The simplified release keeps the existing evidence engine and assessment pipeline. Students browse broader topics and open their subskills; the underlying canonical IDs still identify independently scored skills. Grouping does not combine evidence or transfer mastery.

The implementation was verified against disposable PostgreSQL schemas and deployed to the local Docker stack on October 28. The original audit and governing plan are in [the audit](Learner_Assessments_Concepts_Audit_2026-10-27.md). See the [release record](Learner_Release_Readiness_2026-10-28.md) for final fixes, migration preservation, runtime checks and public deployment requirements.

## Implemented behavior

| Area | Result |
| --- | --- |
| Natural concept breadth | One topic/subskill layer. The configured LLM chooses meaningful topic names, boundaries and child labels. There is no fixed topic catalog or mandatory/minimum/maximum child count. Input batches and assessment selection limits are operational limits, not topic-size limits. |
| Repeat encounters | Exact owned phrase reuse, bounded candidate search and semantic membership advice reuse the existing home. Related skills share a topic without becoming synonyms of each other. Context, scope and supplied IDs are checked. |
| Privacy and compatibility | New human labels and scopes are owner-scoped. Underlying global canonical names for newly organized skills are opaque. Existing IDs, evidence, attempts, grades, keys, citations and legacy links remain intact. |
| Concurrency | Model calls happen outside database transactions. A registry-version check under the commit lock rejects stale advice and retries once against current placements. Publication checks the requested parent again inside the owned save transaction. |
| Failed or cancelled generation | Unpublished assessment mappings stay out of public topic lists. A resolver outage can leave an unclassified skill rather than a guessed parent. A failed historical grouping preview writes no fallback membership. |
| Historical organization | Preview, apply and undo operate in bounded batches, preserving skill IDs and evidence. Receipts make repeated apply/undo safe. Renaming and moving a child use revisions; undo rejects intervening placement changes. |
| Assessment targets | Parent selection chooses a bounded need-aware sample. Explicit child selection fixes the targets and requires enough questions. Planned targets are validated and saved question breadcrumbs record the actual topic/subskill identities. Unchanged revised questions retain their original labels and keys. |
| Component evidence | One deterministic choice question with several concepts no longer creates high-confidence mastery evidence for every listed concept. Raw correctness, marks and existing assistance policy remain unchanged. |
| Retention | Time changes projected recall support, not historical mastery. Retention and challenge prediction share observation-age freshness. Qualified independent successes at least 24 elapsed hours apart extend challenge-specific stability. Failures and weak chat do not rejuvenate old success. |
| Unknown recall | Unknown remains unknown in the learner response. Ranking uses neutral uncertainty for missing recall evidence instead of maximum forgetting risk, with an honest independent-check explanation. |
| Relevance | Context selection controls scope. Relevance contributes once to ranking, alongside need and explicit importance; it is not a mastery estimate. Explicit importance zero excludes a target. Deadline urgency and instructional benefit remain separate future work. |
| Recommendation diversity | Choose the strongest subskill need per topic before taking the shortlist. A topic with many weak children cannot occupy the entire recommendation list. |
| Chat encounters | The explicit concept-resolution tool uses the same owned topic/subskill resolver. Naming a skill may organize it as unassessed; it creates no learning evidence. Existing answer-evidence workers remain the observation producers. |
| Existing misconception feedback | Accepted evidence already projects grade misconception metadata, and corrections remove obsolete accepted observations. This existing path is retained; a missing separate misconception-recording call was not an absence of integration. |
| Broad profile | Mock-exam evidence participates in the existing broad-profile projection. Broad estimates and granular mastery remain separate. |

## Frontend

| Surface | Implemented behavior |
| --- | --- |
| Progress | Paginated topic cards, scope, tracked/checked child counts and grouped search results. Opening a topic loads a separate child page with short ability descriptions; evidence explanations load on demand. Counts are not whole-syllabus mastery claims. |
| Search | Server-side topic, scope, skill and phrase search finds children beyond the currently loaded page. Unknown legacy skills remain searchable under “Not grouped yet.” Stale searches are aborted. |
| Topic corrections | Rename, move, preview/apply grouping and undo preserve evidence. Changes refresh other learning views; dialogs retain their established keyboard/focus behavior. |
| Practice creation | Optional topic/subskill picker, selection across child pages, sample-by-default, count validation and progressively disclosed settings. Target selections survive an owner-scoped tab reload for up to one hour; logout/account changes clear other-owner drafts. |
| Questions and results | Consistent saved topic → subskill labels in interactive, written and feedback views. Coverage describes skills actually checked, excluding untested siblings. |
| Recommendations | One broader topic suggestion with a specific subskill focus and a targeted practice link. |

## Response controls added during implementation

| State | Main composer control | Behavior |
| --- | --- | --- |
| Idle / nonempty draft | Send, arrow, primary color | Starts a new response unless a typed follow-up explicitly continues or makes a small change to retained paused/failed work. |
| Active response or its background generation | Pause, pause icon, warning color | Fences publication, cancels active work across processes, and preserves completed work. Assessment cards also expose controls so older jobs stay stoppable. |
| Paused, empty draft | Resume, play icon, success color | Continues the same response and retained assessment batches. |
| Failed, empty draft | Retry, retry icon, danger color | Resumes the failed graph node, retaining completed graph steps and domain receipts. |
| Typing after pause/failure | Send | Editing the draft changes no server state. Clearing the text restores Resume/Retry. |

PostgreSQL LangGraph checkpoints preserve general response and tool-coordinator state. Completed writes retain domain idempotency receipts; completed write tasks have durable graph results. An interrupted provider call restarts at its node rather than continuing an HTTP/token stream. Background assessment jobs retain validated batch checkpoints and can stop during selection, label resolution, content batches and retries.

Unfinished paused/failed response checkpoints expire after 30 minutes; stopped assessment question/plan checkpoints expire after 30 minutes. Worker sweeps and owned reads perform expiry. Successful completion and chat deletion remove response checkpoints. Original chat messages, saved assessments, attempts, grading/evidence history and source-practice provenance are preserved. The visible paused fragment is a chat record, not a mastery observation. Typed continuation is owner/current-response scoped; semantic classification uses a small bounded model call only for ambiguous typed follow-ups. Transport retries replay continuation receipts instead of adding another user message, even after a newer turn exists. Changed memory context invalidates retained graph context and requires a fresh retry. New/corrected student answers, personal facts and confusion reports remain new canonical user messages rather than being hidden inside response amendments.

## Verification

Verification records use synthetic users/materials in disposable schemas; no production student dataset was inspected or modified.

| Check | Evidence |
| --- | --- |
| Topic organization with the configured provider | [Provider record](topic-organization-live-verification.json): coherent six-skill grouping, paraphrased niche reuse and separation of an unrelated subject. |
| Continuation routing with the configured provider | [Provider record](response-continuation-live-verification.json): continuation, small change and new request, including multilingual inputs and new learner statements. |
| Migration and large-history storage | [Storage record](topic-storage-verification.json): upgrade/downgrade/reupgrade preserves synthetic learner rows; 10,000 children, a 10-row detail page, bounded five-child resolver candidates and a 412-byte grouped list payload in the fixture. Timings are local fixture observations, not production p95 measurements. |
| Main combined backend suite | 198 tests passed in 369.290 seconds, including learner contracts/persistence/realistic histories, assessments, progress, grading/evidence and response/generation stop. |
| Response/tool/summary suite | 128 tests passed in 64.703 seconds. |
| Display-label follow-up | 81 tests passed in 166.002 seconds after the real browser flow caught an internal-name leak; includes readable generated questions, practice targets and both mistake-history paths. |
| Final response lifecycle follow-up | 36 tests passed in 10.802 seconds, including current-response continuation receipts, replay after a newer message, cross-process pause, ownership and invalidated memory context. |
| Final topic-detail follow-up | 13 tests passed in 22.850 seconds, including ability descriptions, concurrent grouping, safe failed previews, unknown skills and topic diversity. |
| Application Python 3.12 runtime | 32 focused tests passed in 84.769 seconds; six additional display/continuation checks passed in 6.999 seconds after the label fix, using a read-only source mount. |
| Browser flows | Nine checks passed in 1.2 minutes, including real authenticated assessment creation/revision/partial answers/grading. The final seven desktop/mobile topic/control checks also passed in 36.0 seconds after adding subskill descriptions and draft ownership guards. |
| Frontend and static checks | Production TypeScript/Vite build passed; theme and UI checks passed; targeted Ruff checks and `git diff --check` passed. Vite still reports the existing large-chunk advisory. |
| October 28 release review | 68 focused backend regressions passed in 66.154 seconds, nine browser checks in 1.3 minutes and four final composer checks in 22.5 seconds. These overlap earlier suites. The dependency audit found zero production frontend vulnerabilities. |
| Built-image production check | [Runtime record](learner-release-runtime-verification.json): isolated synthetic database, live configured-model assessment generation, pause/resume/stale-stop fencing, private keys, published topics, secure cookies and foreign-origin rejection. HTTP size/range and delivery-cancellation checks also passed inside the built backend image. |
| Local deployment preservation | [Migration record](learner-release-migration-verification.json): `0031` to `0034`, all 84 existing application-table row counts unchanged, two additive topic tables. Backend/frontend are healthy and all five workers are running. |

## Rollout and rollback

1. Take the normal database backup and use the established migration/deployment process. Migrations `0032`–`0034` add owned topic membership and response/generation continuation fields. No destructive historical regrouping runs at startup.
2. Update workers, backend and frontend together so every running component understands stopped jobs, continuation fields and topic targets. The local stack now uses rebuilt application images; public releases must build the frontend with the actual HTTPS API origin and use versioned images as described in the release record.
3. Existing skills initially remain available as ungrouped. Preview/apply organization in small batches per owned learning area; inspect scopes and sample practice targets before wider use. Rename/move/undo are placement corrections, not semantic merges or score changes.
4. For application rollback, retain the additive schema and immutable receipts. Destructive downgrades intentionally refuse populated topic memberships or stopped/resumed-work receipts. Do not delete learner evidence, assessments or checkpoints merely to force an old schema downgrade.

## Remaining limits and deliberate deferrals

| Item | Current boundary |
| --- | --- |
| Automatic private learner context for ordinary chat | Not enabled. Automatic approval review rejected the optional prefetch because it would send additional private learner context to the configured model without explicit approval. Existing on-demand retrieval remains. |
| Teaching effectiveness | The check groups overlap; their counts must not be summed as unique tests. Synthetic correctness and workflow tests do not establish student learning gains. Delayed independent unseen-item performance, transfer and learning gain per study minute still need a representative evaluation. |
| Semantic placement recall | Candidate retrieval is bounded and model judgments can still be wrong. Wider lookup and unclassified fallback prevent guessing from becoming a required taxonomy decision; representative multilingual/large-catalog recall still needs evaluation. Manual placement corrections remain available. |
| Retention calibration | The half-life/stability rule is an explainable heuristic. It is not a measured probability of remembering or an individually fitted forgetting model. |
| Curriculum and coverage | Only encountered/linked skills are known. There is no claim of complete syllabus coverage or a guaranteed optimal next lesson. |
| Ranking scale | Topic/child lists, resolver packets and recommendation outputs are bounded. The existing ranking engine still evaluates eligible context-linked states before topic shortlisting; the 10,000-item storage check is not an end-to-end ranking latency benchmark. |
| Chat evidence breadth | The existing answer worker still has question/exposure/assistance limitations described in the audit. Free text confusion, preferences and “I understand” are not automatically graded as knowledge. A general signal platform is deliberately deferred. |
| Item quality | Generator difficulty and grader confidence remain heuristic. Reviewed item/rubric anchors, guessing analysis and held-out calibration remain evaluation work. |
| Broader product systems | Curriculum editors, automatic prerequisite discovery, learned schedulers, generalized tutoring episodes and teaching-method experiments remain deferred under the simplified first-release scope. |
