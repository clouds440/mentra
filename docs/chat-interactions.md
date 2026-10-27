# Native chat interactions

Mentra extends its existing assistant-message metadata and LangChain domain tools.
It does not interpret model-generated HTML, JavaScript or free-text UI instructions.
Choices, input forms and static value bars live in `chat_message.metadata`, while
quizzes use the existing assessments and attempts. No interaction-table migration
is required. Rich rendering adds local Mermaid, remark-directive, DOMPurify and
bundled Inter font dependencies.

## Rich native UI contract

The single model-facing usage contract is
`backend/app/langchain/prompts/chat_ui.py`. Its compact common guide is composed
once through the CHAT registry, including direct chat, tool rounds and edits.
`present_choices` and `request_input` are bound immediately. Mermaid, Lucide,
semantic colors and simple inline bars need no reference lookup.

Detailed charts, disclosures, custom colors and native multi-bar references remain
in that same module. The model loads only the needed topics through the existing
`enable_workflow_tools` tool, e.g. `{"ui":["charts"]}`. `ui:["bars"]` also enables
`present_visuals`; exact tool-name/module discovery still works for all domains.
Selected reference sources are included once in subsequent system instructions,
including budget-final rounds, and are not duplicated in tool receipts. Loading is
budget-checked together with tool schemas; rejection rolls back reference state.
References are scoped to the current turn, never shared between users/turns.
Compatible examples in conversation can be reused without another lookup.

The always-on guide advertises every capability and tells the model to consider
useful UI even without an explicit request, honor prose/code-only requests, and
discover unfamiliar advanced formats instead of guessing. There is no extra LLM
classifier or mandatory per-answer reviewer. Tool descriptions own argument
semantics; assessment/Events retain domain rules. Keep UI examples/policy here.

| Capability | Contract and existing resource |
|---|---|
| Choices + custom text | `present_choices`: each chat option may include `input` with a label, short/long text kind, requiredness and max length. Selecting it opens an input beneath that option in ChoiceCard. IDs/labels have no special behavior. Assessment ChoiceOption remains unchanged. |
| Text/form | `request_input`: `text_input` has one text field; `form` has 1–4 fields with stable IDs. Fields support short/long text, bounded numbers and selections. Existing Input/Textarea/Select/FormField render the controls. |
| Static numeric visuals | `present_visuals`: `question` titles 1–8 `bars` with `label`, `value`, `max`, optional `unit` and `note`. For difficulty/ratings/comparisons use meaningful common scales and label subjective estimates. Bars are read-only and cannot be submitted as answers. |
| Actual action review | Reuse EventProposalCard and the Events proposal service. The real checkpointed interrupt is prepared before a pending proposal is displayed; graph initialization/resume is serialized by workflow thread. Existing claim/commit/replay still owns mutation authority. |
| Shared bar primitive | `ProgressBar` renders static values as accessible meters and existing quiz/calibration/generation data as progress bars. Displays exact value/scale and percentage; never converts ordinary prose percentages. |
| Main chat appearance | Settings → Profile & preferences → Chat appearance. Bundled Inter; Small/Medium/Large text sizes (15/16/18px at the standard root), Medium default. Browser-local appearance setting with cross-tab sync and blocked-storage fallback. Main chat text/composer only; phone composer remains at least 16px, code/math retain specialized fonts. |

Submissions extend the existing `interaction_response` with optional
`option_inputs: {option_id: text}` or `values: {field_id: text}`. The same durable
turn endpoint validates ownership, active/known fields, requiredness, length,
selection/numeric bounds and the canonical 4,000-character user message. Server
labels build canonical content; accepted values and receipt save atomically.
Empty additive fields are excluded from request fingerprints so pre-upgrade pending
choice submissions can still replay. Hidden input values are never submitted.
Unsubmitted drafts remain owner-scoped in bounded ChatStore memory across navigation;
accepted answers and pending sends retain existing durable recovery.

An uncertain submission keeps its original payload and operation UUID. Freeze that
form and offer an explicit retry of the original answer until persistence confirms
the turn. A different answer cannot reuse the old operation, and completion of an
older operation cannot clear a newer pending send.

### Rich Markdown

The same MarkdownContent renderer serves chat and Library. No raw HTML is enabled.

