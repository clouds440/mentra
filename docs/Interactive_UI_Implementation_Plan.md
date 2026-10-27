# Interactive UI and rich responses: implementation plan

Date: 27 October 2026. Implementation authorized after this plan was written; see [the implementation and verification record](Interactive_UI_Verification.md) for delivered behavior and evidence.

## Recommendation

Extend Mentra's existing native controls, durable chat submissions and shared Markdown renderer. Use Pydantic tool contracts for collecting answers and requesting native visual components. Static value bars use structured `present_visuals` data, including difficulty, ratings, quantities and comparisons; they are not live progress tracking. Mermaid fences and selective inline color use explicit Markdown extensions. React components remain application-owned.

Give the main chat a softer, clearer reading style using explicitly bundled Inter, plus a chat-only Small / Medium / Large font-size setting with Medium selected by default. Keep model-facing UI usage instructions together in one shared, versioned prompt module.

The model should describe an input's behavior explicitly. An option ID identifies the option; it should not secretly mean “open an input” because of a particular name or label. Selecting “I'll write my own topic” should reveal a labeled input inside the existing card, require a nonblank value, and submit both the option and entered topic through the current durable turn endpoint.

Reuse is the default implementation rule: modify existing resources first; generalize only where there is a concrete second consumer; add small adapters or primitives where existing resources cannot represent the behavior.

## 1. Current implementation and reusable resources

These findings were checked against the current source. Existing documentation contains some historical behavior that will need updating, particularly quiz delivery defaults.

| Existing resource | Current behavior | Planned use |
|---|---|---|
| `backend/app/interactions/schemas.py` | Shared `ChoiceOption`, `ChoiceContent`, selection validation and assessment answer normalization | Keep the reusable choice foundation. Add chat-specific option input extensions without enabling free text in graded MCQ option schemas. |
| `backend/app/chat/interactions.py` | `present_choices`, server-generated stable UUIDs, typed cards and canonical answer resolution | Extend this tool for choice-with-input; add bounded text/form contracts and server-side response resolution here. |
| `backend/app/chat/repositories/postgres.py` | Owner/conversation checks; atomically saves an answer receipt and canonical user message; durable retry handling | Generalize existing interaction resolution and receipt updates. Keep the same transaction and idempotency path. |
| `backend/app/chat/schemas.py`, `response.py` | Typed request and response boundaries; interactions currently contain only choice cards | Extend to a typed interaction union while preserving legacy choice payloads. |
| `backend/app/langchain/history_orchestration.py`, `capabilities.py`, `tool_selection.py` | Constructs tools, discovers/binds capabilities, dispatches calls and collects cards | Register new schemas through the same discovery and dispatch path. Verify schema availability and execution together. |
| `backend/app/langchain/prompts/chat.py` and `prompts/registry.py` | Core conversation guidance and central prompt composition | Register one shared UI usage prompt; move overlapping UI instructions into it instead of appending rules across domain prompts. |
| `frontend/src/components/interactions/ChoiceOptions.tsx` | Controlled radio/checkbox renderer shared with assessments | Preserve this domain-independent base; extend composition to show attached fields in chat. |
| `frontend/src/components/chat/ChoiceCard.tsx` | Selected IDs only; submits through ChatStore | Add conditional input, validation, drafts and saved-answer display. Extract a shared interaction frame only when text/form cards also use it. |
| `frontend/src/stores/chatStore.ts` | Durable sends, pending request recovery, optimistic state and receipt updates | Extend existing payload/receipt handling for text values and additional interaction kinds. |
| `frontend/src/components/events/EventProposalCard.tsx` and Events services | Review/edit/approve/dismiss real proposals | Reuse this card and existing domain endpoints for action review; do not replace it with generic LLM approval buttons. |
| `backend/app/langchain/graphs/event_confirmation.py` | PostgreSQL-backed LangGraph interrupt/resume for Events | Reuse the established workflow boundary; harden recovery and expose pending review through existing proposal data. |
| `frontend/src/components/content/MarkdownContent.tsx`, `CodeBlock.tsx` | Shared chat/Library Markdown, math, GFM and code blocks; no Mermaid routing | Add Mermaid routing and a shared directive plugin in this rendering stack. Keep citations in their existing feature adapter. |
| `frontend/src/lib/markdownPlainText.ts`, chat `CopyResponse.tsx` | AST-based readable clipboard output | Teach the existing parser about supported directives; keep code payloads exact. |
| `AssessmentGenerationCard.tsx`, `MCQAssessment.tsx`, `CalibrationAssessment.tsx` | Three local progress bar implementations | Extract one accessible `ProgressBar` primitive and migrate these consumers before adding model-authored progress. |
| Chat `ContextualActions.tsx` | Typed “Practice this material” action using validated references | Reuse for a small set of useful follow-up actions; avoid creating a second action system. |
| `frontend/src/pages/SettingsPage.tsx`, shared Select, theme preference persistence pattern | Existing Profile & preferences settings and browser-local appearance preferences | Add Chat appearance here; reuse validated storage, immediate application and cross-tab sync patterns without coupling chat preferences to theme state. |
| `frontend/src/styles/global.css`, `ChatMessage.tsx`, chat composer | Global Inter-first fallback declaration, shared Markdown sizing and existing mobile composer rules | Actually bundle the chosen font, then scope its use and size tokens to main-chat content. Avoid global typography changes. |

