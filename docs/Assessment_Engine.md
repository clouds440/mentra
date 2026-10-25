# Flexible assessments and mock papers

Assessments reuse the existing draft, publication, attempt, grading and learner-evidence lifecycle. Revisions create a new draft; original questions, answers and grading history remain intact.

## Request-led structure

Chat and the queue API accept an entirely unspecified assessment request. The creation page asks only for a topic, optional materials, inclusion instructions, independently selectable question formats and a question count. A background selection step reads the existing owner-bound learner tools for active contexts, study priorities, verification candidates and relevant learning context. When no active context exists, it considers the learner's other non-archived contexts. Selected Library metadata is read through the RAG facade in one owner-checked batch. Profile details supply the education level and learning goals already collected during onboarding/settings.

The existing selection model chooses a coherent topic, delivery format, academic level and result presentation from this packet; no separate frontend configuration model call is introduced. With no useful data it can choose a general reasoning baseline without inventing weaknesses. It never asks for missing configuration merely to complete the request. Explicit topics, formats, level and result preferences are retained. Fully specified topic/format/result requests can bypass selection. Resolved choices are checkpointed before content generation so retry does not change the topic. They stay private; the public job exposes the chosen topic as its title.

An outline model chooses the appropriate length and question mix. Explicit counts, formats, marks, timing, instructions and section plans take precedence. The legacy direct API retains its five-question written default for existing callers; chat can infer a count, while the UI offers an editable five-question default (three for linked quick practice). The creation form queues every request for consistent progress and recovery.

Academic level is not a required creation field. Account education level is the default; current evidence calibrates difficulty conservatively. Any explicit higher/lower level or difficulty request takes precedence and is never capped by the account level or an ability estimate. The optional internal `level` field records the assessment-specific selected or requested level and never writes back to profile settings.

`result_style=grade` means simple grading: correctness and feedback without per-question marks, totals or letter-grade scales. Internal equal weights support grading/evidence when no marks were requested. `marks` retains visible marks and totals; `feedback` is also supported for API callers. These choices persist in assessment preferences and survive revision, chat publication and reopening. UI question views, answer review, feedback and print respect the mode; the chat status tool omits numeric score summaries for unmarked reviews.

Question types are open strings. Single-choice, true/false and multiple-selection questions use option controls. Short answers, numerical responses, essays, proofs, cases, matching and other types use a written response when no specialized widget exists. Prompts, options, answers and rubrics have no fixed character limit; operational model budgets still apply. Requests are capped at 20 questions, including requests for 100. Papers count main questions separately from their parts; ordinary interactive practice exposes at most 20 answerable items. Oversized explicit section plans are shortened consistently instead of rejected.

Mock papers carry exam instructions, timing, sections, globally numbered main questions, shared context, nested part paths and positive marks. Each answerable leaf has its own immutable question ID and grading key. A reference such as `3(a)(ii)` maps to that ID, independent of the item's position in the stored array. Section totals and explicit overall totals are checked. Print produces a separate blank question paper without chat, student answers or private grading keys.

When an AI outline's arithmetic misses a requested total, the server apportions its relative part weights to that total before writing questions or rubrics, preserving every part. Explicit caller-supplied section marks must already agree with the total and are not silently changed.

## Flexible canonical concepts

Assessment generation calls the learner's permissive resolver. It reuses clear exact identities, prefers an unambiguous match in the learner's context, and registers a separate canonical concept for a new or ambiguous label. Ambiguous identities receive a stable context-qualified suffix. Duplicate concepts are acceptable; uncertain semantic merging must not block a valid assessment or rewrite existing learner history.

Generated concept names, human labels accidentally supplied as IDs, and missing attribution are resolved through the learner facade. An unknown UUID is never accepted as identity; explicit names or the assessment topic provide the fallback. Labels are processed in small packets without limiting the number of concepts in the assessment. Generation adds context membership but creates no mastery evidence. Other learner workflows retain their existing strict resolution behavior.

## Durable generation and grading

Mock papers, unspecified lengths and long requests are queued independently of the chat-turn deadline. The owner-scoped job stores its outline and completed question batches privately. Polling exposes counts and state, not partially generated solutions. Retry resumes completed batches. Lease tokens fence stale workers; operation fingerprints prevent a changed retry from reusing an old result. Grounded work must retrieve eligible Library sources and use valid source tokens.

Grading also checkpoints completed batches privately against the question snapshot, submitted answers and grading revision. Retry can resume those batches. The complete grades and a durable learning-update job publish in one transaction, making results available immediately. A separate queue consumer applies learner evidence and profile updates in the background. Learning failures never hide results or re-run grading. Evidence writes and their receipt commit atomically; grade-revision and lease fences prevent stale corrections, duplicates and writes after deletion. Previous accepted receipts remain available for supersession or withdrawal after corrections. Multiple-selection scoring subtracts the fraction of distractors selected from the fraction of correct options selected, with a floor of zero. Selecting every option earns no credit when distractors exist.

