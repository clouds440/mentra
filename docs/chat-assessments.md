# Assessments through chat

Students can request a quiz or mock paper in a normal conversation. The
`assessment_generate` tool creates a chat-scoped draft and returns a public card.
Question IDs, private grading keys, rubrics, and source provenance are stored
once. Private keys never enter chat responses or the browser.

The default setting is **Always auto add assessments: off**. Drafts stay in their
own chat and do not appear in the Assessments library. **Add to assessments**
publishes the same questions and IDs atomically, without another model call.
Publishing is idempotent. Saved assessments and attempts remain independent of
the originating conversation. Deleting an assessment does not silently recreate
it from an old card. Settings are account-owned and use revision checks.

Students can use **Add & answer** for an inline answer sheet, type numbered
answers in the composer, or attach an answer document/image and ask for grading.
Asking to evaluate a draft adds it to Assessments. `assessment_lookup` also finds
previously saved assessments for answering in a later conversation. Mentra must
ask which assessment when the intended target is ambiguous.

Before solving, students can ask about a question or request changes in chat.
`assessment_question` reads one complete public question without exposing its key,
saving a draft, or starting an attempt. `assessment_revise` generates a separate
version using the original concepts and the student's exact requested changes.
Wording, difficulty, format, and question count can change. Original questions,
grading keys, submissions, and grades remain intact. A different topic uses new
generation; a revised version follows the same auto-add preference as other drafts.
The model must identify the intended version when several drafts are present.

`assessment_answer` checks ownership, current conversation membership for drafts,
and the server-selected attachment IDs. Typed answers must be exact excerpts of
the current student message. The tool cannot substitute an AI-written solution.
Numbered answers map to immutable question IDs. The inline card allows missing
answers and transcription to be corrected before complete submission.

Partial typed answers across messages resume the latest unfinished typed attempt.
Students can explicitly request a new attempt to start over without merging answers.
An explicit attempt ID can continue other unfinished work. New text merges by
immutable question ID and retains upload provenance; combined work requires review
before submission. Durable message fingerprints reject changed retries and prevent
replays from replacing subsequent answers. A failed upload retains the saved card
and a draft attempt so students can retry or type their answers. Status reads now
return a bounded score/feedback packet and the full feedback card. Repeated tool
rounds show one latest card per assessment version. Deleted saved assessments are
marked as deleted in their original chat and cannot be republished implicitly.

Images and PDFs use bounded, page-aware vision transcription, with question
numbers and IDs provided by the server. No model answers or rubrics are supplied
to the transcription model. Successful vision avoids redundant OCR. Unsupported
or failed vision falls back to text extraction with a warning. DOCX and other
supported document formats use the shared Documents reader.

Complete, unambiguous numbered typed answers can queue grading directly when the
student requests evaluation. A deterministic parser must agree with the verbatim
tool mapping for every question. Other prepared answers require explicit review
and submission in the chat card, including all document and image transcription. The same
durable grading worker serves chat and the Assessments page, returns per-question
feedback, and admits only sufficiently reliable learner evidence. Formal grading
exchanges are excluded from informal chat evidence to avoid double counting.

Generation currently supports 1–10 questions and established concepts in an owned
learning context. Unrecognized concepts retain the existing review requirement;
the model must explain it rather than silently inventing canonical concepts.
Multiple independent files are not automatically combined into one answer sheet;
use a single document/PDF or choose one file. Vision accuracy depends on the
configured provider/model and is not established by deterministic integration tests.

# Workflow safeguards

The coordinator supports subsequent tool rounds and adjacent independent learner
reads in parallel. Writes and reference-mutating tools remain ordered. It selects
domain schemas, caches reads, compacts duplicate results, and bounds total tool
results. Nested generation, grading and vision share model-call/input/output and
deadline limits. Generation/grading are batched and inputs are checked before
provider calls. Actual usage and cached-token counts are logged when available.
Write receipts reserve UTF-8 bytes as well as tokens. Docker prepares its tokenizer
vocabulary at build time; token counting never initiates a request-time download.
Local development can warm the tokenizer once with
`python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"`.
Without a valid cache, byte counting conservatively enforces budgets; large requests
may require smaller batches rather than silently exceeding a provider context.

A stateless provider still receives instructions and enabled schemas with each
request; omitting those would change behavior. Provider prompt caching may reduce
billing when supported. These changes reduce context size rather than claiming
that LangGraph removes repeated provider input.

Assessment corrections preserve immutable observations and withdraw obsolete
accepted evidence transactionally, including low-confidence corrected grades.
Subject-answer evidence projects only domain familiarity into the profile; it
does not infer general reasoning or rewrite user-entered facts. Projection
snapshots remain append-only and replays do not add evidence weight twice.
The profile education-context version is captured when work is submitted/queued.
Multi-concept questions count once using their overall question grade, with
conservative agreement across accepted concepts for older evidence.

Migration `20261010_0015` is additive apart from expanding the evidence-state check.
It adds generation leases, assistance provenance, submission context versions,
chat drafts, and assessment preferences. Apply through the existing deployment
migration runner; do not manually synchronize SQLAlchemy metadata in production.
Migration `20261010_0016` adds chat-answer start fingerprints and message provenance
to attempts. Both upgrades and downgrades use the existing Alembic chain.

# Verification

The affected-domain regression suite passed 290 backend tests with isolated,
migrated PostgreSQL schemas. The final logging connections also passed 13 focused
chat/vision/coordinator checks. Nineteen browser scenarios passed across the main
run and corrected reruns, covering chat drafts, typed grading, upload review,
recovery, auto-add preferences, chat deletion, existing assessments, events,
ordinary attachments, chat history and onboarding/profile behavior. The frontend
TypeScript/Vite production build passed. AI responses were deterministic test
fixtures; live provider handwriting accuracy was not benchmarked. No application
database migration or production deployment was performed.

The subsequent gap review passed 300 backend regression tests and 42 final focused
checks, with no skipped tests. Five browser scenarios passed for chat discussion,
revisions, partial-answer continuation, inline grading, draft persistence, settings,
events, existing assessment corrections and ordinary document workflows. The two
chat scenarios were rerun after the final card recovery changes and passed. The
final TypeScript/Vite production build passed. The migration regression checked
metadata against the migrated schema and exercised downgrade/upgrade preservation.
These checks use isolated databases and deterministic AI fixtures; the application
database and live provider were not exercised. The Docker tokenizer bake command
was verified in the cached backend image; a full image rebuild was not performed.