## 2. Contracts and persistence

### Choice options with attached input

Extend the chat choice option contract with an optional `input` definition. A new chat option model can extend the shared `ChoiceOption`; assessments continue using the existing option type. Share bounded text-field definitions with the later form card.

Illustrative model tool arguments:

```json
{
  "kind": "single_choice",
  "question": "Which concept would you like to explore?",
  "options": [
    {"id": "react", "label": "React rendering and reconciliation"},
    {
      "id": "custom_topic",
      "label": "I'll write my own topic",
      "input": {
        "kind": "short_text",
        "label": "Your topic",
        "placeholder": "For example, database indexes",
        "required": true,
        "max_length": 300
      }
    }
  ]
}
```

The server continues assigning the interaction UUID. `custom_topic` has no reserved meaning: the `input` definition controls rendering. Explicitly distinguish a free-text alternative from an ordinary “Other” label. Multiple-choice cards may attach inputs too, but require values only for selected options and reject submitted values for unselected or unknown options.

Extend the existing response with an optional `option_inputs` mapping; old responses default to an empty mapping:

```json
{
  "message_id": "<existing assistant message UUID>",
  "interaction_id": "<server interaction UUID>",
  "selected": ["custom_topic"],
  "option_inputs": {"custom_topic": "Database indexes"}
}
```

Pydantic validates bounded shapes, input kinds, IDs and text lengths. The existing resolver checks the submitted values against the stored card, validates conditional requirements, and constructs canonical user content from server-owned labels plus the user's actual text. Never accept client-supplied labels, field definitions, action authority or workflow identifiers as authoritative.

Recalculate the existing 4,000-character canonical-message budget to include entered text and all selected fields. Validate total card/answer limits as well as individual field limits. Trim surrounding whitespace for requiredness; preserve Unicode, internal whitespace and the original user value where needed for provenance. User-entered text remains untrusted conversation data.

### Additional input kinds

Use a discriminated union for new interaction kinds, with legacy `single_choice` and `multiple_choice` cards still accepted unchanged. Add `text_input` and `form` kinds using a shared bounded field contract. Defaults for omitted new fields must preserve old stored cards and pending requests. Version new contracts explicitly where necessary; do not rewrite historical metadata.

| Kind | Native control | First use |
|---|---|---|
| Choice with input | Existing options plus conditional Input/Textarea | Custom topic, custom preference, “Other” with detail |
| `text_input` | Labeled Input or Textarea | A topic, short explanation or required missing detail |
| `form` | At most four fields using existing Input/Textarea/Select primitives | Topic + available study minutes + preferred explanation depth |
| Domain review | Existing proposal/editor card | Review, edit or dismiss a proposed event |