| Format | Example | Rendering |
|---|---|---|
| Mermaid | Fenced `mermaid` source | Lazy local rendering; source view/copy, expanded Dialog and sanitized SVG download. Light/Dark/System, title/description support, per-instance SVG IDs, strict config, bounded source/edges, at most three rendered diagrams per content. Invalid/unsafe source remains accessible. |
| Recharts | Fenced `recharts` JSON | Data-only chart configuration using familiar Recharts type/dataKey names. Line, bar, area, composed, pie, radar and scatter families load individually near the viewport. Exact data table, source/copy and fullscreen views; accessible keyboard tooltips and theme-aware colors. Invalid data/import/render failures stay local. No JSX execution or model-authored callbacks/props. |
| Semantic color | `:color[Success]{tone="success"}` | success/warning/danger/info/accent; named aliases map to these tones. Contrast adapts to the actual surface. |
| Custom color | `:color[Needs review]{hex="#F54927"}` | Six-digit hex only; readable foreground adjustment, forced-colors fallback. No arbitrary CSS. |
| Inline icon | `:icon[BookOpen] Further reading` | Installed Lucide names in PascalCase or kebab-case. Every response icon loads on demand; the catalog contains import functions, not eagerly imported glyphs. Unknown names, loading/import failures and render errors show a fixed-size CSS placeholder, never raw names or broken images. Decorative and hidden from screen readers; keep adjacent meaningful text. Copy omits icon tokens and preserves literal code. At most 32 rendered icons per response. |
| Optional static bar | `::bar{label="Difficulty" value="3" max="5" unit="points"}` | Explicit bounded meter. Prefer `present_visuals` so bars need no response markup. `::progress` is also accepted. |
| Callout | Container directive `:::callout{title="Key idea" tone="info"}` with body and closing `:::` | Quiet semantic Card styling. |
| Disclosure | Container directive `:::details{title="Show a hint"}` with body and closing `:::` | Native accessible disclosure. Never include unreleased assessment answers in hidden content. |

The allowlisted AST transform shares parsing with markdownPlainText. Copy removes
valid presentation syntax, retains text/counts, and preserves malformed directives
and exact code payloads. Mermaid is rendered locally with no external fetches,
callbacks, model-authored initialization or raw HTML labels. App-owned SVG
sanitization also covers exported diagrams. See [verification](Interactive_UI_Verification.md).

### Rendering performance

Recharts JSON requires `type`, `title`, `xKey`, `data` and `series`. For example:

```recharts
{"type":"BarChart","title":"Study time","xKey":"topic","unit":"minutes","data":[{"topic":"Algebra","minutes":20},{"topic":"Geometry","minutes":30}],"series":[{"dataKey":"minutes","name":"Study time"}]}
```

Optional top-level fields are `description`, `unit` and `stacked` (bar/area/composed).
Series accept `dataKey` and optional `name`; composed series require `type` Line,
Bar or Area. The [frontend contract](../frontend/src/lib/chartSpec.ts) bounds each
chart to 24,000 characters, 200 rows, six series and three charts per response.
Pie/radar allow at most 24 categories; radar requires at least three. Pie uses one
nonnegative numeric series with a positive total. Scatter x values are numeric.
Cartesian gaps use null; all other series values are finite numbers within ±1e12.
Arbitrary props/resources, duplicate series keys, missing values, all-null series
and unsupported shapes are rejected. Original data names stay in source/tables;
only app-owned canonical field names enter Recharts shape data.

Parsed charts use a 30-entry owner-scoped cache. Chart families and their shared
Recharts dependencies load only when a valid chart approaches the viewport.
Chart canvases have no conversation/theme subscriptions. Existing memoized message
identity rules prevent typing/unchanged refresh/font changes from rerendering them.
ResizeObserver handles actual plot sizing locally. Small charts animate for 250ms
with Recharts' reduced-motion-aware `auto`; above 120 row-series pairs animation is
disabled. Tooltip changes do not animate or delay exact values.

Native inputs/bars are ordinary application components with no animation gate or
extra model round needed merely to render accepted data. Static cards subscribe to
no conversation state. Active forms/actions subscribe only to busy/error state;
completed messages and Markdown are memoized. Authoritative refreshes preserve
unchanged object identities using all metadata, so real receipts and value changes
still publish correctly.

Plain single-line text without Markdown syntax/plugins bypasses AST parsing.
Directive parsing runs only when an extension marker is present; semantic colors
use CSS without per-span observers or state updates. One chat-scope CSS variable
applies font size without rerendering each message. Custom colors and diagrams
share a single resolved-theme observer.

Mermaid's heavier library/layout is loaded near the viewport, yields before layout,
uses a bounded owner-scoped cache, and never gates the surrounding text. The
cache holds at most 30 entries and two million
characters, with one million characters per SVG. Owner changes fence queued jobs.
SVG IDs are rewritten in one pass; encoded CSS resource loading is rejected before
rendering and generated SVG is sanitized. A failed diagram chunk leaves its source,
the rest of the answer and the composer usable. This does
not make first-use diagram layout equivalent to plain text. The performance suite
measures actual input-to-frame latency, completed-component renders and long tasks;
it also verifies that static native bars do not download Mermaid code and changed
metadata still updates the correct visual.

## Model requests

`present_choices` accepts a validated `kind` (`single_choice` or `multiple_choice`),
`question`, and bounded `options` with stable IDs and labels. The server assigns a
turn-derived interaction UUID. ChatResponse validates the public card contract.
The tool is available in the chat domain and uses existing activity announcements,
write/result budgets and ordered dispatch. Repeated identical tool calls yield one card.

For quizzes use `assessment_generate` with `question_format: "mcq"`, the requested
count (1-10), a learner-owned context and established concepts. Existing generation,
source grounding and concept-review requirements apply. Ordinary quizzes default
to interactive delivery while explicit written/printable requests retain their format.
Delivery and question type are independent. Generation is available on tool-enabled chat turns. Revisions
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
