# Native chat interactions

Mentra extends its existing assistant-message metadata and LangChain domain tools.
It does not interpret model-generated HTML, JavaScript or free-text UI instructions.
No new database tables, migrations or dependencies are required: choices live in
chat_message.metadata, while quizzes use the existing assessments and attempts.

## Model requests

`present_choices` accepts a validated `kind` (`single_choice` or `multiple_choice`),
`question`, and bounded `options` with stable IDs and labels. The server assigns a
turn-derived interaction UUID. ChatResponse validates the public card contract.
The tool is available in the chat domain and uses existing activity announcements,
write/result budgets and ordered dispatch. Repeated identical tool calls yield one card.

For quizzes use `assessment_generate` with `question_format: "mcq"`, the requested
count (1-10), a learner-owned context and established concepts. Existing generation,
source grounding and concept-review requirements apply. The generation API and tool keep written as their default so plain quiz requests
and old callers remain compatible. The model selects MCQ for interactive/clickable
requests or when it decides an interactive check will help, regardless of planning
keywords. Generation is always available on tool-enabled chat turns. Revisions
preserve MCQ format unless another format is requested.

## Submissions and persistence

ChoiceCard uses native radio/checkbox controls and the shared Button. Submit sends
`interaction_response: {message_id, interaction_id, selected}` through the existing
persistent conversation turn endpoint and ChatStore. The server checks ownership,
conversation/message association, option IDs and cardinality under the existing
owner transaction lock. It saves the card receipt and canonical student message
atomically, using server labels instead of client text. The model receives both
the canonical message and the structured response. Ordinary turns are unchanged.
Retries reuse the durable turn ID; concurrent or changed submissions cannot answer
the same interaction twice. Accepted selections are read-only in chat history.
Generation failures retain the accepted answer and use the existing chat retry flow.

The general ChoiceOptions component renders native single/multiple selections,
with controlled values and callbacks, without chat, assessment, API or store
dependencies. ChoiceCard supplies LLM-answer submission; MCQAssessment and
AnswerSheet reuse the same controls. Backend app.interactions owns shared choice
schemas and option-answer validation; chat-specific IDs/receipts stay in app.chat.

MCQAssessment shows one question with progress, Back and immediate Next. Selections stay in owner/session memory until final Submit; advancing does not write the database. Refresh can discard an unsubmitted local draft. Final submission creates/reuses the durable attempt and atomically saves the complete answer set before queuing evaluation. Rendering/reopening alone does not create attempts. Interactive generation saves immutable questions/private keys in Assessments; written worksheets retain their draft/add policy.

The last action is Submit, with no redundant Finish Quiz button. It uses the shared complete-submission API and durable worker. Submitted answers remain visible while evaluation runs, and the composer displays the evaluating indicator. Correct-option
IDs, model answers and rubrics remain private until feedback. The worker grades
MCQ IDs deterministically against the private key; written questions retain their
existing LLM grading. Typed and reviewed OCR answers may use exact option IDs (including letter IDs)
or unambiguous exact option labels; the server normalizes them deterministically
while preserving original submission fingerprints and extraction provenance.
Ambiguous answers require correction. Both paths use the same grade persistence, retries, correction
history, evidence admission and learner/profile projection. Correct/incorrect,
concept, difficulty, attempt number and self-reported assistance retain the existing
provenance. There is no parallel mastery implementation.

AnswerSheet renders submitted MCQ labels, per-question feedback, a total score and
existing learner-evidence status. This also supports MCQ attempts opened on the
Assessments page. Completed results remain available after reopening chat.

## Important implementation files

- `backend/app/interactions/schemas.py`: general option contracts and deterministic selection/answer validation.
- `backend/app/chat/interactions.py`: choice contracts, stable IDs, selection validation and model tool.
- `backend/app/chat/repositories/postgres.py`: atomic choice receipt and conversation turn.
- `backend/app/langchain/history_orchestration.py`, `workflow_tools.py`, and chat/generation prompts: model integration.
- `backend/app/assessments/schemas.py`, `repositories/postgres.py`, `api/routes/assessments.py`, and `langchain/assessment_workflows.py`: public/private MCQ contracts, draft persistence and worker grading.
- `frontend/src/components/interactions/ChoiceOptions.tsx`: general reusable controlled radio/checkbox component.
- `frontend/src/components/chat/ChoiceCard.tsx`, `ChatMessage.tsx`, and `stores/chatStore.ts`: native choices and reliable conversation submission.
- `frontend/src/components/assessments/MCQAssessment.tsx`, `ChatAssessmentCard.tsx`, and `AssessmentWorkspace.tsx`: quiz progress, recovery and shared feedback.
- `backend/tests/test_chat_interactions.py`, `test_mcq_assessments.py`, and `frontend/tests/chat-interactions.spec.ts`: feature verification.

## Scope and limitations

Practice and mock assessments currently release feedback only after final submission.
There is no timed/proctored exam enforcement, immediate per-question feedback or
hint counter beyond existing assistance reporting. Provider-generated key accuracy
still depends on generation quality; deterministic tests verify contracts and
execution, not the educational accuracy of a live model. New interaction kinds can
extend the typed metadata union and native renderer without changing text chat.

## Validation

- 86 backend tests passed without skips in isolated migrated PostgreSQL schemas:
  native choices/MCQs, ownership, concurrency, replay, partial persistence, private
  keys, grading/evidence, persistent chat, written assessments, orchestration,
  activity streaming, titles and chat evidence jobs.
- 13 browser scenarios passed: existing history and written-assessment workflows,
  keyboard-operable mobile single/multiple choices, structured AI continuation,
  refresh restoration, lost-answer-response recovery, and a five-question MCQ with saved progress and final
  learner-integrated results. Follow-up review adds explicit interactive/clickable
  wording, model-selected quizzes without quiz keywords, immediate assessment
  persistence, and conflicting-answer recovery. AI uses deterministic test fixtures.
- TypeScript/Vite production build and semantic theme checks passed.

No application-database migration or deployment was performed.

## Review corrections

The follow-up review corrected an invocation gap: generation schemas were exposed
to the model but dispatch still rejected generation outside assessment planning.
Both schema selection and dispatch now share one capability check. Browser coverage
includes explicit interactive wording, clickable-option wording and an LLM-chosen
quiz after a message with no quiz/assessment keyword. Ordinary written generation
and discussion/revision behavior remain covered. Stale draft-answer conflicts restore
authoritative answers instead of allowing unseen newer answers to be overwritten.

Interactive work is an existing Assessment and Attempt, with the same learner-model
admission as paper OCR and chat reply answers. No parallel assessment storage,
grading service or learner state was introduced.

## Shared graded feedback

`QuestionFeedback` is a controlled presentation component without chat or API
dependencies. `AssessmentFeedback` joins persisted grades and student answers by
immutable question ID and uses the same renderer in chat and Assessments. Green,
amber and red semantic theme tokens, icons and text distinguish correct, partial
and incorrect answers in both themes. The summary shows counts and total marks.

The assessment domain computes the public outcome from validated scores and marks
when completing the existing grading job. The LLM writes rubric-based feedback
for written answers; MCQs use the stored private answer key. Correct option labels
are published only with completed grades. Existing historical grades use a score
based display fallback. Correction retains prior grades and answers.

Dummy browser scenarios capture desktop/mobile interactive questions and feedback,
including correct, partial and incorrect examples. These fixtures exercise real
chat, database, grading and learner evidence paths with deterministic model output.