Start forms with short text, long text, bounded numbers and selections. Reuse current date/time controls inside Events rather than creating a generic date framework. Fixed field kinds and bounds only: no arbitrary model-generated validation expressions, HTML, scripts, endpoint URLs or component names.

Keep `present_choices` backward compatible; introduce one `request_input` tool for the text/form union. Reuse the existing tool factory and three-card ceiling. Prefer one concise card per decision; the ceiling is a safety bound, not a target.

### Submission, drafts and history

1. Render from validated assistant metadata using a small explicit kind-to-component dispatcher in the existing chat interaction path.
2. Reuse ChatStore's durable `client_turn_id`, pending request storage, revisions, owner fences and retry handling.
3. Extend the current atomic transaction to save selected IDs, entered values, canonical user content and receipt together.
4. Reuse the same ID and payload after an unknown network result. If generation fails after answer acceptance, retry generation without answering again.
5. Reconcile cards from server receipts following refresh, reconnect and another tab's submission. A saved answer is read-only and includes the actual entered topic/field values.
6. Keep unsubmitted field drafts owner/conversation/message/interaction scoped using the existing chat state conventions. Retain them through component rerenders and rejected/failed submissions; clear on logout/account switch, deletion or authoritative acceptance. Initial scope does not promise unsent drafts survive a full reload; accepted answers and pending durable sends must survive it.
7. Switching options may retain an unsent local draft, but hidden values must never be submitted. Submitted values come only from currently active fields.

No new generic interaction tables are expected: extend existing message metadata. Verify actual query/recovery needs before proposing a migration.

## 3. Central UI usage instructions and model behavior

Keep the model's UI usage guidance in one proposed `backend/app/langchain/prompts/chat_ui.py`, registered and composed through the existing `prompts/registry.py`. Include it once per relevant chat model invocation, including follow-up tool rounds and response-edit paths that author chat content. Keep only a short reference/composition hook in the core chat prompt. Reuse the registry's versioning and caching identities.

Move overlapping UI usage guidance out of `chat.py` and related prompts when the new shared module is introduced. Tool descriptions should explain arguments, prerequisites and outcomes; domain prompts should retain only domain-specific rules such as assessment answer privacy or event authorization. Neither should duplicate the full selection, styling and formatting policy. Schemas remain the executable contract; the shared module owns when and how the model uses those capabilities.

The tables below define that central policy. Later sections specify implementation details rather than separate prompt instructions.

| Situation | Expected behavior |
|---|---|
| A material clarification has a small useful set of answers | Present clickable choices, including an input-capable alternative where appropriate. |
| One missing free-text detail prevents continuation | Show an inline text card with a clear label and submit action. |
| Two to four related details are needed together | Use a compact form rather than several back-and-forth questions. |
| Existing permission or review rules require a decision | Surface the domain's real pending proposal and review controls. |
| User asks for practice | Continue using existing assessment tools/cards, preserving question type/count and private keys. |
| Request is already clear | Complete it directly; interactive UI should not introduce an unnecessary decision. |
| User requests prose, paper, code or a specific format | Honor it. Do not force an interactive card. |

| Presentation/action | Central usage rule |
|---|---|
| Custom-topic alternative | Attach a real input definition; never promise typing through a label alone. |
| User decisions | Call the appropriate tool before claiming a card is available, wait for the user and never submit on their behalf. |
| Mermaid | Use a small diagram when flow, interaction, hierarchy, state or relationships become clearer. Use a `mermaid` fence, an accessible title/description and a brief prose explanation; omit model-authored configuration. |
| Color | Prefer semantic tones on short meaningful phrases. Use custom hex sparingly; avoid decorative paragraphs and color as the only meaning. |
| Progress | Use an explicit progress directive only for supported counts/measurements. Preserve exact values; never invent mastery, certainty, live execution progress or a missing total. Ordinary percentages stay prose. |
| Hint/callout | Use when it improves learning or highlights a useful point; never expose unreleased private answers. |
| Follow-up actions | Offer at most one or two contextual actions backed by supported intents/references; omit when competing with required input. |
| Typography | Application settings own font and size. The model does not emit font families, text sizes or CSS. |

