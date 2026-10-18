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
