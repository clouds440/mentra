# Flexible assessments and mock papers

Assessments reuse the existing draft, publication, attempt, grading and learner-evidence lifecycle. Revisions create a new draft; original questions, answers and grading history remain intact.

## Request-led structure

Chat and the creation form accept an entirely unspecified assessment request. A background selection step reads the existing owner-bound learner tools for active contexts, study priorities, verification candidates and relevant learning context. When no active context exists, it considers the learner's other non-archived contexts. Selected Library metadata is read through the RAG facade in one owner-checked batch. Profile details supply the education level and learning goals already collected during onboarding/settings.

The model chooses a coherent topic and delivery format from this packet. With no useful data it can choose a general reasoning baseline without inventing weaknesses. It never asks for missing configuration merely to complete the request. Explicit topics and formats bypass this selection model call. Resolved choices are checkpointed before content generation so retry does not change the topic. They stay private; the public job exposes the chosen topic as its title.

An outline model chooses the appropriate length and question mix. Explicit counts, formats, marks, timing, instructions and section plans take precedence. The legacy direct API retains its five-question written default for existing callers; this is not the chat/UI default. The creation form queues every request for consistent progress and recovery.

Academic level is not a required creation field. Account education level is the default; current evidence calibrates difficulty conservatively. Any explicit higher/lower level or difficulty request takes precedence and is never capped by the account level or an ability estimate. The optional internal `level` field records only a requested override and never writes back to profile settings.

`result_style=grade` means simple grading: correctness and feedback without per-question marks, totals or letter-grade scales. Internal equal weights support grading/evidence when no marks were requested. `marks` retains visible marks and totals; `feedback` is also supported for API callers. These choices persist in assessment preferences and survive revision, chat publication and reopening. UI question views, answer review, feedback and print respect the mode; the chat status tool omits numeric score summaries for unmarked reviews.

Question types are open strings. Single-choice, true/false and multiple-selection questions use option controls. Short answers, numerical responses, essays, proofs, cases, matching and other types use a written response when no specialized widget exists. Prompts, options, answers and rubrics have no fixed character limit; operational model budgets still apply.

Mock papers carry exam instructions, timing, sections, globally numbered main questions, shared context, nested part paths and positive marks. Each answerable leaf has its own immutable question ID and grading key. A reference such as `3(a)(ii)` maps to that ID, independent of the item's position in the stored array. Section totals and explicit overall totals are checked. Print produces a separate blank question paper without chat, student answers or private grading keys.

When an AI outline's arithmetic misses a requested total, the server apportions its relative part weights to that total before writing questions or rubrics, preserving every part. Explicit caller-supplied section marks must already agree with the total and are not silently changed.

## Flexible canonical concepts

Assessment generation calls the learner's permissive resolver. It reuses clear exact identities, prefers an unambiguous match in the learner's context, and registers a separate canonical concept for a new or ambiguous label. Ambiguous identities receive a stable context-qualified suffix. Duplicate concepts are acceptable; uncertain semantic merging must not block a valid assessment or rewrite existing learner history.

Generated concept names, human labels accidentally supplied as IDs, and missing attribution are resolved through the learner facade. An unknown UUID is never accepted as identity; explicit names or the assessment topic provide the fallback. Labels are processed in small packets without limiting the number of concepts in the assessment. Generation adds context membership but creates no mastery evidence. Other learner workflows retain their existing strict resolution behavior.

## Durable generation and grading

Mock papers, unspecified lengths and long requests are queued independently of the chat-turn deadline. The owner-scoped job stores its outline and completed question batches privately. Polling exposes counts and state, not partially generated solutions. Retry resumes completed batches. Lease tokens fence stale workers; operation fingerprints prevent a changed retry from reusing an old result. Grounded work must retrieve eligible Library sources and use valid source tokens.

Grading also checkpoints completed batches privately against the question snapshot, submitted answers and grading revision. Retry can resume those batches. Grades and learner evidence publish atomically after the complete attempt is ready. Multiple-selection scoring subtracts the fraction of distractors selected from the fraction of correct options selected, with a floor of zero. Selecting every option earns no credit when distractors exist.

Typed paper drafts can be saved and reopened. Handwritten uploads map printed numbers and nested part references to immutable IDs; transcription requires review before submission. Vision packets contain public questions only. Provider-dependent handwriting accuracy is not guaranteed by deterministic tests.

## Runtime bounds

There is no fixed five-question template, ten-question generation cap or question-text character cap. Jobs still have finite resource budgets: generation and long grading allow 900 seconds, up to 256 model rounds, and bounded token envelopes per run. Question generation batches contain at most three answerable parts. Uploads retain the 25 MiB limit, with up to 40 vision pages per document. Interrupted work keeps checkpoints for retry; these bounds are not a promise of unlimited paper size.

The assessment worker needs the same embedding, vector-store, Library storage and profile dependencies as the API. Migration `20261014_0023` adds paper metadata, private grading checkpoints and generation jobs. Migration `20261014_0024` adds preferences with backward-compatible defaults. Rebuild and recreate the API, assessment worker and frontend together. Selection has its own 120-second bounded budget before content generation; model admission covers both phases. Retry observes the same owner concurrency limit as new requests.

## Verification

Focused backend integration tests cover mixed response modes, nested paper references, full-paper generation and grading, permissive concept ambiguity, unknown generated IDs, migration preservation, stale lease fencing, and generation/grading checkpoint recovery. Browser fixtures cover compact desktop/mobile interaction, one final quiz submission, paper printing, saved written drafts and generation progress recovery. These fixtures verify UI behavior; isolated PostgreSQL tests verify persistence and evidence behavior.

Verified locally on 2026-10-14: all 90 focused assessment regression checks passed. Another 21 targeted intent/engine checks covered final source-context fallback and checkpoint preferences; seven fast contract checks covered shorthand expansion, immutable request fingerprints and equal weights for simple grading. Six production-browser assessment checks and nine existing quiz-recovery checks passed, as did TypeScript/Vite, theme/UI checks, container builds and production asset serving. The production browser checks include entirely blank creation and correctness/feedback without visible marks or letter grades.

A synthetic live-provider check produced six main questions, 13 parts and exactly 30 marks across essay, MCQ, numerical, short-answer and true/false formats. A content batch generated from that outline passed validation after the automatic repair path corrected its batch count. This verifies model/schema compatibility, not a full live learner assessment or handwriting accuracy.

Screenshots: [mixed practice on mobile](assessment-engine/mixed-practice-mobile.png), [paper preview on mobile](assessment-engine/mock-paper-mobile.png).