Model evaluations are aligned to server-owned question IDs, canonical concepts and mark maxima. Unknown concept keys never become evidence identities. Missing single-concept attribution uses the question's overall evaluation; missing multi-concept attribution remains low confidence. Consistent alternative mark scales are normalized; ambiguous out-of-range overall scores still require repair. This avoids rejecting a correct evaluation because the model echoed a different concept key or maximum.

An evaluation failure offers **Retry evaluation**, which requeues the same attempt with the original answers. **Start new attempt** is a separate action after a completed evaluation. Empty abandoned retry drafts do not hide a saved failed submission. Answers use a distinct bordered, tinted box with a **Your answer** chip. Results default to numbered navigation with green correct, red incorrect and amber partial cards, plus previous/next controls; **List view** shows every result.

Typed paper drafts can be saved and reopened. Handwritten uploads map printed numbers and nested part references to immutable IDs; transcription requires review before submission. Vision packets contain public questions only. Provider-dependent handwriting accuracy is not guaranteed by deterministic tests.

## Runtime bounds

The question limit is 20; there is no question-text character cap. Generation allows 900 seconds, up to 256 model rounds, and bounded token envelopes per run. Normal quizzes use one content-generation request when the estimated output fits the configured budget. Larger work uses batches of six with two concurrent calls; long revisions retain smaller batches. A malformed large response falls back to bounded batches instead of regenerating the whole oversized response repeatedly. Ordered checkpointing and cross-batch duplicate checks remain enforced. Grading uses one request when the complete written-answer packet fits, otherwise at most two concurrent batches, balanced using packet size and verified input/output budgets. Objective questions are scored locally without model calls. Each completed grading batch checkpoints independently. Model/schema repair is bounded to one additional call per affected batch, without nested SDK retries. Complete answers, prompts, contexts and rubrics are retained; a submission that cannot fit two packets returns an actionable capacity error instead of truncating work or making many calls. Grading has a 120-second deadline and a 180-second claim; a timeout stops automatic retry loops and offers same-attempt recovery. Uploads retain the 25 MiB limit, with up to 40 vision pages per document.

The assessment worker needs the same embedding, vector-store, Library storage and profile dependencies as the API. Migration `20261014_0023` adds paper metadata, private grading checkpoints and generation jobs. Migration `20261014_0024` adds preferences with backward-compatible defaults. Migration `20261015_0025` adds the durable assessment learning-update outbox. Its consumer runs independently alongside grading, generation and chat-evidence consumers in the assessment worker process. Rebuild and recreate the API, assessment worker and frontend together. Selection has its own 120-second bounded budget before content generation; model admission covers both phases. Retry observes the same owner concurrency limit as new requests.

Question and result navigation use a 180ms, 7px directional fade for buttons and numbered jumps. First render and list view remain still, reduced-motion disables the transition, and answers remain in the parent state. Polling continues through grading and quietly refreshes background learning status after results appear, without increasing the global evaluation counter or blocking navigation.

The grading output ceiling defaults to 8192 tokens. Each packet reserves only its estimated result size plus headroom, retaining input capacity for long answers. This supports full mock papers with multiple parts in two packets without applying the full output ceiling to every small request. Explicit configured ceilings remain authoritative.

## Verification

Focused backend integration tests cover mixed response modes, nested paper references, full-paper generation and grading, permissive concept ambiguity, unknown generated IDs, migration preservation, stale lease fencing, and generation/grading checkpoint recovery. Browser fixtures cover compact desktop/mobile interaction, one final quiz submission, paper printing, saved written drafts and generation progress recovery. These fixtures verify UI behavior; isolated PostgreSQL tests verify persistence and evidence behavior.

Verified locally on 2026-10-14: all 90 focused assessment regression checks passed. Another 21 targeted intent/engine checks covered final source-context fallback and checkpoint preferences; seven fast contract checks covered shorthand expansion, immutable request fingerprints and equal weights for simple grading. Six production-browser assessment checks and nine existing quiz-recovery checks passed, as did TypeScript/Vite, theme/UI checks, container builds and production asset serving. The production browser checks include entirely blank creation and correctness/feedback without visible marks or letter grades.

A synthetic live-provider check produced six main questions, 13 parts and exactly 30 marks across essay, MCQ, numerical, short-answer and true/false formats. A content batch generated from that outline passed validation after the automatic repair path corrected its batch count. This verifies model/schema compatibility, not a full live learner assessment or handwriting accuracy.

Screenshots: [mixed practice on mobile](assessment-engine/mixed-practice-mobile.png), [paper preview on mobile](assessment-engine/mock-paper-mobile.png).