Keep concise syntax examples for custom-topic input, compact form, review, Mermaid, color and measured progress beside these rules in the shared module. Maintain one example fixture corpus used by prompt/contract tests rather than copying large examples between prompts. Document the model-facing contract in `docs/chat-interactions.md`; other engineering documents should link to it for usage policy.

Improve capability discovery and dispatch alongside this shared prompt. A prompt alone will not fix tools that are unavailable during binding or rejected by execution. Scope the included capabilities to those actually enabled so the model cannot promise unavailable UI.

Ordinary topic choices are durable chat answers and do not need graph interrupts. True human-in-the-loop actions require persisted workflow state and a real resume operation.

## 4. LangGraph human-in-the-loop integration

Preserve the Events proposal service as the authority for authorization and business commits. The current `EventConfirmationGraph.decide()` creates/checks an interrupt when deciding; this is not evidence that every displayed proposal already has a paused graph. Make pending proposal state and graph state recovery agree at the actual review boundary.

| Requirement | Implementation direction |
|---|---|
| Durable review | Persist the proposal first; establish/reconcile its checkpointed review state before exposing it as resumable. Reuse the existing checkpointer and owner/proposal workflow thread identity. |
| Native pending UI | Render the existing `EventProposalCard`, including its editor and approve/dismiss actions. Restore it from canonical proposal state on reopen. |
| Valid resume | Domain service checks ownership, pending state, revision, allowed decision and workflow version before resuming the matching interrupt. |
| Replay safety | Treat answer/decision acceptance, checkpoint resume and domain mutation as separate recoverable steps; do not assume the checkpoint and business write share a transaction. Reconcile interrupted steps using existing proposal states and operation identities. |
| Node re-execution | Keep pre-interrupt effects idempotent, or move them after review/into their existing durable operations. |
| Changed proposal | Revalidate edited details; stale decisions cannot authorize a different revision or action. |
| Recovery | Recover after restart, lost response, duplicate click, concurrent tabs, dismissal and unsupported workflow version without repeating the mutation. |
| Chat continuation | Do not fabricate an ordinary choice answer for a domain decision. If continuation is needed, consume a verified domain receipt through existing turn handling. |

Only extract a shared workflow-review adapter once a second actual workflow needs it. Do not add a general approval engine or move assessment grading into this system. A confirmation never becomes learner mastery evidence.

