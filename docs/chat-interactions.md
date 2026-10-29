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
`present_questionnaire`, `present_choices` and `request_input` are bound immediately. Mermaid, Lucide,
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
| Conversational questionnaire | `present_questionnaire`: one batch of 1–20 related questions with stable IDs; mix single/multiple choices and short/long text. All questions/options are retained. Reuses assessment `QuestionProgress`, navigation and choice/field controls, with one Submit all answers action. Creates chat metadata only, without assessment drafts, attempts, grades or automatic mastery. |
| Choices + custom text | `present_choices`: each chat option may include `input` with a label, short/long text kind, requiredness and max length. Selecting it opens an input beneath that option in ChoiceCard. IDs/labels have no special behavior. Assessment ChoiceOption remains unchanged. |
| Text/form | `request_input`: `text_input` has one text field; `form` has 1–4 fields with stable IDs. Fields support short/long text, bounded numbers and selections. Existing Input/Textarea/Select/FormField render the controls. |
| Static numeric visuals | `present_visuals`: `question` titles 1–8 `bars` with `label`, `value`, `max`, optional `unit` and `note`. For difficulty/ratings/comparisons use meaningful common scales and label subjective estimates. Bars are read-only and cannot be submitted as answers. |
| Actual action review | Reuse EventProposalCard and the Events proposal service. The real checkpointed interrupt is prepared before a pending proposal is displayed; graph initialization/resume is serialized by workflow thread. Existing claim/commit/replay still owns mutation authority. |
| Shared bar primitive | `ProgressBar` renders static values as accessible meters and existing quiz/calibration/generation data as progress bars. Displays exact value/scale and percentage; never converts ordinary prose percentages. |
| Main chat appearance | Settings → Profile & preferences → Chat appearance. Bundled Inter; Small/Medium/Large text sizes (15/16/18px at the standard root), Medium default. Browser-local appearance setting with cross-tab sync and blocked-storage fallback. Main chat text/composer only; phone composer remains at least 16px, code/math retain specialized fonts. |

Submissions extend the existing `interaction_response` with optional
`option_inputs: {option_id: text}` or `values: {field_id: text}`. The same durable
turn endpoint validates ownership, active/known fields, requiredness, length,
selection/numeric bounds and canonical content. Standalone inputs retain the
4,000-character limit; complete questionnaire/batch summaries allow 16,000. Server
labels build canonical content; accepted values and receipt save atomically.
Empty additive fields are excluded from request fingerprints so pre-upgrade pending
choice submissions can still replay. Hidden input values are never submitted.
Unsubmitted drafts remain owner-scoped in bounded ChatStore memory across navigation;
accepted answers and pending sends retain existing durable recovery.

An uncertain submission keeps its original payload and operation UUID. Freeze that
form and offer an explicit retry of the original answer until persistence confirms
the turn. A different answer cannot reuse the old operation, and completion of an
older operation cannot clear a newer pending send.

Questionnaire answers use `answers: {question_id: {selected, option_inputs, values}}`;
text questions use `values.answer`. Existing assistant messages with several input
cards are grouped in the same UI and submitted with `additional_responses` in one
owned message transaction. Already submitted cards remain read-only and are not
resubmitted. Every pending card/question must validate before any selection is
saved. The server supplies canonical question/option labels; duplicate, unknown,
cross-owner or invalid answers cannot partially commit a batch. Legacy request
fingerprints retain their original field order and omit empty new fields.

Presentation tools have their own bounded allowance (20 calls and 20 cards), separate
from external lookup/write budgets. The normal model/time/input limits still apply.
Prefer one questionnaire call over several standalone calls. A compact result receipt
never discards already validated UI metadata. Pause/resume retains presentation counts
and restores currently available common controls, including for older checkpoints.

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

Optional top-level fields are `description`, `unit`, `colors`, `enableControls`,
`model` and `stacked` (bar/area/composed).
Series accept `dataKey` and optional `name`; composed series require `type` Line,
Bar or Area. The [frontend contract](../frontend/src/lib/chartSpec.ts) bounds each
chart computation to 200 rows, six series and three charts per response. Generation
guidance targets 24,000 characters; the parser accepts up to 512,000 so copied source
can retain calculated numeric defaults and escaped labels. Parse caching remains
bounded to 30 entries and two million source characters.
Pie/radar allow at most 24 categories; radar requires at least three. Pie uses one
nonnegative numeric series with a positive total. Scatter x values are numeric.
Line/bar/area/composed gaps use null; all other series values are finite numbers within +/-1e100.
Arbitrary props/resources, duplicate series keys, missing non-derived values, all-null series
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

## Equation-driven chart exploration

Recharts enables controls for a valid equation model when `enableControls` is
omitted. Explicit `false` always keeps it read-only; charts without a model still
default to read-only. With controls enabled, users can
switch between Slider (default) and Number entry; the value, selected inputs and
mode survive entering/leaving fullscreen, and Reset restores supplied inputs.
Without `model`, edits remain independent data edits. No mathematical dependency
is inferred from unrelated facts or supplied measurements.