## Simplified creation — 18 October 2026

Material card actions reuse small bordered secondary buttons and separate icons.
The creation page removes the context, purpose, concept-name, result-style, timing,
marks and grounding controls. Materials imply grounding; empty selection means a
request without Library grounding. Linked exact concepts and verification purpose
remain server-validated even though they are no longer separate form controls.
Editing the topic clears the old exact concept/context target.

`question_formats` is an optional list of concrete types, normalized and deduplicated.
An empty list permits automatic selection. Multiple selected types use the existing
mixed planner, which must include every selected type and no other type. There must
be at least one question per selected format. For these quizzes count means exactly
that many answerable items, with no hidden multipart expansion. Invalid outlines
receive bounded repair and never publish as a completed assessment.

Omitted result presentation is decided in the existing assessment-selection call;
explicit requests such as feedback without marks take precedence. The outline and
content calls retain their existing responsibility for marks, difficulty, sections
and educational content. This shared chat/UI pipeline can involve several bounded
calls; simplifying the form does not promise one total model request.

Empty format lists and omitted result styles are excluded from replay fingerprints,
preserving requests queued by earlier callers. Resolved preferences and formats are
checkpointed for retries. No database migration is needed for these request fields.

Verification includes 51 browser cases and 79 distinct backend cases across the
69-test assessment/chat regression run and 25-test intent/prompt run (15 overlap),
production TypeScript/Vite build and theme/UI checks. Live synthetic English and Urdu
selection/outline checks retained both requested formats, exactly four answerable
items and feedback-only presentation. These are contract checks, not a broad
subject-quality or educational-effectiveness evaluation.


## Revision practice workspace (2026-10-19)

Assessments → **Practice my mistakes** centralizes graded mistakes and partial answers. Assessment results now link to this workspace with their assessment filter preselected. The topic and assessment dropdowns support multiple selections; the filtered action is **Practice selected**.

| Contract | Behavior |
| --- | --- |
| `GET /api/v1/assessments/mistakes` | Owner-scoped history, 30 rows per page, repeated `assessment_id` / `topic_id` filters, source assessment and attempt links, feedback and topic labels. Includes the learner’s submitted answer and public option labels; never returns private answer keys or rubrics. |
| History | One row per source question, with its most recent mistake and accumulated failures across its revision lineage. A later correct graded answer marks the lineage corrected without removing earlier mistake records. Corrections use the current authoritative grade revision. |
| Automatic selection | Unresolved mistakes only; descending failure count, proportional score gap, marks, then recency. Duplicate root questions are removed before applying the requested maximum of 1–20. This is a transparent heuristic, not an LLM judgment of curricular importance. |
| `POST /api/v1/assessments/mistakes/practice` | Accepts `client_request_id`, optional assessment/topic ID arrays, and count. Owner transaction checks selected assessments and the existing two-active-job admission limit. |
| Durable generation | Selection and shuffled order are snapshotted once in the private generation job checkpoint. Retries reuse the same operation, selection and provenance. Each source produces one new answerable variation; unchanged prompts fail generation validation before checkpoint publication. |
| LLM responsibility | Generate fresh, self-contained wording/examples/values and appropriate choices, answers and rubrics using the existing assessment-generation workflow. |
| Server responsibility | Set the `revision assessment` tag, title, source assessment IDs, per-question root identity, concept IDs, source attempt/grade revision and learning context. Clients cannot submit these metadata fields. |
| Persistence | Existing `assessment.practice_lineage` JSON stores revision metadata; `Assessment.tags` and `source_assessment_ids` expose safe projections. No database migration is needed. Source snapshots preserve provenance even if a source is subsequently removed. |
| Learning evidence | Revision remains known-exposure/repeated practice. Cross-context revisions submit each question’s evidence in its original learning context and retain its specific source attempt and grade revision. |

Verification: 40 distinct backend cases passed across the 39-case regression run and final seven-case revision suite (six overlap). These include owner isolation, API metadata rejection, filters, concurrency, replay, multi-source generation, corrected history and cross-context evidence. A synthetic live-provider run produced three fresh schema-valid questions with server tags and source IDs intact. This is a generation contract smoke test, not a broad educational-quality evaluation.


### October 20: stable page caches and assessment review

Settled pages no longer refresh on timers, focus, visibility changes or reconnect. Owner-scoped in-memory caches persist until relevant writes, explicit refresh, bounded capacity eviction or account changes. Successful writes invalidate dependent domains and notify mounted views and same-owner tabs. Generation, grading and ingestion continue to poll only while unfinished, and completion invalidates their dependent views. Authentication checks still verify session access without resetting page content.