LangGraph requires checkpointing for interrupts, resumes via `Command`, and re-executes the interrupted node from its beginning. These properties drive the recovery requirements above. [Official interrupt reference](https://reference.langchain.com/python/langgraph/types/interrupt).

## 5. Full frontend Mermaid support

Add the maintained `mermaid` package, resolved and locked to a compatible supported release at implementation time. Route only fenced blocks with language `mermaid` through a lazy-loaded diagram component inside the shared `MarkdownContent` stack; preserve the exact original source and existing code behavior for all other languages.

| Area | Planned behavior |
|---|---|
| Rendering | Local rendering through Mermaid's API, explicit initialization, `startOnLoad: false`; unique instance IDs prevent SVG collisions. |
| Supported diagrams | Support stable types available in the chosen version. Acceptance fixtures cover flowchart, sequence, state, class, ER, mindmap, timeline and Gantt. Invalid/unsupported syntax falls back locally. |
| Diagram frame | Responsive figure with horizontal overflow for wide diagrams, readable labels and a compact toolbar: diagram/source toggle, exact source copy, expand in existing Dialog, and local SVG download. |
| Theme | Derive theme values from existing Light/Dark/System tokens. Invalidate rendering on resolved theme changes; coordinate renders so shared Mermaid initialization cannot race between mounted diagrams. |
| Accessibility | Accessible name/description, visible textual explanation, keyboard-accessible toolbar, focus return from expanded view, high-contrast/reduced-motion behavior. Encourage `accTitle`/`accDescr` in model output. |
| Safety | App-owned strict configuration, HTML labels disabled, no click callbacks, external resources or executable links. Reject diagram-supplied init/frontmatter configuration and unsafe style/resource features. Sanitize generated SVG at the insertion/export boundary using a maintained SVG-capable sanitizer. |
| Bounded work | Set explicit source/edge limits, cap per-message diagrams, serialize or bound render work and cache a bounded set by source/theme/version. Test expensive input; use an isolated worker/iframe where supported if real cancellation is needed, since a timeout cannot preempt synchronous main-thread work. |
| Failure | Preserve the answer and show a concise diagram-unavailable state with source access. Do not repeatedly regenerate or expose internal parser errors. |
| Chat behavior | Respect the current completed-answer rendering and activity model. Reserve a local loading surface while the lazy diagram renderer loads; do not reintroduce token-by-token Markdown rendering or reset scroll/focus on completion. |

Mermaid's strict mode disables click functionality and encodes label HTML; it is a baseline, supplemented by the application constraints above. [Official usage/security configuration](https://mermaid.js.org/config/usage). Accessible diagram metadata uses `accTitle` and `accDescr`. [Official accessibility guidance](https://mermaid.js.org/config/accessibility). Theme configuration must remain application-owned. [Official theming](https://mermaid.js.org/config/theming.html).

Model usage and syntax examples belong in the shared UI prompt described in section 3.

## 6. Inline colored text

Use `remark-directive`, which fits the existing unified/remark pipeline, with an application-owned allowlisted transform. It supplies directive parsing, not permission to render arbitrary attributes. [Official remark-directive project](https://github.com/remarkjs/remark-directive).

Proposed syntax:

```text
:color[Success]{tone="success"}
:color[Needs another attempt]{tone="danger"}
:color[Failure is a reminder]{hex="#F54927"}
```

Prefer this explicit grammar over hash delimiters: it distinguishes text from headings, hex literals and code, and can be parsed as Markdown nodes without whole-message regular-expression replacement.

| Rule | Implementation |
|---|---|
| Semantic colors first | `success`, `warning`, `danger`, `info` and `accent` resolve to shared theme tokens. Named-color aliases such as green/red may map to those tokens. |
| Custom colors | Accept only a validated six-digit hex value. No CSS strings, URLs, variables, alpha or arbitrary style properties. |
| Contrast | Adjust custom colors to a readable foreground on the actual surface, or fall back to the semantic/accent foreground. Reuse the existing UI contrast-check approach; add explicit tests for semantic colors too. |
| Meaning | Keep visible words such as “Success” or “Needs review”; color never carries the only meaning. |
| Restraint | Enforce the central usage guidance in section 3; keep examples and selection policy in that shared prompt. |
| Parser boundaries | Only supported directive nodes become spans. Do not interpret directive-like text in code, math, URLs or escaped literal examples. Reject conflicting/unknown attributes. |
| Compatibility | No arbitrary HTML rendering. Malformed/unknown markup remains readable literal text; valid unsupported colors retain their text without unsafe styling. |
| Clipboard | Existing `markdownPlainText` returns the phrase with formatting removed. Exact code-copy behavior stays unchanged. |

Custom model-specified foreground color is a narrow, documented exception to the frontend's semantic-token styling rule, handled in one component. It must not spread raw palette values throughout the application.

## 7. Dedicated value/progress bar

Extract `ProgressBar` from the existing assessment/calibration implementations into `components/ui/`. Keep feature-specific labels, data loading and status decisions with their current callers. Preserve those callers' current value semantics.

Prefer structured `present_visuals` tool arguments so the model does not need presentation markup. Supply a bounded list of labeled values/scales and optional explanatory notes. Compare concepts on a common scale and label subjective difficulty/ratings as illustrative or estimated. These are static visuals. Reuse the same primitive for existing domain-owned progress displays without introducing new live tracking.

Optional block syntax, parsed with the same directive infrastructure:

```text
::bar{label="Estimated difficulty" value="3" max="5" unit="points"}
```

| Concern | Decision |
|---|---|
| Exactness | Display `3 / 5 questions · 60%` beside the bar. Preserve original counts; define sensible decimal precision for nonintegral percentages. |
| Validation | Require a nonempty bounded label and finite numbers, `max > 0`, `0 <= value <= max`; bounded plain-text unit. Invalid directives do not render a misleading bar. |
| Meaning | Render only explicit progress directives or actual domain progress data. `60%`, scores and statistics in prose remain text. |
| Truthfulness | Model-authored bars are static snapshots of provided/measured quantities. They cannot claim unsupported mastery, certainty or background completion. |
| Live state | Existing generation/quiz/calibration data drives live bars. Continue using current subscriptions/polling; no new polling store and no fake animated percentages. |
| Unknown total | Existing live workflows may use an indeterminate state with a meaningful label; do not invent a percentage. The model directive initially requires a known total. |
| Design | Sleek rounded track, modest height, accent/semantic fill, exact count text, accessible name and `aria-valuenow/min/max`. Short transitions respect reduced motion. |
| Copy | Convert to readable `Practice completed: 3 / 5 questions (60%)` through the existing plain-text parser. |

Presentation directives are validated AST data, not action tools. Add a small Pydantic `ProgressSpec`/`ColorSpec` only where backend structured generation consumes them; do not imply Pydantic validates free-form Markdown unless an actual parser supplies those models. Frontend runtime validation is mandatory. Use shared golden examples for cross-language parity if backend validation is introduced.

## 8. Small useful additions

Include these after the core input, Mermaid, color and progress work. Reuse the same rendering/plugin and primitive boundaries.

| Addition | Value | Reuse and limits |
|---|---|---|
| Hint / solution / explanation disclosure | Lets learners reveal help without cluttering an answer | Existing native disclosure styling; small `details` directive. Do not hide private assessment answers in the DOM or metadata before release. |
| Tip / caution / key idea callout | Makes a short important point easy to find | Existing Card and semantic text styles; bounded `callout` directive using the same plugin. Never auto-generate warning panels from tool failures. |
| Contextual follow-up actions | Useful “Explain with an example” or “Practice this material” actions | Extend `ContextualActions.tsx` with a few typed intents and existing validated references. No arbitrary URLs, endpoints or hidden auto-execution. |

Follow the central suggestion policy in section 3. Defer generic dashboards, arbitrary model-authored layouts, drag-and-drop builders and a large visualization library.

## 9. Main-chat typography and font-size settings

Use self-hosted **Inter** with a comfortable reading size, regular 400-weight prose, restrained 500–600-weight emphasis and approximately 1.65–1.75 line height. Inter is designed for screen readability, including a tall lowercase x-height. [Official font project](https://github.com/rsms/inter). Validate the final result visually against real long chat responses before finalizing spacing.

The current CSS already lists `Inter` first globally, but the frontend source inspected here does not include a font-face declaration or bundled Inter asset. Listing a family does not ensure that users see it. Bundle licensed WOFF2 assets with the frontend, including required normal/italic weights or variable equivalents, and use a distinct chat font-face name such as `Mentra Chat Inter`. Apply that alias only to the main-chat scope so loading the font does not inadvertently alter the rest of the app. Keep the font license with the assets; use `font-display: swap` and sensible system fallbacks. Verify the actual computed font in browser acceptance.

| Setting/area | Planned behavior |
|---|---|
| Location | Add a compact **Chat appearance** section to Settings → Profile & preferences using the existing settings layout and shared Select. Label the control **Chat font size** and state that it applies to main chat only. |
| Sizes | **Small: 15px**, **Medium: 16px (default)**, **Large: 18px** at the standard browser root size, implemented as relative units. Missing/invalid saved values resolve to Medium. Preserve browser zoom and user accessibility scaling. |
| Preview | Show one short sample of a user message and assistant response inside Settings; size changes apply immediately, with no page reload or model call. |
| Scope | Main-chat user and assistant prose, Markdown lists/tables, inline code, inline interactive question labels and entered text, and the main composer text. Heading sizes remain proportional to the selected base. |
| Stable controls | Retain compact toolbar/button/status text and shared control dimensions. Do not scale the application root, sidebar, chat list, navigation, settings, Library or standalone assessment pages. |
| Specialized content | Fenced code retains the established monospace font and code sizing. KaTeX retains its math fonts and scales relative to prose. Mermaid uses its app-owned diagram typography. Embedded assessment/editor components retain domain layout and sizing unless a deliberate chat-specific text token is supported. |
| Mobile composer | Retain the existing minimum 16px composer text on phones even with Small selected, avoiding focus zoom and preserving current composer geometry. |
| Tokens | Define chat-specific family, base-size and line-height tokens at the conversation/composer scope. Extend existing Markdown styles through a scoped chat override; shared MarkdownContent used elsewhere must keep its current typography. |
| Persistence | Reuse the browser-local appearance preference pattern from ThemeProvider with a validated `small | medium | large` value, guarded storage access and cross-tab updates. Store only this nonsensitive appearance choice; in-memory fallback remains usable if storage is blocked. Treat it as a device/browser setting in this scope, with no profile API or migration. |
| Scroll and focus | Reuse existing chat resize/scroll anchoring. Preserve the reading position on size change, follow growth only when already following the bottom, and preserve text drafts, selections and keyboard focus. |

Do not add a font picker in this scope: select one clear typeface and provide the requested size control. Font and size are deterministic frontend presentation settings and must not be passed to the LLM as behavioral instructions.

## 10. File-level implementation sequence

| Phase | Modify/generalize existing resources | Add only when required | Exit condition |
|---|---|---|---|
| 1. Fix custom-topic entry | Chat choice schemas/resolver, ChoiceCard, interaction types, ChatStore, durable receipt transaction | Small shared text-field contract | Screenshot scenario works end to end; old choices and graded MCQs retain their behavior. |
| 2. Expand native inputs | Tool factory, capability catalog/selection, request/response unions, chat renderer and prompt | Text/form card; shared frame once at least two consumers use it | Text and compact form input survive acceptance/retry/reopen with canonical values. |
| 3. Complete workflow review | Existing EventConfirmationGraph, proposal service/repository, EventProposalCard and recovery | Narrow adapter only if a second workflow is implemented | Pause, review, resume and recovery do not repeat domain effects. |
| 4. Share progress | Existing generation, MCQ and calibration displays | One ProgressBar primitive | Existing progress remains correct and accessible across all consumers. |
| 5. Rich Markdown | MarkdownContent, CodeBlock routing, markdownPlainText, styles and theme checks | MermaidDiagram, narrow directive transform/components; Mermaid, remark-directive and SVG sanitizer dependencies | Diagrams, color, progress, copy and graceful failures work in chat and Library. |
| 6. Chat appearance | SettingsPage, shared Select, current appearance persistence patterns, chat/composer scoped CSS and Markdown overrides | Bundled licensed Inter assets; small chat-size preference helper/component | Medium is default; sizes persist and affect only main-chat typography. |
| 7. Useful additions and consolidated guidance | Existing disclosures, Card, ContextualActions, prompt registry and documentation; remove duplicated UI usage instructions | Minimal callout/disclosure adapters; one shared `chat_ui.py` prompt module | Additions are useful without clutter; one composed UI policy guides actual model behavior. |

Update `docs/chat-interactions.md`, frontend/backend standards and relevant LangChain documentation for the final contracts. Keep schema examples, prompt examples, types and test fixtures consistent. Preserve sidebar/composer placement, shared controls and current responsive geometry.

## 11. Verification and acceptance

These are required implementation checks, not claims that tests have run for this planning task.

Additional implementation requirement: native controls must render with minimal
overhead; completed components must not rerender on unrelated UI updates. Plain
text should bypass rich parsing where safe. Heavy diagrams must be lazy and cannot
gate surrounding text. Measure input latency and actual component renders with a
200-message chat, including unchanged refreshes and a real metadata update; report
first-use diagram costs honestly rather than claiming parity with plain text.

| Area | Required evidence |
|---|---|
| Screenshot regression | Select custom topic → input opens in the card → blank submit blocked → type a topic → submit once → exact topic reaches model context → accepted topic survives refresh. |
| Conditional fields | Normal options need no text; switching away excludes hidden text; unknown field IDs, unselected inputs, whitespace-only required values and over-limit totals are rejected. Include multilingual text and mobile keyboard input. |
| Compatibility | Existing stored choices, legacy response payloads, pending durable sends, MCQ validation/grading, written assessments, source citations, math and code remain correct. |
| Durable submissions | Isolated real PostgreSQL checks for ownership, message/conversation mismatch, concurrent tabs, changed duplicate payloads, lost acknowledgment and failed-generation retry. Accepted values and canonical text stay atomic. |
| Workflow review | Real checkpoint/proposal persistence across restart; approve/dismiss/edit, stale revision, unknown workflow version and failures between acceptance/resume/business commit. No duplicate event writes. |
| Mermaid | Stable diagram family fixtures, multiple diagrams, source copy/download, theme switch during rendering, invalid syntax, excessive input, unsafe SVG/config/links, lazy-load failure, small screens, dialog focus return and restored chat scroll. |
| Formatting | Directive escaping, malformed/unknown attributes, nesting, ordinary percentages, hex examples, code/math/link boundaries, citation coexistence, contrast, plain-text copy and historical messages. |
| Shared progress | Zero, complete, fractional, unknown-total live state, invalid/nonfinite/out-of-range values and accessible announcements. Confirm model snapshots never subscribe to fabricated live progress. |
| UI | Keyboard/screen-reader names, associated errors, active-field focus only following user selection, Light/Dark/System, forced colors, reduced motion, 320–375px layouts and no composer/sidebar regressions. |
| Chat typography/settings | Verify the bundled font actually loads; Medium default, all three sizes, immediate preview/application, refresh, cross-tab sync, invalid/blocked storage and browser zoom. Compare before/after outside-chat typography to prove it is unchanged. Cover prose/headings/tables/inputs, code/math exceptions, mobile composer minimum size, long responses and stable scroll/focus. |
| Central UI policy | Prompt assembly includes the versioned UI module exactly once across initial/tool/response-edit chat paths and advertises only supported capabilities. Review existing prompts for duplicated/conflicting UI instructions; test behavior using the shared examples. |
| Real model behavior | Use the configured provider with synthetic requests for custom topics, forms, useful diagrams, measured progress and plain requests needing no UI. Validate returned Pydantic tool arguments, actual execution and final rendering; do not judge only schema validity or deterministic fixtures. |
| Build/checks | Frontend production build, `check:theme`, `check:ui`, focused backend interaction/workflow tests and browser suites. Extend `backend/tests/test_chat_interactions.py` and `frontend/tests/chat-interactions.spec.ts`; use existing event and rendering suites for related paths. |

Track model selection quality with expected behaviors, including false positives. The goal is more appropriate UI, not an interaction quota on every response. Log card kind, validation outcome and recovery errors without logging sensitive entered text unnecessarily.

## 12. Rollout, rollback and completion

1. Keep old payloads readable before enabling new generation. Deploy backend readers/contracts and frontend renderers in compatible order; advertise only supported formatting/input capabilities to the model. Refresh prompt versions/cache identities when the contract changes.
2. Use the existing configuration approach for narrow generation switches if needed. Disabling generation must leave rendering and recovery available for already-saved cards and pending workflows.
3. Rebuild/recreate frontend and backend together when validating the local stack; check actual API/UI compatibility, not only container health. Deployment is a later implementation task, outside this plan-only request.
4. Roll back new tool/prompt exposure first if validation or model selection regresses. Keep backward-compatible readers and saved data; workflow recovery continues through domain services. A rollback to a binary that cannot read new payloads needs an explicit compatibility step.
5. Keep model-authored visual syntax readable when unsupported. Renderer failure must not lose the surrounding answer, user input or accepted action receipt.
6. Remove superseded local progress markup and duplicate rendering helpers only after all known consumers are migrated. Keep legacy card readers; do not delete historical interaction data or assessment provenance.

Complete when the custom-topic example works, native input and actual workflow review are reliable, Mermaid is fully integrated, restrained colors and explicit progress render correctly, chat-only typography and size settings work with Medium as the default, UI usage guidance is centrally composed, and the verification above records what passed and what remains unverified.