An optional `model` provides kind (`illustrative` or `established`), an explanatory
`note`, global `parameters`, and output `equations`. Each parameter has key/label,
initial value/min/max and optional step/unit. Optional `inputs` identify per-row
numeric inputs with dataKey/label and optional min/max/unit; these can describe the
independent axis or declare auxiliary data columns without plotting extra series.
Outputs are series keys or named helpers that feed plotted outputs; helpers share
the six-equation limit and never become extra visible series or controls. Global
parameters may be omitted when none are needed. Unrelated observation series remain read-only
in model mode. Values are computed in dependency order; users
edit inputs, never outputs. Derived values may be omitted or null placeholders, including
scatter/pie/radar: validation applies to the calculated results rather than gaps.

Example of an explicitly hypothetical model, not a prescribed teaching equation:

```json
{"type":"LineChart","title":"Hypothetical response","xKey":"x","enableControls":true,"data":[{"x":1,"y":null},{"x":2,"y":null}],"series":[{"dataKey":"y","name":"Response"}],"model":{"kind":"illustrative","note":"A simple assumed response curve, not measured data.","parameters":[{"key":"gain","label":"Gain","value":2,"min":0,"max":5}],"inputs":[{"dataKey":"x","label":"Input","min":0,"max":10}],"equations":[{"dataKey":"y","expression":"gain*x^2"}]}}
```

The frontend utility accepts explicit arithmetic, powers, parentheses, scientific
notation, pi/e and a small documented set of numeric functions. It never evaluates
JavaScript. Expressions are limited to 240 characters, 128 tokens and 32 levels;
models have at most eight parameters, eight row-input declarations and six outputs.
Unknown references, cycles, unused controls, unsupported syntax and invalid initial
domains disable the model locally. If supplied series values are usable, the chart
renders those original values with a notice and no controls, including fullscreen,
tables and downloads. No equation repair or invented values are applied. Invalid
base data and null-only fallback series still require source fallback. Invalid edits (including intermediate overflow or
division by zero) leave the last valid chart untouched. Finite plotted values are
bounded at +/-1e100 and large/tiny axis values use compact scientific labels.

Equation programs compile once per parsed model. Input changes are frame-coalesced
and remain within chart state, without network/model calls, transcript edits or
learner-evidence writes. Tables, fullscreen and SVG/PNG exports use current results;
exports include assumptions, equations and current parameter values. Existing lazy
family loading and hidden-inline-plot freezing remain in place.

`chat_ui.py` remains the only model-facing guidance: common instructions advertise
this capability; its detailed schema is part of the on-demand charts reference.
Contextual invented models are allowed when useful and labeled illustrative with
assumptions. The model can instead choose independent editing or read-only data.
Useful linked exploration is selected proactively; the learner does not need to
request equations or sliders. Global parameter names cannot collide with sampled
axis or row fields. Plotted calculations use matching series keys; helper expressions
may be named when they feed plotted results. There is no automatic current-setting marker.

Additional hardening: bounded scalar row metadata is ignored unless explicitly used
as a declared input. It cannot become renderer props or equation variables. Models
with ambiguous `e`/`pi` field references fall back rather than silently substituting
mathematical constants. Copied source retains numeric plotted defaults and omits
calculated helpers; valid equations recompute them when reopened. Numeric line/area
axes use actual distances; categorical and bar axes keep their category layout.
Exports reject edits or viewer closure during capture, so captions and geometry
cannot come from different model states. Static fallback exports identify themselves.
When a failed model has an all-null prediction series alongside usable observations,
the fallback shows the usable series and omits the unavailable one. Invalid observed
values are still rejected; neither missing predictions nor replacements are invented.

Second hardening pass (2026-10-29): 74 equation/data/cache checks, 47 production-build
browser checks and 15 backend policy checks passed. Browser coverage includes numeric
spacing, linked helpers, observation fallback, concurrent export edits, all seven
families, lazy loading, and zero rich-message/chart rerenders during typing or
unchanged refresh. Three live synthetic scenarios passed (factual chart, proactive
equation exploration, requested practice); both generated charts also passed the
exact frontend parser with their models active where expected. No learner records
were written. Local 200-row dependent-update p95 remained below one millisecond;
these are local measurements, not a timing guarantee on every device.

Hardening verification (2026-10-29): 61 equation/model checks and 15 browser cases
passed, covering omitted/false controls, the reported axis/parameter collision,
unsafe expressions, initial domain failures, supplied-value fallback, fullscreen,
Reset and downloads. Backend teaching/UI policy checks passed (15 tests). Live
synthetic checks produced a factual chart without an exercise, a proactive linked
model from a natural explanation request, and explicitly requested practice with
visible teaching. Model output varies; the frontend validates every response and
does not rely on prompt compliance for model failure isolation.