Mistake practice lives in Assessments; old Progress links redirect with filters and revision jobs intact. Mistake cards reuse the assessment answer component, resolving choice IDs to labels. Assessment list cards summarize the latest graded attempt with correct/incorrect counts (partial credit is included in incorrect and disclosed separately). Unattempted and ungraded attempts have distinct status badges. Summaries use one bounded, owner-scoped query for each page of assessments.


## Answer sheets and question-paper downloads

Interactive quizzes, written chat worksheets and assessment detail pages expose Upload answersheet for PDF, TXT and PNG/JPEG files. The regular chat attachment path also accepts these files for assessment answer preparation. Files remain owned by the shared Files service; extraction retains the assessment/attempt binding. Valid printed option letters or option text normalize to immutable option IDs before review. Existing draft answers survive incomplete extraction.

The student reviews extracted text, confirms it, and submits through the same `/attempts/{id}/submission` route, grading worker and learner-evidence worker as UI answers. Upload alone is pending transcription, never graded evidence. The owner-scoped assessment session synchronizes original chat cards and review cards, polls only unfinished evaluation/evidence work and shows Attempted plus saved question outcomes after grading.

`GET /api/v1/assessments/{id}/paper.pdf` renders an owner-authorized public assessment or unsaved current-chat draft as an A4 PDF with numbered parts, marks, available timing/instructions, and how to write/upload answers. It never publishes a draft, creates an attempt or reads private answer/rubric fields. Responses are private/no-store and include attachment download headers. The existing Print action remains available.

### Verification (2026-10-25)

- 37 distinct PostgreSQL integration cases across assessment, chat-assessment and answer-sheet suites passed. This includes real TXT/native PDF parsing, image upload/transcription plumbing, identical choice normalization/grading to typed answers, source ownership, extraction confirmation, preserved partial drafts, retries and public PDF export access.
- 56 selected fixture-based UI regressions passed, including dedicated PDF/TXT/PNG uploads, regular chat attachments updating original and new cards, assigned written uploads, file-receipt retry reuse, PDF downloads and canonical graded results.
- Two additional browser-to-database E2E cases passed for TXT interactive and PDF written assessments: real registration/profile gating, authenticated export, Files intake, native extraction, confirmation/submission, grading/evidence workers and saved results after reload. AI responses and remote file storage use the test server's deterministic substitutes; no handwriting-quality or live-provider accuracy benchmark is claimed.
- Production TypeScript/Vite build, theme/contrast checks, targeted Python checks and whitespace checks passed. A three-page nested-question PDF was rendered and visually checked; question headings stay with content across page breaks.

The browser tests exposed and fixed a first-upload refresh race and the detail page's failure to restore a graded attempt after reload. This change does not deploy or migrate the production application.


## Self-reported assistance and final scoring

Migration `20261025_0031` converts the existing assistance flag to the PostgreSQL `assessment_assistance_kind` enum (`unknown`, `independent`, `assisted`) and adds a separate enum `reported_assistance` plus nullable JSONB `scoring`. The separation preserves the existing server-enforced exposure flag for repeated practice; using a revision assessment alone never asserts that the student used AI or hints.

The shared UI selector explicitly asks about AI/hints and discloses the score policy before submission. Its value is saved with drafts and submissions, including transitions to answer-sheet uploads. The grader evaluates the normal rubric. On completion, `self-reported-assistance-v1` stores raw total, adjusted total, maximum, multiplier and disclosure: reported `assisted` gets 0.9x; `independent` and `unknown` get 1.0x. The multiplier is applied once to the final total, with four-decimal rounding. Per-question marks, correctness and misconceptions retain their raw rubric meaning. The existing learner-evidence independence handling remains in force.

Results display the adjusted final total and a visible raw-score/adjustment explanation. Corrections retain the prior disclosure and scoring metadata in grade history and calculate again from the new raw result, avoiding compounded penalties. Migration preserves existing grades; old rows keep `scoring=NULL` and are displayed without retroactive penalties. The downgrade refuses to discard persisted score-policy provenance.

### Final assistance-policy verification (2026-10-25)

The affected backend verification covered 66 cases; after extending the migration regression to recognize the new provenance downgrade guard, its focused rerun passed. All 58 selected UI checks and both full browser-to-database TXT/PDF grading cases passed, including persisted enum disclosures, adjusted totals, draft/upload transitions and reloads. Three final scoring/chat checks also passed against the rebuilt Docker frontend. The built backend separately confirmed 10 raw marks become 9 adjusted marks for reported assistance.

Both Docker images were rebuilt and all seven local services refreshed. API readiness is ready, frontend login returns HTTP 200, and the configured database reports migration `20261025_0031` with the native `assessment_assistance_kind` type. A network-disabled backend container generated a valid PDF and ran the baked `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` reranker (revision `1427fd652930e4ba29e8149678df786c240d8825`) successfully. Existing backend-map and README edits are outside this assessment change.
