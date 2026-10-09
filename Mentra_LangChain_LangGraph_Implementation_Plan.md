# Mentra LangChain + LangGraph Module — Full Implementation Plan

**Status:** Implementation resumed at the user's request on 2026-10-09. The live tracker distinguishes wired code, verified checks and remaining scope. End-to-end completion has not been achieved.
**Audience:** Human developers and AI coding agents
**Scope:** LangChain + LangGraph orchestration module
**Relationship:** `app.langchain` is the central AI orchestration point for all Mentra capabilities. It decides what runs, in which order, with which context, permissions, budgets and recovery policy. Domain services retain their canonical data and deterministic business rules.

## UI consistency follow-up (2026-10-10)

The six requested frontend fixes are wired: shared FileInput hides native chooser chrome; the full event agenda and proposals live in Progress/Events; all selection fields use the shared portaled Select; dropdowns/account menus/dialogs use central popover/scrim tokens; interactive binary controls use Toggle; shared page/field typography and spacing align across Library, Progress, Assessments, Notifications and Settings. Existing event URLs redirect without losing event IDs. Account-menu focus, dropdown keyboard/typeahead, multi-selection, viewport anchoring and cancellation are handled centrally. Verified: production Docker build and theme checks passed. The full browser regression passed 49/52; the three failing cases were a short-screen dropdown scroll bug (fixed) and ambiguous test locators (corrected). The four-case affected/mobile recheck passed, covering all 52 unique cases across both runs. Keyboard/typeahead, multi-selection, portals, file chooser interaction, legacy event redirect, switches and mobile Light/Dark screenshots were verified. Screenshots reviewed visually. Fresh frontend container rebuilt from the completed source and healthy; backend and workers running. Logs: `.ui-system-full-browser.log`, `.ui-system-mobile-recheck.log`, `.ui-system-final-docker-build.log`, `.ui-system-theme.log`.

## Live implementation progress

Updated 2026-10-09 during implementation. **In progress** means code is being written and is not yet verified. **Implemented** means wired code exists; **Verified** requires the listed checks to pass. The full plan remains the completion contract.

| Workstream | Status | Current evidence / next check |
| --- | --- | --- |
| Central facade and existing chat/RAG/history integration | Verified | Added `OrchestrationService`, startup injection and compatibility adapter; regression tests pending |
| Learner context and recommendation tools in chat | Implemented | Public learner packet and read tools wired; budgets/failure tests pending |
| Typed tool announcements and durable activity stream | Verified | Pydantic schemas, bounded PostgreSQL journal, SSE endpoint and React activity UI added; ordering/reconnect/owner tests pending |
| Chat attachments through Documents/Vision/OCR | Verified | Owned upload, composer, transcript metadata and extraction wired; text-file browser flow passed; real OCR/image and race coverage still required |
| Explicit Add to Library on uploaded user-message file | Verified | Independent card action with context selection; browser save/reload/Library publication passed |
| RAG pre-extracted ingestion | Verified | Existing RAG worker reuses versioned extracted blocks; parser/detector-not-called and provenance test passed; broader lifecycle review pending |
| Events AI admission/proposals and confirmation graph | Implemented | Owned tools, durable proposals, strict checkpoint schema, minimal interrupt graph, APIs/cards and Progress recovery added. Focused restart/concurrency/deletion tests and proposal browser acceptance passed; admission refinement underway |
| Notifications/reminder worker and inbox | Verified | Generic domain, owner-locked delivery, lifetime receipts, inbox/preferences/sync API, migration, worker, frontend inbox/badge/settings added. Focused backend suite passed; browser acceptance remains pending |
| Full assessments, grading, granular calibration, OCR correction | Implemented | Canonical records, protected rubrics, orchestration generation/grading, durable worker, transcription confirmation, correction history and atomic learner updates added; focused domain and browser acceptance passed; final review underway |
| Durable chat evidence, routing/profile refinements, token streaming | Implemented | Validated allocation, selective profile/learner/RAG reads, assistant text deltas and durable demonstration jobs added; acceptance/recovery checks underway |
| Progress/Events/Learning/Settings frontend | Verified | Learning public-contract view, recommendation links, proposal recovery, Events, Notifications and assessment answer sheets wired; TypeScript and new browser workflows passed; full browser regression pending |
| Graph dependency/restart/cleanup gate | Verified | Frozen-snapshot Python 3.12 rehearsal passed interrupt/restart/resume, all saver-table cleanup and all 343 backend tests. Tested dependencies pinned in requirements; graph application integration underway |
| Full regression, migration rehearsal, image/browser checks | Verified | Rebuilt Docker Python 3.12: 357 tests passed, including migrations/schema parity. All 49 browser cases passed across full run and affected recheck. Real image OCR and Nginx smoke checks passed; no application database migrated. |

Current verification checkpoint (2026-10-09, supersedes pending checks in older tracker evidence): images rebuilt as `mentra-backend:latest` (`eab904ab4d5e`) and `mentra-frontend:latest` (`d52fd1e50fc0`). All 49 browser cases passed across the initial 43/49 run and the 13/13 affected-suite recheck. Restored the Profile & preferences tab, removed stale memory rows during filtering, and adapted code-display mocks to explicitly exercise synchronous compatibility; orchestration browser cases exercise async turns. Streaming tests passed 2/2, event admission/proposal tests 8/8 and durable evidence job tests 2/2. Real image OCR and frontend image Nginx smoke tests passed. Final rebuilt Docker Python 3.12 full regression passed **357 tests** in 372.489 seconds (`.orchestration-final-runtime.log`), including migration rehearsal and schema parity. Windows sandbox full run encountered temporary-directory access failures and is not a passing result. Removed eight obsolete/testing Mentra containers and all three named verification images. Only the rebuilt current Mentra images remain. Database volumes and unrelated n8n remain intact.

Remaining completion scope: native assessment chat tools and native iterative RAG tool/citation integration; adaptive/mock-exam flows; model-assisted ambiguous routing and broader profile evidence; automatic Events semantic deduplication and broader admission acceptance; broader evidence extraction/recovery acceptance. Current implementation is not completion of every requirement in Phases 0-36. Real provider quality and handwriting accuracy are not established by deterministic fixtures; unknown paper transcription confidence requires explicit user confirmation.

New requirements incorporated during implementation: a chat upload must use Documents and Vision through orchestration; each uploaded file shown in the user's message must have an independent **Add to Library** option; that action must reuse already extracted content through RAG and skip document reading/OCR. Choosing not to save requires no action and must not trigger automatic Library admission.

Historical stop checkpoint (superseded by the live tracker, 2026-10-09): current worktree reverified and edits preserved, uncommitted. Latest focused Notifications/Events/History/Orchestration suite passed **85 tests** (`.orchestration-domain-tests.log`); earlier focused suite passed 96 and chat browser suite passed 8. Latest attachment browser acceptance passed after adding inline context creation and cancellation guards. Events browser test encountered an inaccessible exact reminder selector; explicit accessible label added, **not rerun**. TypeScript passed before the latest small attachment/editor changes; `git diff --check` passed at stop. Tool activity now shares step identity across planned/running/completed and carries tool-call identity. Candidate dependency suite initially had migration-test failures (fixed), then a tool-loop failure during live-source edits; frozen-snapshot rerun was still running when the user requested stopping and is not claimed as passed. Production graph dependencies remain unchanged. No application database migration or deployment performed. Remaining scope includes Events AI/proposals/graph, assessments/grading/OCR confirmation, durable evidence, selective routing/profile/token streaming, Progress/Learning, and final full verification.

Historical resume audit (superseded by the live tracker): worktree changes retained; Python compilation and frontend TypeScript checks pass. Fresh focused run passed 96/96 tests; browser run passed 8/8 after fixing long-history reconciliation. The candidate-dependency full run executed 338 tests with nine errors traced to a historical migration test comparing newer schema tables after downgrade; comparison and guaranteed schema restoration corrected, rerun pending. Logs: `.orchestration-focused-tests.log`, `.orchestration-browser.log`, `.orchestration-frontend-build.log`, `.orchestration-graph-gate.log`, `.orchestration-graph-regressions.log`. Only the isolated `mentra-orchestration-test-20261009` database container has been used; no application migration/deployment performed.

Read the **Current Codebase Inventory and Migration Boundary** for the verified baseline, Phases 0-29 for the preserved core requirements, and Phases 30-36 for the complete integration and delivery specification. Phase 34 includes the required backend activity contract and frontend implementation. Phase 36 maps the original plan and historical TDD requirements to this revision.

---

# 1. Objective

Implement a reusable orchestration module that acts as Mentra's AI-facing coordination layer.

Every AI-assisted workflow belongs behind this coordination boundary. Manual CRUD, authentication, deterministic parsing, database transactions and reminder delivery do not require a model invocation. Orchestration decides when a module is needed; domain services enforce whether its operation is valid. Background workers execute durable domain jobs without routing every job through chat.

The module is responsible for:

- interacting with configured LLM providers;
- constructing prompts and model context;
- exposing Mentra capabilities as typed tools;
- retrieving compact learner context from the Learner Engine;
- requesting contextual material from RAG;
- routing requests to appropriate workflows;
- coordinating multi-step tutoring and assessment flows;
- validating structured model outputs;
- streaming responses to the application layer;
- publishing validated activity and tool announcements before each visible action, including deterministic document/learner operations;
- coordinating history, personal memory, profile, Events, Notifications, document reading and their confirmation/recovery flows;
- managing short-lived workflow state;
- handling retries, timeouts, tool failures, and fallbacks;
- using LangGraph where workflows require explicit state, branching, resumability, or human confirmation.

Core rule:

> **LangChain/LangGraph orchestrates Mentra's modules. It does not become the owner of their data or business rules.**

---

# 2. Architectural Role

```text
Frontend / authenticated APIs / durable workflow jobs
    -> LangChain + LangGraph orchestration
       -> Chat: canonical turns, attempts, publication and recovery
       -> Learner: contexts, concepts, evidence, mastery and recommendations
       -> Student Profile: details, broad estimates and onboarding
       -> RAG / Library: ingestion jobs, retrieval and provenance
       -> Documents -> Vision: extraction and OCR
       -> History Management: canonical history reads and personal memory
          -> Events: lifecycle, dates, proposals and reminder eligibility
       -> Notifications: reusable inbox/delivery (implemented)
       -> Assessments: canonical questions, attempts and grades (implemented)
       -> MentraLLM -> configured provider
```

Preferred dependency direction:

```text
LangChain/LangGraph
       ↓
domain service interfaces
       ↓
domain implementations
```

Avoid domain modules depending on LangChain for their core business logic.

The Learner Engine may expose functions that LangChain wraps as tools, but learner logic itself remains framework-independent.

---

# 3. LangChain vs LangGraph Responsibilities

Treat LangChain and LangGraph as one Mentra module, but use each selectively.

## Use LangChain for

- provider-independent chat-model initialization;
- model invocation and streaming;
- prompt/message construction;
- structured output;
- tool definitions and binding;
- retriever adapters where useful;
- output parsing;
- ordinary short model/tool interactions.

## Use LangGraph for

- workflows with multiple explicit stages;
- deterministic + LLM mixed execution;
- conditional branching;
- resumable workflows;
- confirmation/human-in-the-loop gates;
- workflows where state must survive multiple nodes;
- complex tutoring turns involving learner + RAG + evidence extraction.

## Do not use LangGraph merely because it exists

A single model operation such as conversation-title generation should remain a simple model call.

A flow such as this is a good graph candidate:

```text
student question
    ↓
resolve intent/context
    ↓
load learner context
    ↓
retrieve RAG
    ↓
generate response
    ↓
extract learning evidence
    ↓
validate/resolve concepts
    ↓
submit evidence
```

---

# 4. Recommended Module Structure

Adapt naming to existing repository conventions.

Extend `app/langchain/model_factory.py`, `llm.py`, `prompts/`, `chat_service.py`, `profile_evaluator.py`, `learner_tools.py`, `rag_tools.py` and `history_orchestration.py`. History tool wrappers currently live in `app/history_management/tools.py`. AI generation composition also lives in `app/chat/generation.py`; move that composition behind the orchestration facade while preserving Chat's durable turn ownership. Do not duplicate provider/model/context abstractions. The unified facade and confirmation graphs are now implemented; the live tracker records verification and remaining extensions.

```text
backend/app/langchain/
├── __init__.py
├── model_factory.py          # Current OpenAI-compatible provider factory
├── llm.py                    # Shared MentraLLM invocation and output validation
├── prompts/                  # Separate versioned prompt modules + trusted registry
├── chat_service.py           # Current simple chat workflow
├── profile_evaluator.py      # Current structured broad-profile evaluation
├── learner_tools.py          # Current learner-engine tool adapters
├── rag_tools.py              # Existing owned retrieval/source adapters
├── history_orchestration.py  # Existing bounded history/memory tool loop
└── ...                       # Add focused facade/router/graph modules as implemented
```

Do not create unused folders merely to match this tree. Preserve the boundaries as features are implemented.

As implementation proceeds, add focused `orchestration_service.py`, routing/decision schemas, context composition, activity publisher and tool executor modules rather than growing `chat_service.py` into one large file. Place actual graph definitions under `graphs/`, provider-independent workflow contracts beside their workflow, and checkpoint/activity persistence adapters behind explicit ports. Keep domain SQL in its owning repository. The facade coordinates these pieces and does not implement every module's policy.

---

# Phase 0 — Contracts and Module Skeleton

## Goal

The model and prompt boundary exists. Cross-module workflows now justify a stable orchestration facade. Add it incrementally around existing services with compatibility adapters for current callers.

## Tasks

1. Reuse the existing LangChain package and service boundaries.
2. Introduce `OrchestrationService` now as the central AI workflow entry point; inject it at startup and migrate callers without changing canonical domain ownership.
3. Extend `ModelFactory` for real provider requirements; currently it supports the configured `openai_compatible` adapter.
4. Add typed schemas close to each workflow until shared schemas are justified.
5. Reuse `create_learner_tools` for authenticated, server-scoped learner access.
6. Define graph state only with the first graph implementation.
7. Keep each workflow's system prompt in `prompts/<workflow>.py`, with its version and a `PromptSource` registry entry.
8. Keep provider errors and structured-output validation in the shared invocation boundary where appropriate.
9. Extend the existing backend tests.
10. Continue injecting domain services rather than hiding them behind globals.

Suggested facade:

```python
class OrchestrationService:
    async def chat(...): ...
    async def stream_chat(...): ...
    async def run_tutoring_turn(...): ...
    async def generate_assessment(...): ...
    async def grade_assessment(...): ...
    async def run_calibration(...): ...
    async def evaluate_profile(...): ...
    async def analyze_attachment(...): ...
    async def process_answer_sheet(...): ...
    async def resume_workflow(...): ...
```

FastAPI/application services should call this facade rather than constructing chains/graphs inside routes. Persistent Chat remains the outer turn/attempt owner and invokes the facade through an injected generation port. Events/history/memory are capabilities selected within runs; manual CRUD stays on domain APIs. Profile/memory semantic evaluation uses injected AI ports to avoid service/facade dependency cycles. Every workflow accepts the same activity publisher, including non-chat assessment/document jobs.

### Current status

- Implemented: FastAPI route delegates chat to `ChatService`; it does not contain prompt text or instantiate provider clients.
- Implemented: startup creates one `MentraLLM` and injects that same invocation component into chat and Student Profile evaluation.
- Implemented: `ModelFactory` constructs the configured OpenAI-compatible chat client, with configuration validation and bounded retry/timeout settings.
- Implemented: source-specific prompt modules (`chat.py`, `learner_context.py`, `student_profile.py`, `rag_context.py`, `history_management.py`, `memory_validation.py`) own prompt versions, and trusted services select their `PromptSource`.
- Implemented: `MentraLLM` composes registered instructions/context, supports structured output, and validates results.
- Implemented: learner tool adapters bind `learner_id` from authenticated server scope.
- Implemented: RAG retrieval in chat, read-only RAG tools, persistent conversations/attempts, bounded history/memory tool execution and structured memory admission. Tool existence does not imply registration in ordinary chat.
- Planned: unified facade/router, learner selection in normal chat, chat evidence extraction, Events AI tools/proposals, Notifications, LangGraph/checkpoints, streaming and full assessments. Library ingestion already exists; AI attachment/ingestion coordination is separate work.

### Remaining acceptance criteria

- API routes contain no prompt logic.
- API routes do not instantiate LLMs directly.
- Domain modules do not import LangGraph.
- Provider can be changed through configuration.

---

# Phase 1 — LLM Provider Abstraction

## Goal

Prevent Mentra from becoming tied to one AI provider.

Use LangChain's standard model interfaces underneath a Mentra-owned factory/configuration boundary.

Current configuration uses `AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`, `AI_BASE_URL`, `AI_TEMPERATURE`, `AI_TIMEOUT`, and `AI_MAX_RETRIES` (see `app/core/config.py`). Keep examples and future provider work consistent with these names. The supported provider value is currently `openai_compatible`; implement additional adapters only for an actual provider API need. These are the implemented setting names; do not add duplicate `LLM_*` aliases.

```text
AI_PROVIDER
AI_MODEL
AI_API_KEY
AI_BASE_URL
AI_TEMPERATURE
AI_TIMEOUT
AI_MAX_RETRIES
```

Only expose settings actually supported by the configured provider.

The existing `MentraLLM` receives the trusted `PromptSource` for each invocation. Prompt source answers “where did this request come from?” and is selected by service/graph code, never by HTTP input or model output. Model purpose is a separate concern; add purpose-aware model selection only when workloads need different model configurations. If introduced, keep all model construction and invocation behind the same `MentraLLM` component.

```python
result = await llm.ainvoke(PromptSource.CHAT, inputs)
```

Potential purposes:

```text
TUTORING
ROUTING
STRUCTURED_EXTRACTION
GRADING
ASSESSMENT_GENERATION
SUMMARIZATION
```

Currently all supported workflow sources use one configured model. Keep that default until evaluation shows a need to specialize.

Other Mentra modules must not instantiate provider SDK clients directly.

Only implement providers required now. Keep compatibility for API and local providers without building ten unused adapters.

### Acceptance tests

- configured model invokes through one Mentra interface;
- provider swap does not alter graph/domain code;
- missing credentials produce a clear error;
- retries/timeouts are bounded.

---

# Phase 2 — Structured Output Layer

## Goal

Never rely on free-form text where Mentra needs machine-readable decisions.

Use typed schemas for:

```text
intent classification
concept extraction
evidence extraction
misconception extraction
assessment specifications
grading results
routing decisions
```

Example:

```python
class ExtractedEvidence(BaseModel):
    concept_label: str
    result: Literal["correct", "partial", "incorrect", "unknown"]
    confidence: float
    misconception: str | None
```

The LLM output is a proposal, not learner state.

```text
LLM structured output
        ↓
schema validation
        ↓
concept resolution
        ↓
domain validation
        ↓
Learner Engine submit_evidence()
```

If output remains invalid after bounded retry, skip the durable mutation and preserve the user-facing interaction where possible.

---

# Phase 3 — Tool Layer

## Goal

Expose Mentra capabilities without leaking domain internals.

## Learner tools

Read tools:

```text
get_active_learning_contexts
get_relevant_learner_context
get_study_recommendations
get_verification_candidates
resolve_student_concept
```

Mutation:

```text
record_learning_evidence
```

Never expose:

```text
set_mastery
set_retention
insert_concept
update_learner_row
```

## RAG tools

```text
search_study_material
get_study_source_chunk
```

These are the existing names in `rag_tools.py`. Chunk access is restricted to IDs returned in the current tool scope and rechecks ownership/lifecycle. Ordinary chat currently pre-fetches RAG once and does not register these tools in the history-only loop. RAG performs retrieval; tools are adapters.

## Assessment tools

Possible adapters:

```text
get_assessment_targets
create_assessment_request
submit_assessment_evidence
```

Each tool must have a narrow purpose, typed input/output, domain-service call, minimal returned data, clear errors, and independent tests.

---

# Phase 4 — Prompt Architecture

## Goal

Keep prompts composable and bounded.

Build context from explicit sections:

```text
1. Mentra system behavior
2. workflow/task instructions
3. compact learner context
4. relevant RAG material
5. bounded conversation context
6. current user request
```

Not every request needs every section.

Prompt architecture is partially implemented. `app/langchain/prompts/` contains separate source-owned modules, and `prompts/registry.py` maps the closed `PromptSource` enum to each prompt and version. Services choose the source in trusted code and call the shared `MentraLLM`; external requests cannot select prompts. Chat uses `CHAT`, optionally composes the registered `LEARNER_CONTEXT` fragment, and passes the compact learner packet as server-owned context. Profile calibration uses `STUDENT_PROFILE_EVALUATION` with validated structured output.

Add future system prompts as separate workflow modules and registry entries, then route calls through `MentraLLM`. Do not inline system instructions in routes, graphs, tools, or ad hoc model calls. Dynamic learner or retrieved-document content is data/context, never a replacement for the registered system prompt. Keep prompt versions attached to evaluation/evidence where reproducibility requires them.

The base system prompt contains stable behavior, not dynamic learner data.

Dynamic learner state comes through `app.learner.engine.LearnerEngine.get_relevant_context(...)`. This interface exists, but normal chat does not yet fetch and pass its packet; Phase 8 must wire that behavior explicitly.

RAG context comes through the RAG service.

## Prompt budgets

`ContextBuilder` should enforce independent budgets for system instructions, conversation history, learner context, RAG, and tool results.

If compression is needed, remove low-value context before damaging the current user request.

---

# Phase 5 — Conversation Context

## Goal

Separate conversation memory from long-term educational memory.

Conversation history answers:

> What have we been discussing in this chat?

Learner Model answers:

> What does Mentra believe this student knows?

They are not interchangeable.

The primary endpoint is `/api/v1/conversations/turns`. `app.chat` owns PostgreSQL conversations, canonical visible messages, durable attempts, revisions, idempotent retries, leases and status/sync recovery. `/api/v1/chat` is deprecated and stateless, already bounded, and has no automatic personal-memory writes. Preserve that compatibility boundary.

`HistoryContextPolicy` selects recent canonical messages. `history_lookup` retrieves older exchanges on demand; `user_memory` recalls or proposes evidence-backed personal facts. Preserve canonical IDs through selection. No growing automatic summary is required. Any future summary must remain derived, versioned and invalidatable, never a substitute for source evidence. See Phase 30.

Do not replay unlimited history.

LangGraph checkpoints are workflow execution state, not automatically the canonical conversation database.

LangChain/LangGraph memory must never replace the Learner Engine.

---

# Phase 6 — Intent and Request Planning

## Goal

Determine which subsystems are required for a request rather than calling everything.

Potential intents:

```text
GENERAL_CHAT
EXPLAIN_CONCEPT
TUTORING
STUDY_RECOMMENDATION
QUIZ_REQUEST
ASSESSMENT_REQUEST
MATERIAL_QUESTION
PROGRESS_QUESTION
CALIBRATION
HISTORY_QUESTION
PERSONAL_MEMORY
EVENT_QUERY
EVENT_CAPTURE_OR_CHANGE
DOCUMENT_ANALYSIS
ANSWER_SHEET
NOTIFICATION_QUERY
OTHER
```

Prefer deterministic routing where obvious and model classification where semantic interpretation is needed.

Example plan:

```json
{
  "intent": "EXPLAIN_CONCEPT",
  "needs_learner_context": true,
  "needs_rag": true,
  "needs_assessment": false,
  "allow_evidence_extraction": true
}
```

---

# Phase 7 — Core Tutoring LangGraph

## Goal

Implement Mentra's primary adaptive conversational workflow.

```text
START
  ↓
prepare_request
  ↓
resolve_intent_and_context
  ↓
load_learner_context_if_needed
  ↓
retrieve_RAG_if_needed
  ↓
build_model_context
  ↓
generate_answer
  ↓
response_available
  ↓
extract_learning_evidence_if_assessable
  ↓
validate_and_resolve
  ↓
submit_evidence
  ↓
END
```

Where architecture/runtime permits, do not unnecessarily block the visible answer on non-critical post-response evidence extraction. Do not launch untracked work that can silently disappear.

Suggested graph state:

```python
class TutoringState(TypedDict):
    request_id: str
    learner_id: str
    conversation_id: str
    messages: list
    user_query: str
    intent: str | None
    active_context_ids: list[str]
    resolved_concept_ids: list[str]
    learner_context: dict | None
    rag_context: list
    model_context: dict | None
    response: str | None
    extracted_evidence: list
    accepted_evidence_ids: list[str]
    errors: list
```

Do not put the entire learner database into graph state.

---

# Phase 8 — Learner Context Integration

For relevant requests:

```text
query
  ↓
`LearnerEngine.get_relevant_context(...)`
  ↓
compact LearnerContextPacket
  ↓
ContextBuilder
  ↓
LLM
```

The LLM should receive only relevant concepts, misconceptions, and state.

For `What should I study?`, call ``LearnerEngine.get_study_recommendations(...)`` and let the LLM explain the result. Do not ask the LLM to scan the entire learner model.

---

# Phase 9 — RAG Integration

## Goal

Use RAG as a domain service rather than scattered retriever calls.

```text
user query
    ↓
resolved learning context
    ↓
RAGService.search(owner, SearchRequest(...))
    ↓
ranked chunks + provenance
    ↓
ContextBuilder
```

Prefer active material, then related material. Dormant material is used only when explicitly or strongly relevant; archived material only when requested.

RAG output should preserve content, document/source ID, chunk ID, relevance information, context ID, and citation metadata.

If RAG finds nothing, do not fabricate source-grounded claims.

---

# Phase 10 — Evidence Extraction Workflow

## Goal

Convert useful learning interactions into candidate evidence without treating every message as a test.

Likely evidence:

```text
student answers a question
student explains a concept
student solves an exercise
student corrects a misconception
student succeeds after hints
```

Usually not mastery evidence:

```text
"What is 3NF?"
"Explain recursion."
"Give me notes."
```

Flow:

```text
interaction
    ↓
is assessable?
    ↓
structured evidence extraction
    ↓
concept resolution
    ↓
confidence checks
    ↓
`LearnerEngine.submit_evidence(...)`
```

Raw LLM labels never become learner keys.

---

# Phase 11 — Assessment Generation Workflow

Recommended flow:

```text
START
  ↓
resolve requested context/scope
  ↓
Learner Engine:
  recommendations + verification candidates
  ↓
Assessment Engine:
  construct assessment specification
  ↓
LLM:
  generate question content
  ↓
structured validation
  ↓
Assessment Engine:
  persist canonical assessment
  ↓
END
```

The implemented Assessment domain owns assessment records. `app.learner.assessment` supplies targeting/observation contracts, not a canonical question bank or attempt store. Keep the Assessment domain/API/UI as an explicit dependency; never persist assessments only in checkpoints. Learner owns targeting; LLM generates language/content.

Every persisted question should map to canonical concept IDs, difficulty, marks, rubric/model answer, and question type.

This can begin as a service/chain and become a graph when branching/state justifies it.

---

# Phase 12 — Grading Workflow

```text
student answer
    ↓
load canonical question/rubric
    ↓
grade with structured output
    ↓
validate grade
    ↓
map concept-level performance
    ↓
submit evidence to Learner Engine
    ↓
generate feedback
```

Structured grading should support score, max score, concept-level results, misconceptions, grading confidence, and feedback points.

Do not reduce every result to correct/incorrect.

---

# Phase 13 — AnswerSheetGraph: OCR + Human Confirmation

This is a strong LangGraph use case.

```text
START
  ↓
load uploaded answer sheet
  ↓
OCR / segmentation
  ↓
OCR confidence check
  │
  ├── high confidence ───────────┐
  │                              │
  └── low confidence             │
          ↓                      │
      INTERRUPT                  │
          ↓                      │
 student confirms/corrects       │
          ↓                      │
       RESUME                    │
          └──────────┬───────────┘
                     ↓
                grade answers
                     ↓
              submit evidence
                     ↓
                    END
```

This workflow benefits from explicit state, branching, persistence, interruption, and resume.

Never update learner state before confirmation when OCR confidence is insufficient.

---

# Phase 14 — CalibrationGraph

## Goal

Preserve the implemented Student Profile onboarding calibration and add separate adaptive granular calibration. `student_profile/calibration` owns a fixed eight-question broad-profile assessment, atomic Finish and evaluation. Its UI keeps options/Next/Back local and submits the complete answer map only at Finish; preserve skip/resume and failed-Finish drafts.

The adaptive flow below concerns concept-level calibration using `app.learner.calibration` targets. Do not replace the broad-profile baseline or mix broad estimates with concept mastery. Any future adaptive onboarding integration needs an explicit versioned migration and equivalent UI acceptance.

```text
START
  ↓
collect minimal study context
  ↓
choose initial target
  ↓
ask question
  ↓
WAIT FOR USER ANSWER
  ↓
evaluate
  ↓
submit evidence
  ↓
choose next target based on uncertainty
  ↓
repeat until stopping condition
  ↓
complete calibration
```

For the new granular flow, use learner uncertainty to choose successive targets and bound question count, time and confidence stopping conditions. Preserve the current fixed Student Profile blueprint until intentionally migrated.

---

# Phase 15 — Streaming

Implement backend and frontend together. Every meaningful workflow step must emit a typed activity update, including deterministic steps and tool use. The UI displays these as the assistant's working/“thinking…” status. These messages describe actions, not hidden reasoning. Phase 34 defines the required Pydantic pre-tool output, activity stream, React integration and browser acceptance; token streaming alone does not complete this phase.

Potential event types:

```text
response_start
activity_started / activity_updated / activity_completed / activity_failed
tool_planned / tool_started / tool_completed / tool_failed
content_delta
reference_available
workflow_waiting
response_completed
error
```

Never expose internal chain-of-thought.

High-level UI activity may say things like `Searching your study material…` or `Checking your learning progress…`, not raw reasoning.

---

# Phase 16 — Failure Handling

A failure in one optional subsystem should not automatically destroy the interaction.

## Learner Engine unavailable

Where safe, continue non-personalized and record degraded mode. Never fabricate learner context.

## RAG unavailable

If the user explicitly asks about uploaded material, report retrieval failure. Do not pretend the document was read.

## Evidence extraction failure

Preserve the user-facing answer and skip learner mutation.

## LLM failure

Use bounded retries. Never create infinite loops.

## Tool failure

Return typed failure state and route intentionally.

---

# Phase 17 — Guardrails and Tool Permissions

Categorize tools:

```text
READ
SAFE_MUTATION
SENSITIVE_MUTATION
```

Sensitive mutations such as learner evidence or finalized grading should happen through explicit validated workflow nodes rather than unrestricted agent behavior where possible.

Do not give the model generic database or filesystem access.

---

# Phase 18 — Graph Persistence and Checkpointing

Use persistence for workflows that genuinely need pause/resume/recovery:

```text
multi-turn calibration
OCR confirmation
long assessment workflows
human confirmation/approval
independent event proposals
answer-sheet correction and recoverable evidence jobs
```

Graph checkpoints are not canonical storage for learner state, documents, assessments, or conversation history.

Define distinct identifiers:

```text
conversation_id
workflow_id
learner_id (internal UUID, bound from authenticated server context)
request_id
```

Do not overload one ID for all purposes.

---

# Phase 19 — Observability

Trace at least:

```text
request ID
workflow/graph name
node timings
provider/model
model/tool latency
tool calls
RAG retrieval count
learner-context concept count
token usage where available
structured-output failures
retries
degraded-mode events
workflow errors
```

LangSmith may be used for development/evaluation, but Mentra must not require it to function.

Do not send sensitive student data to third-party observability systems without an explicit privacy decision.

---

# Phase 20 — Token and Context Budgeting

The context builder should independently bound:

```text
conversation history
learner context
RAG chunks
tool results
system instructions
```

Rule:

> **Retrieve/select before summarize; summarize before truncate; never dump everything.**

100 or 10,000 historical learner concepts must not imply linear prompt growth.

Thousands of document chunks must still produce only a small relevant RAG context.

---

# Phase 21 — Caching

Possible cache candidates:

```text
stable prompt fragments
model configuration
concept-resolution candidates
RAG query embeddings
short-lived active-context lookups
```

Do not indefinitely cache learner state, recommendations, or retention-sensitive results.

Learner evidence submission should invalidate affected derived caches.

---

# Phase 22 — Security and Privacy

Before external LLM calls, send only required learner fields and RAG chunks.

The model often needs:

```text
"Recursion: low mastery; repeatedly confuses the base case"
```

not the student's entire history.

Uploaded material should be sent externally only when required by the operation and allowed by Mentra's privacy configuration.

---

# Phase 23 — Testing Strategy

## Unit tests

Test without external LLM calls where possible:

```text
ContextBuilder
tool adapters
routing
graph transitions
state reducers
failure routing
token budgeting
permission rules
provider factory
```

Provide a deterministic fake model.

Mock/fake domain services:

```text
`LearnerEngine`
RAGService
AssessmentService
```

## Integration tests

Test:

```text
chat → learner context → LLM
chat → RAG → LLM
student answer → evidence extraction → Learner Engine
recommendation request → Learner Engine → response
assessment request → targeting → generation
OCR low confidence → interrupt → confirmation → grading
calibration across multiple turns
```

## Failure tests

Explicitly test LLM timeout, invalid structured output, RAG timeout, learner errors, tool exceptions, graph resume, duplicate requests, and cancelled streams.

---

# Phase 24 — Evaluation

Measure orchestration separately from model quality.

Potential metrics:

```text
correct tool selection
unnecessary tool-call rate
learner-context relevance
RAG grounding accuracy
structured-output validity
evidence extraction precision
graph completion rate
average latency
time to first token
token usage
cost per tutoring turn
degraded-mode rate
```

For learner-state mutation, precision is more important than extracting evidence from every possible interaction.

---

# Phase 25 — Initial Graph Set

Do not create dozens of graphs.

Recommended initial set:

```text
1. TutoringGraph
   Main adaptive conversational learning workflow

2. CalibrationGraph
   Multi-turn granular calibration; preserve current profile onboarding

3. AnswerSheetGraph
   OCR → confirmation interrupt → grading → evidence

4. AssessmentGenerationGraph
   Add when assessment generation develops meaningful branching/state

5. GradingGraph
   Add when grading develops meaningful branching/state
```

Add `EventConfirmationGraph` for durable event proposals as the first narrow graph rollout after Phase 33 passes. It is independent of a completed chat turn. Assessment generation and grading may initially remain ordinary orchestration services/chains.

---

# Phase 26 — Integration Contracts

## Learner Engine

LangChain/LangGraph may call:

```python
resolve_concept(...)
resolve_learning_context(...)
get_active_contexts(...)
get_relevant_context(...)
get_study_recommendations(...)
get_verification_candidates(...)
submit_evidence(...)
```

Never manipulate learner persistence directly.

## RAG Engine

Implemented public methods (request fields remain defined by `rag/schemas.py`):

```python
search(owner, SearchRequest(...))
get_chunk(owner, chunk_id, include_archived=False)
search_document(owner, document_id, query, ...)
search_assessment(owner, AssessmentGroundingRequest(...))
```

RAG owns embeddings, vector search, hybrid search, reranking, and provenance.

## Assessment Engine

Expected conceptual interface:

```python
create_assessment(...)
get_assessment(...)
get_question(...)
record_attempt(...)
finalize_grading(...)
```

Assessment persistence belongs to Assessment Engine.

## LLM Provider

Expected conceptual capabilities:

```python
get_model(purpose)
invoke(...)
stream(...)
structured_output(...)
```

---

# Phase 27 — Request Flow Examples

## Explain a concept

```text
"Explain transitive dependencies again."
        ↓
TutoringGraph
        ↓
resolve concept/context
        ↓
Learner Engine → relevant learner context
        ↓
RAG → active Database Systems material
        ↓
LLM → personalized explanation
        ↓
no mastery evidence merely because the student requested an explanation
```

## Student answers

```text
Mentra: "Why does this violate 3NF?"
Student: "Because a non-key field depends on another non-key field."
        ↓
response generation
        ↓
evidence extractor
        ↓
structured candidate evidence
        ↓
concept resolution
        ↓
Learner Engine submit_evidence()
```

## What should I study?

```text
request
  ↓
intent = STUDY_RECOMMENDATION
  ↓
`LearnerEngine.get_study_recommendations(...)`
  ↓
top relevant recommendations
  ↓
LLM explains naturally
```

No full learner-model dump.

## Old knowledge becomes relevant

```text
Current context: Python

"Is a Python dictionary like a database table?"
        ↓
Python = active
Database Systems = explicitly relevant dormant context
        ↓
Learner + RAG retrieve both selectively
        ↓
LLM produces cross-context explanation
```

---

# Phase 28 — Agent Implementation Rules

AI coding agents must obey these constraints:

1. Do not instantiate LLM providers inside API routes.
2. Do not place domain business logic inside LangChain tools.
3. Tools adapt domain services; they do not replace them.
4. Do not let LangChain write learner tables.
5. Do not bypass RAG services with direct vector/database calls from prompts/graphs.
6. Do not use free-form LLM output for durable mutation when structured output is possible.
7. Do not make every operation a LangGraph graph.
8. Do not store the whole learner model in graph state.
9. Do not use LangGraph persistence as the canonical learner database.
10. Do not send all historical learner concepts to the LLM.
11. Do not send all RAG chunks to the LLM.
12. Do not expose `set_mastery`-style tools.
13. Do not update learner state from low-confidence extraction.
14. Do not block the visible answer on non-critical post-processing unless correctness requires it.
15. Do not run unbounded agent/tool loops.
16. Do not silently pretend an answer is grounded when RAG failed.
17. Do not couple graphs to one provider.
18. Do not expose chain-of-thought.
19. Keep mutations explicit, validated, traceable, and narrow.
20. Add fake-model/domain-service tests before relying on live APIs.

---

# Phase 29 — Implementation Order

1. Freeze current contracts and regression fixtures; add the facade and dependency injection (Phases 0-2, 26).
2. Centralize generation/context/tool execution while preserving durable chat, RAG, history and memory (3-5, 9, 30, 34).
3. Add bounded routing, learner/profile context and recommendations; retain simple chat (6-8, 20).
4. Add validated chat evidence and durable post-processing (10, 17, 35).
5. Resolve the graph/checkpoint dependency gate in a disposable runtime (18, 33).
6. Add Events admission/tools and narrow confirmation graph, proposal APIs and UI (31, 34).
7. Deliver generic Notifications and the independent reminder worker/inbox (32, 34).
8. Introduce the tutoring graph where justified and streaming with canonical publication/recovery (7, 15-16).
9. Build canonical assessment APIs/UI; generation, grading and granular calibration (11-12, 14, 34).
10. Compose Documents/Vision and answer-sheet correction/resume (13, 35).
11. Complete observability, caches, privacy, evaluation and rollout gates (19-24, 33, 36).

Stages are incremental, not scope cuts. Dependency-independent work can proceed before graph adoption. Preserve all requirements in Phases 0-28 and the additions in Phases 30-36; use the traceability matrix below for final sign-off.

Each phase requires implementation, typed contracts, unit tests, relevant integration tests, and documentation of new public behavior.

---

# Architectural Invariants — Do Not Violate

1. **LangChain/LangGraph is orchestration, not the owner of domain truth.**
2. **Auth binds internal learner identity; Learner owns concept evidence policy, mastery, retention and learning-context lifecycle.**
3. **RAG Engine owns ingestion and retrieval.**
4. **Assessment Engine owns canonical assessments.**
5. **LLM providers are replaceable.**
6. **Structured outputs are validated before domain mutation.**
7. **Raw LLM labels are resolved before becoming concept references.**
8. **The full learner model is not placed in ordinary prompts.**
9. **The full document corpus is not placed in ordinary prompts.**
10. **Conversation memory is not the Learner Model.**
11. **LangGraph checkpoint state is not canonical domain storage.**
12. **Human confirmation occurs before uncertain OCR-derived evidence is persisted.**
13. **Deterministic domain logic should not be delegated to an LLM unnecessarily.**
14. **Simple workflows remain simple; LangGraph is used where state/branching/resume provides real value.**
15. **Mutations are explicit, validated, traceable, and narrow.**
16. **Optional personalization may degrade gracefully, but Mentra must never invent missing learner/RAG data.**

---

# Definition of Done

The LangChain + LangGraph module is complete for the first full Mentra implementation when:

- FastAPI invokes Mentra through a stable orchestration facade;
- all module integrations and backend/frontend acceptance requirements in Phases 30-36 are complete, with implemented versus planned capabilities reported honestly;
- every workflow step publishes bounded user-facing activity, and model-selected tools emit validated tool names and action descriptions before execution;
- the frontend shows live working status, tool activity, durable confirmations, recovery, citations and final answers through the existing chat components;
- the configured LLM can be swapped without rewriting workflows;
- tutoring requests selectively retrieve learner context;
- RAG retrieval is context-aware and provenance-preserving;
- general recommendations come from the Learner Engine rather than an LLM scan;
- assessable student responses can produce validated learner evidence;
- non-assessable questions do not create fake mastery evidence;
- adaptive assessments consume learner recommendations/verification candidates;
- grading produces structured concept-level evidence;
- low-confidence handwritten OCR can pause and resume through confirmation;
- existing broad-profile onboarding remains intact, and separate granular calibration supports bounded adaptive turns;
- streaming works without exposing hidden reasoning;
- graph state is bounded and does not duplicate domain databases;
- failures have explicit degraded/error paths;
- prompts have bounded learner/RAG/conversation context;
- model/tool calls are observable and testable;
- fake models allow deterministic graph tests;
- no external module is bypassed through direct database access;
- Mentra's learner intelligence remains intact when the LLM provider changes.

The following integration phases complete this definition of done, including frontend delivery. They are required scope, not optional follow-up suggestions.

---

# Current Codebase Inventory and Migration Boundary

This inventory records source inspection on 2026-10-09, not a new runtime test result. Read executable code before older README/plan claims. The current checkout already contains unrelated documentation edits; implementing this plan must preserve unrelated work.

| Module / source of truth | Existing implementation | Orchestration work still required |
| --- | --- | --- |
| `app.langchain` | Shared `MentraLLM`, `ModelFactory`, prompt registry, profile evaluator, chat service, learner/RAG adapters, history tool loop | Unified facade, typed routing/context plan, shared tool executor, activity stream, graphs and workflow recovery |
| `app.chat` | PostgreSQL conversations, canonical messages, attempts, leases, revision/sync recovery; `generation.py` composes RAG and history | Move AI composition behind injected facade; retain canonical publication and turn recovery; add streaming/activity projections |
| `app.learner` | Public engine/schemas, PostgreSQL repository, canonical concepts/contexts, evidence, scoring, retention, recommendations, verification, assessment/calibration adapters | Wire selective learner context into ordinary chat, validated assessable-turn evidence, adaptive targeting and bounded Learning UI reads |
| `app.student_profile` | Explicit profile details, broad estimates, onboarding, eight-question calibration, structured evaluator and context-version fencing | Select minimal profile context when useful; preserve explicit facts and broad/granular separation; coordinate evaluation through the shared AI boundary |
| `app.rag` | Library lifecycle/ingestion worker, extraction adapter, embeddings/Qdrant, scoped retrieval and source packets; `search_assessment` exists | Intent-aware retrieval, bounded tool registration, assessment grounding and attachment choices; preserve publication/generation fences |
| `app.documents` | Public reader facade, native format/code readers, provenance, warnings, isolated bounded extraction | Add authorized chat/assessment attachment workflow; reuse reader rather than another parser; persistent Library indexing only when selected |
| `app.vision` | Stateless English Tesseract OCR and poppler PDF rasterization | Answer segmentation, question mapping, handwriting quality/confidence contract and correction UI; generic OCR is not a complete handwriting grader |
| `app.history_management` | History lookup, personal memory recall/admission/maintenance, provenance, receipts, preferences and reference validation | Integrate existing tools into shared registry/budgets and activity events; retain source visibility, consent and publication fences |
| `app.history_management.events` | Manual Events service/APIs, temporal preview, lifecycle, preferences, evidence/audit/receipts/sync and single-reminder ledger | AI admission/tools, durable proposals, confirmation graph, reminder producer and complete Events frontend |
| Notifications | No `app.notifications` implementation | Build independent inbox, receipts, preferences, sync, producer API and shared frontend; Events first producer |
| Assessments | Learner observation/targeting adapters; `AssessmentsPage` placeholder | Canonical assessment/question/attempt/answer/grade domain, APIs, generation/grading workflows, history and answer-sheet frontend |
| Auth / `integrations.eduverse` | Internal UUID identity, authentication/onboarding guards, signed external provisioning/profile initialization | Bind identity outside model input; preserve signed-subject validation; no LLM authentication/provisioning tools |
| `app.db`, core, workers | PostgreSQL/Alembic, owner transaction boundary, configuration, logging, errors, RAG worker | Workflow/checkpoint/activity migrations, bounded maintenance/reconciliation and independent reminder worker |
| React frontend | Persistent Chat/Library/Profile/Memories and citations; Progress/Assessments placeholders | Live activity/token stream, proposals, Events/Learning/Notifications, assessments, OCR correction and adaptive calibration |

Startup wiring is in `backend/app/main.py`. The existing path is `conversations/turns -> ConversationService -> chat.generation.generate_reply -> ChatService -> MentraLLM / history_orchestration`. Generation currently searches RAG when available but does not load granular learner context for `ChatService.reply`. `create_learner_tools` and `create_rag_tools` exist; the history loop registers only `history_lookup` and `user_memory`.

Target persistent path: `API -> ConversationService (begin/recover turn) -> OrchestrationService (plan/execute/publish activity) -> public domain facades -> ConversationService (validate/finalize)`. Inject a typed run context rather than passing a FastAPI Request into orchestration. Manual domain endpoints continue to call their services directly. Student Profile and memory semantic validators use injected AI ports implemented by this module, without introducing circular imports or moving their policies into prompts.

# Phase 30 — Central Planning, History, Memory and Profile

## Typed execution and module selection

Define a trusted `RunContext` containing authenticated owner, request/conversation/turn/attempt IDs, canonical current user-message ID, server clock, explicit user timezone if known, approved source selection, domain revisions, capabilities and budgets. Models cannot supply ownership, leases, prompt sources, graph thread IDs or consent flags.

Define a validated `ExecutionPlan`: intent, selected modules, ordered steps/dependencies, required versus optional reads, proposed mutations, evidence eligibility, required confirmation, context allocation and total deadline. A classifier proposes a plan; deterministic policy validates it against the request, feature availability and permissions. Avoid a classification call for obvious explicit actions. Compound requests may select several modules; “remember my study preference and add my exam” becomes two independently validated operations with distinct outcomes.

| Request | Required decisions and modules | Durable effect |
| --- | --- | --- |
| General explanation | Simple response; learner/profile only when useful | No mastery evidence from asking a question |
| Material question | Resolve approved scope, RAG sources, optional relevant learner packet | Canonical answer plus verified source references |
| “What should I study?” | Learner recommendations/verification, optionally relevant upcoming Events | Explain domain-ranked results; no invented score or automatic schedule |
| “What did we discuss?” | Bounded history tool with owned references | Read only |
| Personal preference / correction | Profile fact lookup and personal memory admission | Memory receipt or confirmation; never silently edit explicit profile details |
| Upcoming exam / deadline | Events lookup, temporal normalization and admission | Committed event or durable proposal, never a deadline hidden in memory |
| Quiz / graded answer | Learner targets, RAG grounding if needed, Assessment domain | Canonical questions/attempt/grades and accepted learner evidence |
| Uploaded file / answer sheet | Authorized attachment, Documents/Vision, user-selected purpose | Temporary analysis, explicit Library job, or assessment attempt/correction workflow |
| Notifications | Bounded owned inbox/service reads, explicit user actions | No model-created reminder duplication or automatic mark-all-read |

Use a capability registry with typed input/output, module owner, allowed intent, read/mutation category, timeout, maximum result size, retry policy and user-visible display name. A server allowlist selects tools per run. Do not bind every tool for every request. Extend existing adapters, including `get_student_weaknesses` and `resolve_student_concept`, without inventing aliases that conflict with current names.

## Context composition and bounded tool execution

Compose independently budgeted registered instructions, current request, recent canonical exchanges, learner packet, minimal profile context, RAG, and selected tool results. No mandatory full profile/memory/event dump. Existing prompt sources are `CHAT`, `LEARNER_CONTEXT`, `STUDENT_PROFILE_EVALUATION`, `RAG_CONTEXT`, `HISTORY_MANAGEMENT`, `MEMORY_VALIDATION`; add trusted versioned sources for routing, evidence, Events, assessment, grading and activity/tool decisions as those workflows are implemented.

Reuse `CHAT_HISTORY_TOKEN_BUDGET`, `CHAT_CONTEXT_WINDOW_TOKENS`, `CHAT_OUTPUT_TOKEN_RESERVE`. Existing history execution bounds are five model calls, six tool calls, two write proposals and 3000 cumulative UTF-8 bytes of tool results. Preserve these until measured revisions justify new settings. A composed workflow needs one shared budget, not six calls per module. Account for schemas, pre-tool structured output, activity descriptions, protocol overhead and final answer capacity. Bound per-tool and total wall time under the parent turn deadline; current persistent generation timeout is 150 seconds.

Trim complete exchanges/tool groups without orphan tool messages; preserve the current request or return an actionable context-limit error. Prefer select/retrieve before any summarization. Cache reads only within authorized scope, invalidate after writes and revalidate at publication. Serialize conflicting mutations; parallelize only independent bounded reads with deterministic result/reference merging.

## Preserve existing history and memory guarantees

1. History remains a read projection over canonical Chat records. Cross-chat lookup requires keywords; bound windows, dates and result size. Keep message role, occurrence time, exchange status and source identity.
2. Memory remains personal facts/preferences/goals, distinct from profile details, learner mastery, study documents and dated Events. Recall includes only eligible current facts through the public service.
3. AI writes require an exact span from an owned user message visible in this run or returned by authorized history lookup. Assistant text, uploaded content and arbitrary IDs are not personal evidence.
4. Preserve structured semantic verification, pending inference confirmation, explicit consent for sensitive memory, secret rejection, manual correction precedence, expiry, quotas and the independent automatic-memory preference. Recheck preferences at commit.
5. Preserve receipt identity derived from canonical turn/proposal, lease/attempt fencing, revision checks, deletion suppression and the shared owner lock. Verification holds no database locks.
6. Publication revalidates current memory references and source existence. Preserve `S` Library, `H` history and `M` memory namespaces and viewers; model-authored markers cannot create references.
7. Chat deletion detaches evidence according to existing retention policy. Checkpoints/activity caches cannot restore deleted facts or become an ungoverned second transcript.

## Learner and Student Profile remain separate

Use `StudentProfileService.prompt_context` for bounded broad personalization when needed. Explicit educational details and preferences remain user controlled; profile evidence updates estimates under its versioned service policy. Do not send all profile fields for ordinary chat. Preserve EduVerse initialization semantics and never overwrite later manual edits.

Granular learner context, recommendations and verification come from `LearnerEngine` public schemas. Resolve contexts/concepts before use; ambiguous labels remain candidates. Distinguish mastery, estimate confidence, retention confidence and relevance. Preserve hint dependence, independent success, difficulty, misconceptions, contradiction verification and source/channel quality. A completed Event, read document, self-rating or memory is not demonstrated mastery.

Acceptance: trace simple chat, history recall, memory write/rejection, relevant learner personalization, study recommendation and mixed event/memory requests with fake services and real owned persistence. Verify no unnecessary calls and no bypass of domain policy.

# Phase 31 — Events Tools and Durable Confirmation

Implement the remaining AI integration from [Events plan](Mentra_Events_Implementation_Plan.md), preserving the manual foundation described in [Events implementation](docs/events.md).

- Add `event_lookup` for bounded owned agenda queries and typed references. Add `event_manage` for propose-create/update/status with exact visible user evidence; owner, proposal ID and run identity are server bound. No autonomous hard-delete tool.
- Validate evidence and deterministic fields before at most a bounded necessary structured admission/date call. Separate independent memory/event extraction from the same sentence. No extra event extraction pass on every chat turn and no historical transcript rescans.
- Preserve date-only versus aware-instant modes, IANA zones, original local meaning, DST gap/fold choices and occurrence-time anchoring for relative dates. Do not invent a timezone or time when absent. Use Events temporal preview; ask through a proposal when required fields/intent are uncertain.
- Clear supported first-party statements may save automatically under Events policy. Unclear dates, ambiguous duplicate matches or conflicting changes to manually controlled events create durable proposals. Final transaction rechecks capture preference, revision, evidence lifecycle, lease and ownership.
- Tool outcomes distinguish `saved`, `already_known`, `awaiting_confirmation`, `rejected`, `expired`, `unavailable`. Success wording is allowed only after a committed outcome; `tool_started` never implies an event was saved.
- `EventConfirmationGraph` accepts a server-created proposal ID and minimal typed state, interrupts, validates explicit decisions/edits, and commits through EventsService. The normal assistant answer completes with a proposal card. Keep chat statuses `RUNNING/SUCCEEDED/FAILED`; do not add WAITING or hold a turn lease while the student is away.
- Proposal APIs verify owner, expected revision, expiry, target revision and current evidence. Clients submit typed decisions, never raw graph commands or thread IDs. Explicit approval is a manual action even when automatic capture has since been disabled; reminder preferences remain independent.
- Store proposals and decisions in Events persistence; graph checkpoints are execution state. Reconcile event commit/checkpoint failure using durable receipts. Concurrent approve/dismiss has one winner; retries cannot create another event. Claims expire and recover.
- Purge proposal checkpoint payloads, pending writes and blobs on terminal retention, rejection/deletion and applicable source/account deletion. Confirmed Events survive source chat deletion with detached evidence; unsupported pending proposals are cancelled according to policy.

Frontend: chat cards show title/kind, local date/time/zone, uncertainty, reminder defaults, **Add event**, **Edit details**, **Dismiss**. Pending proposals are also recoverable in Progress after refresh/login/restart. Keep drafts on failed saves and show current revisions on conflicts. Final acceptance includes continued chatting while a proposal is pending, restart/resume and deletion races.

# Phase 32 — Notifications and Reminder Coordination

Notifications is a new standalone `app.notifications` domain, not a History/Events table wrapper or graph loop. Implement its generic producer API, inbox, content-free delivery receipts, unread totals, read/dismiss, independent global/type preferences, revision/sync/tombstones, retention and safe target descriptors. Its core must not import Events, learner repositories or history internals. Verify reuse with a second test producer.

Events owns eligibility and its lifetime reminder ledger; Notifications owns idempotent publication/delivery. A lightweight `events-worker` uses bounded batches, leases, retry/backoff, clean shutdown and heartbeat. It loads neither embeddings/Qdrant nor document/LLM clients. Do not use a sleeping graph or RAG ingestion worker as a scheduler.

One event may create at most one lifetime notification/reminder, including concurrent workers, retries, rescheduling, reopening, inbox pruning, read/dismiss and restart. Keep the Events ledger and Notifications producer receipt consistent through the public transaction contract; preserve the existing owner-first lock order. Delivery rechecks event/global preferences and lifecycle. Re-enable skips missed disabled-window reminders; a delivered event cannot rearm. Purge personal snapshots while retaining permitted content-free deduplication receipts; deleting an inbox row cannot recreate a reminder.

Orchestration may read bounded upcoming events/notifications when relevant and explain committed outcomes. It cannot bypass notification preferences, publish duplicate reminders, or infer successful delivery from a pending ledger. Manual inbox management uses authenticated domain APIs.

Frontend delivery in this plan includes a shared inbox entry/badge, paged unread/all list, mark-read/dismiss, Settings preferences and safe deep links to current Events. Use authoritative unread totals, cap badge text with accessible actual counts, and show deleted/changed targets honestly. Many due Events produce one aggregate badge and a paged inbox, not per-item toasts, sounds or popups.

# Phase 33 — Durable Runtime, Dependencies and Recovery

The original baseline pinned `langchain-openai==0.3.35` and had no graph dependency. The current implementation pins `langchain-openai==1.7.0`, `langchain-core==1.6.9`, `langgraph==1.2.14`, `langgraph-checkpoint==4.2.0` and `langgraph-checkpoint-postgres==3.1.2`. Frozen Alembic migrations own the saver schema; startup never calls `saver.setup()`. Earlier compatibility-gate notes are historical.

Before adoption, resolve and pin a supported compatible LangChain/provider/graph/checkpoint/PostgreSQL saver set in a disposable actual-runtime image. Recheck upstream advisories and selected-version documentation. Test any required framework migration against current message/tool/structured-output/provider behavior before changing production pins. Do not install an old vulnerable candidate merely because it resolves. See the [upstream checkpoint advisory](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-g48c-2wqr-h844) and the repository's disposable `backend/testing/event_dependencies.py` probe.

Require strict serializer controls for selected dependencies, minimal typed state and owner-safe deletion. Rehearse saver setup/migrations, interrupt, process restart, authenticated resume, replay, concurrent decisions and deletion of checkpoints/pending writes/blobs. Upstream interrupts resume by re-entering the interrupted node, so pre-interrupt effects must be idempotent; do not equate resumption with exactly-once business execution. See [LangGraph interrupt documentation](https://docs.langchain.com/oss/python/langgraph/interrupts). Use only APIs supported by the tested pins, not unversioned examples copied from newer documentation.

Use distinct server-bound conversation, turn, attempt, workflow, proposal, checkpoint-thread, step and operation IDs. Persist a workflow version and define how in-flight workflows migrate, complete under their original version or fail safely after deployment. Store IDs/revisions and bounded validated data, not live services, provider objects, secrets, raw full transcripts or entire uploads.

Database commits and checkpoint advancement are not one atomic transaction. Each mutation needs a domain receipt and reconciliation strategy. If domain commit succeeds then the graph crashes, retry reads the receipt; if checkpoint/proposal creation fails first, restart from canonical durable state. Use bounded reclaimable claims, no permanent processing flags. Preserve owner-first transaction ordering and never hold locks during model/network/OCR calls.

Account/source deletion and preference changes fence running attempts, post-processing and resume. Every delayed job revalidates current authorization, evidence lifecycle and revisions. Additive migrations must preserve existing data and pass upgrade/downgrade/re-upgrade and concurrent migration rehearsal on a dedicated test database. Dependency probes must never run during application startup.

# Phase 34 — Live Activity, Tool Announcements and Complete Frontend Delivery

## Required user-visible behavior

For every meaningful step, orchestration sends what is currently happening to the frontend: “Checking your learning context”, “Reading documents”, “Searching earlier conversations”, “Checking the proposed event”, “Preparing your answer”. Show this in the assistant's working/“thinking…” area. A step begins before the work, updates when the action changes, and ends with completed/failed/cancelled status. Do not invent percentages or silently keep a spinner after terminal failure.

Before each model-selected tool executes, require a structured model decision containing the exact tool name, validated tool arguments and a short user-facing action description. For example: `search_study_material` and “Searching your study material for normalization examples. Please wait…”. The UI can display a friendly label while retaining the exact returned tool name in activity details. Do not expose private tool arguments or raw reasoning.

## Pydantic model output and server event envelope

The following is a target contract, not existing code. Define a discriminated model decision union: `ToolDecision` or `FinalDecision`. Generate per-tool argument schemas from the trusted registry and validate arguments against the selected tool. `ToolName` is the server allowlist of tools enabled for that run, not an arbitrary provider string.

```python
class ToolDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["tool"]
    tool_name: ToolName
    user_message: str = Field(min_length=1, max_length=240)
    arguments: dict  # Validate against registry[tool_name].args_schema before use.

class FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["final"]
    content: str = Field(min_length=1)

class ActivityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    event_id: UUID
    sequence: int = Field(ge=1)
    conversation_id: UUID
    turn_id: UUID
    attempt_id: str
    workflow_id: UUID | None = None
    step_id: str
    tool_call_id: str | None = None
    tool_name: str | None = None  # Registry-validated when present.
    event_type: ActivityEventType
    status: Literal["planned", "running", "completed", "failed", "cancelled", "waiting"]
    user_message: str = Field(min_length=1, max_length=240)
    occurred_at: datetime  # Server-generated aware timestamp.
```

Imports/enums and exact identifier representations are resolved against existing domain schemas during implementation; examples must not force replacement of current turn/attempt identities. Use typed envelopes for content deltas, references, terminal results and confirmation payloads rather than forcing all payloads into an activity message.

The model owns only its proposed tool/action text and arguments. Server code binds all IDs/timestamps/sequences, validates the enabled tool and permission, sanitizes the user message, and emits `tool_planned` before invoking it. Reject unknown names, invalid arguments, model-supplied IDs and unsupported mutation intent. Bound repair attempts under the same run budget; malformed output must never run a tool. If the description is unsafe, overly revealing or missing after validation, use a safe registry template; do not skip the announcement.

Support two tested provider execution modes behind `MentraLLM`: structured decision output dispatched by the server, or native tool calling through typed wrapper schemas requiring the same public action description. Do not assume all providers support native tools and structured response schemas simultaneously. Normalize both to the same validated decision/event contract. Strip public-description metadata before calling domain services. Preserve native tool-call/result protocol IDs when using native mode. If neither mode is supported, provide an honest text-only/degraded answer without claiming tools ran.

For deterministic server-selected steps, emit the same event contract from trusted templates without an unnecessary model call. Emit an initial “Planning your request” activity before waiting for the first model decision. If the model proposes several tools, announce each immediately before its dispatch; never announce queued tools as already running. Keep one shared budget and attach unique operation/tool-call IDs.

Execution order is explicit: validate decision -> authorize -> append/publish `tool_planned` -> append/publish `tool_started` -> execute bounded domain operation -> publish completed/failed result -> continue. Persist/publish before dispatch so ordered stream delivery can precede completion; a disconnected frontend does not require an acknowledgement to let work continue. Domain commit is required before “Saved” wording. Failure produces an actionable safe status and appropriate fallback; raw exception strings, prompts, credentials, full quotes and chain-of-thought never enter activity events.

## Backend transport and recovery

Add an authenticated server-sent event endpoint under the existing conversation/turn API, for example `GET /api/v1/conversations/{conversation_id}/turns/{turn_id}/events` (new proposed endpoint). Keep `POST /conversations/turns` backwards compatible; add an explicit opt-in streaming-client admission mode that returns a durable accepted turn promptly while generation runs. The browser then subscribes using the canonical IDs. Appending events before subscription must be recoverable. Keep normal JSON/status polling as fallback.

Use a bounded durable activity journal or equivalent shared replay store keyed by owner/turn/attempt. Do not depend on a process-local queue for multi-worker delivery or restart recovery. Sequence events monotonically within the documented stream identity; deduplicate by event ID. Support a validated resume cursor/Last-Event-ID, heartbeat, expiry/reset and final canonical snapshot. Preserve old-attempt isolation when a retry starts. Store minimal status messages with explicit TTL/size limits and deletion policy; high-volume content deltas may be transient if reset/status can retrieve the canonical answer. Activity is operational UI metadata, not chat evidence or personal memory.

Transport disconnect does not cancel the durable turn or repeat mutations. Subscription errors reattach/poll. Explicit cancellation, if added, uses a separate authenticated operation with defined semantics: stop future work where possible, fence publication, and report any already committed mutation truthfully. Add bounded buffering/backpressure, connection limits, no-store responses, origin/access checks and proxy flushing/timeouts. Completion is emitted only after canonical assistant publication; a final validation failure cannot appear as success. Activity termination and durable failed status must reconcile after crashes.

Streaming model content is provisional until commit. Prevent intermediate structured JSON, tool arguments and incomplete reference markers from appearing in final Markdown. Mutating-tool confirmations must not stream ahead of the committed receipt. On failed publication, replace provisional content with the canonical failure/retry state. No hidden reasoning tokens or provider reasoning fields are exposed.

## React implementation within this delivery

| Existing surface | Required implementation |
| --- | --- |
| `services/api.ts`, `services/conversations.ts`, shared types | Typed admission/activity/content/reference events, credentialed stream connection, schema-version handling, abort/reconnect/resume and polling fallback; preserve existing JSON error behavior |
| `stores/chatStore.ts`, `chatCache.ts` | Per-owner/conversation/turn/attempt activity state; dedupe/sequence reducer, current step, bounded history, provisional content and canonical final reconciliation; no persistence of sensitive raw tool payloads |
| `ChatSession`, `ChatMessage`, `ChatComposer` | Show initial working state immediately, current activity and tool label before tool result, optional compact activity disclosure, final/error/retry/waiting states; keep composer behavior and canonical turn rules |
| Existing Markdown/citation viewers | Reuse `MarkdownContent`, `CodeBlock`, `SourceViewer`, `HistoryReferenceViewer` and memory viewer; resolve only server-issued `S/H/M` references and new typed Event references |
| Chat event proposals | Add/Edit/Dismiss cards, accessible validation and failed-save drafts; waiting proposal stays independent of chat completion; restore from server after reload |
| Library/material detail/source selector | Preserve upload/job polling, scope/mode selection, archive consent, warnings and citations; show reading/retrieval activity in chat and link to current owned sources |
| Progress | Replace placeholder with Events and Learning tabs per Events plan; agenda, filters, manual create/edit/lifecycle/delete, timezone/temporal preview, reminders, proposals, sync/tombstones; Learning consumes bounded public projections |
| Settings/account drawer | Preserve Profile/Memories and their drafts; add independent event capture/reminder and Notifications preferences with URL/tab/keyboard handling; preserve centralized theme selector |
| Notifications | Shared entry/badge, unread/all paged inbox, read/dismiss, authoritative counts, safe targets and settings; no flood of per-event popups |
| Assessments | Replace placeholder with generated quizzes/mock papers, question/attempt workflow, saved results/history, partial/concept-level feedback, revision/retry states and links from chat |
| Answer sheets | Owned upload, processing activity, extracted answer/question mapping, correction/confirmation, explicit submit, grading progress and recoverable results |
| Calibration | Keep current local-choice/atomic-Finish UI; add distinct granular adaptive session with resume, answer entry, progress/stopping reason and feedback |

Use existing shared UI primitives and semantic theme tokens. Activity is an accessible polite status region; do not announce every token or force focus/scroll on each update. Support reduced motion, narrow screens, keyboard interaction and Light/Dark/System. Do not reveal prompts, node internals or raw arguments in a technical dashboard. Human-facing labels are short action descriptions.

On account switch/logout, abort streams and clear owner-scoped activity/drafts/caches. On conversation switch, disconnect the view without cancelling generation; restore running/final state when revisiting. Ignore late events from another owner or superseded attempt. Keep scroll position stable when reviewing older messages and allow the user to return to the latest response.

## Required activity and frontend acceptance

1. A delayed fake tool emits a validated exact tool name and public message; the browser shows “Reading documents” or the specific tool action before the tool finishes. Verify server event append precedes dispatch, not just that a spinner eventually appears.
2. Deterministic learner loading, document extraction, retrieval, grading, validation and saving all have start/terminal events. Invalid model decisions invoke no tool and show a safe retry/degraded status.
3. Exercise both native-tool and structured-decision providers, including unsupported capabilities, malformed output, timeout and final-answer generation.
4. Disconnect/reconnect before/after commit, reload, switch conversations, restart the backend, retry a failed turn and deliver duplicate/out-of-order/stale-attempt events. No duplicated answer/mutation or permanently spinning UI.
5. Test authentication expiry, owner isolation, deletion during execution, expired cursors, dropped heartbeats, polling fallback, multi-worker delivery and bounded replay/buffering.
6. Verify proposal approval/dismiss races and continued chat while waiting; no success label before commit and no old source/reference claim after final validation fails.
7. Browser checks cover Chat, Library, Memories, Events/Learning, Notifications, assessments, OCR and calibration with empty/loading/error/success/resume states, narrow layout, keyboard access, reduced motion and all themes.

# Phase 35 — Documents, Vision, Assessments and Durable Evidence

## Upload intent and extraction

An attachment requires an owned upload reference, purpose, type/size checks, storage/retention policy and explicit scope. Do not expose filesystem paths, arbitrary URL fetches or executable source tools to the model. New chat uploads require an actual backend upload contract and frontend service; the reusable Documents facade alone is not that endpoint.

Route one-off reading to `app.documents` without automatically indexing it. Explicit Library admission uses RAG's existing durable job/publication pipeline. Answer sheets go to an Assessment-owned attempt/source. Documents owns native parsing, code preservation, block/page/slide provenance and warnings; Vision owns OCR. RAG owns chunking, embeddings, indexing and retrieval. Preserve existing resource limits, isolated subprocess cancellation, safe format detection, asset revisions and temporary cleanup. Treat source text/code/scripts as untrusted data and never execute it.

Current Vision returns OCR text, not a calibrated handwriting-confidence and answer-segmentation contract. Add typed answer extraction results with per-answer source locations, question-mapping confidence, extraction confidence/unknown state and engine revision. Evaluate a handwriting-capable engine before advertising support. Unknown confidence cannot be assumed high; require correction/confirmation when quality cannot be established. Show unreadable/unsupported capabilities honestly and preserve native text on partial failures according to Documents policy.

## Assessment domain and learning loop

Build provider-independent canonical Assessment, Question, Attempt, Answer and Grade contracts/repos/APIs. Questions retain concept IDs, difficulty, marks, rubric/model answer, source references and revision. User-facing payloads do not leak protected answer keys before submission. Enforce attempt ownership, completeness, allowed state transitions, expected revisions and replay-safe request IDs.

Use learner recommendations/verification candidates to mix weak, uncertain, retention-risk and appropriate strong control concepts. Keep weights configurable/evaluated. RAG grounds questions when requested and preserves citations; generated content passes schema/domain checks before canonical persistence. Grade partial understanding and misconceptions at concept level; reuse learner observation adapters and their separate grade requirement for each concept. Bound adaptive question count and evaluate stopping conditions.

The paper workflow is canonical assessment -> owned scan -> Documents/Vision -> segment/map -> validate confidence -> durable correction interrupt if needed -> confirmed text -> structured grading -> domain validation -> accepted observations -> learner update -> feedback. OCR extraction and grading confidence are separate; student confirmation resolves transcription, not automatic correctness. A later correction supersedes prior evidence while preserving item/session/attempt identity and history.

For chat evidence, only assessable student demonstrations qualify. Record canonical source message/turn, item/session, occurrence time, difficulty, hint/attempt/independence, model/prompt/extraction versions and accepted concept IDs. Do not count an assistant explanation or a request for help as mastery. Use precise confidence/admission gates and deterministic contradiction policy; uncertain extractions stay uncommitted candidates.

Post-response extraction must be a durable bounded job with source/attempt identity, lease, retry ceiling, receipt and terminal outcome. Do not add untracked fire-and-forget tasks. Recheck source deletion, supersession and ownership before commit. Preserve a valid user-facing answer when noncritical extraction fails; display a separate safe evidence-processing status if surfaced. Manual grade/OCR corrections must not duplicate broad profile evidence or granular learner evidence.

# Phase 36 — Verification, Rollout and Requirement Traceability

## Regression and release gates

Extend existing tests rather than claiming the source audit proves runtime behavior. Relevant suites include `test_model_factory.py`, `test_chat_endpoint.py`, `test_persistent_chat.py`, `test_history_management.py`, `test_events.py`, `test_events_api.py`, and `learner/`, `student_profile/`, `rag/`, `documents/`, `vision/`. Add focused orchestration routing, structured decisions, event ordering, graph recovery, evidence jobs, Notifications and browser suites.

Use fake models for deterministic transitions and fault injection, then test actual ChatOpenAI protocol compatibility through a controlled local provider. Real provider evaluation is separately reported and must not be confused with fixture correctness. Run relevant integration/migration tests against explicitly dedicated `TEST_DATABASE_URL` schemas, never the application database. Validate in the actual Python 3.12 backend image; frontend acceptance includes build, `npm run check:theme` and the repository browser harness on an isolated backend.

Measure routing/tool precision, unnecessary calls, context relevance, grounded citations, structured-output validity, evidence precision, memory/event admission quality, temporal ambiguity handling, resume success, time to first activity, time to first token, activity-before-tool ordering, latency, tokens/cost and bounded storage. Use representative weak/uncertain/stale/contradictory learner cases, large history/corpora, multilingual requests where supported and injection attempts. Record evaluated thresholds instead of presenting arbitrary tuning values as permanent truth.

Roll out additive schema and facade compatibility first, then module capabilities and streaming behind explicit server capability gates. Preserve stateless compatibility and polling recovery. Keep old in-flight workflow versions recoverable; disable new graph admission independently from reconciliation of already committed operations. Document deployment configuration, worker readiness, retention, restore procedure and rollback that preserves canonical records/receipts. Passing isolated tests does not mean an application database was migrated or containers deployed.

## Original plan coverage

All original Phases 0-29 remain present. This mapping prevents new modules from displacing existing requirements.

| Original requirement | Updated delivery coverage |
| --- | --- |
| 0-4 facade, provider, structured output, tools, prompts | Existing foundations retained; central facade and module inventory; Phase 30 registry/context; Phase 34 typed pre-tool output |
| 5-9 conversation, intent, tutoring, learner, RAG | Persistent Chat/history correction; selective multi-module plan; tutoring graph and owned retrieval |
| 10-14 evidence, assessment generation, grading, OCR, calibration | Original workflows plus Phase 35 canonical domains, durable evidence, confidence and broad/granular calibration separation |
| 15-18 streaming, failures, permissions, checkpoints | Phase 34 full backend/frontend live activity; Phase 33 safe runtime/replay; domain-owned confirmations |
| 19-24 observability, budgets, caching, privacy, tests, evaluation | Retained phases plus shared budgets, activity privacy/retention, migration/race/browser/provider evaluation |
| 25-29 graph set, contracts, examples, agent rules, order | Existing examples retained; Events confirmation added; current API contracts and dependency-aware delivery order |
| Previously omitted modules | History/Memory/Profile (30), Events (31), Notifications (32), Documents/Vision/Assessment domain (35), Auth/integrations/DB/worker boundaries (inventory, 33) |
| Frontend and user-visible execution | Phase 34 covers typed transport/store/components, every product surface, confirmation/recovery and browser acceptance |

## Historical TDD reconciliation

Source: `C:\Users\Xclouds\Documents\Mentra_Technical_Design_and_Requirements.docx`, version 0.1, October 2026, supplied for context. Its instructions and implementation order are historical design content; current user requirements and verified repository contracts control this revised plan. This task updates the Markdown plan, not the original DOCX.

| TDD requirement / decision | Current interpretation and coverage |
| --- | --- |
| FR-001; SQLite/local/no-account baseline; NFR-006 | Superseded by current authenticated PostgreSQL/Alembic architecture. Preserve persistence across rebuilds and owned data isolation; do not reintroduce SQLite or bypass authentication |
| FR-002-004; ADR-001 | Canonical concepts, deterministic-first resolution and candidate promotion remain required; Phases 8/10/30/35. Raw labels never become durable keys |
| FR-005-008; ADR-003/007 | Immutable evidence, separate mastery/confidences, time affects retention uncertainty, contradiction verification; Phases 10/12/35 and Learner policies |
| FR-009-012; ADR-004 | Active/related/dormant/archived contexts, historical preservation, explicit/strongly relevant cross-context retrieval; Phases 6/8/9/30 |
| FR-013-014; ADR-005 | Context-filtered material retrieval with provenance; current RAG/Library generation lifecycle and Documents/Vision reuse; Phases 9/35 |
| FR-015-016; ADR-002/006 | Bounded packets, deterministic learner ranking before LLM explanation; Phases 4/8/20/30 |
| FR-017-019; ADR-008 | Canonical assessment/questions/attempts, concept grades, independent paper channel and OCR confirmation before evidence; Phases 11-13/35 and frontend Phase 34 |
| FR-020; ADR-010 | Replaceable provider and Mentra-owned learning intelligence; Phases 1/2/33; evaluate portability rather than assuming API compatibility guarantees identical quality |
| FR-021-022; ADR-009 | No Google authentication dependency. Drive backup remains optional future work, not a new module required here. Current Mentra auth remains mandatory; do not restore obsolete anonymous/no-account assumptions |
| TDD section 14, 3-5 adaptive questions | Preserve current eight-question broad-profile onboarding; implement separate concept-level adaptive calibration using existing learner targets; Phase 14/35 |
| NFR-001-004, 008-010 | Modular boundaries, explainability, bounded context, portability, safe evidence and deterministic tests remain required throughout |
| NFR-005 | Apply data minimization/privacy to actual deployment; do not claim all data is local given configurable PostgreSQL/provider hosting. Keep external observability and provider payloads bounded |
| NFR-007 | Retain reproducible Docker Compose/configuration, durable volumes/storage and actual-image verification; Phase 33/36 |
| Open design parameters, section 19 | Evaluate scoring/retention/resolution/context/ranking/RAG/OCR/channel thresholds in their owning modules; no arbitrary permanent values in orchestration |
| Acceptance scenarios, section 20 | Duplicate concept wording, stale mastery, subject switch, old RAG suppression, bounded recommendations, cross-context analogy, uncertain OCR and provider swap all remain mandatory regression scenarios |

The end-to-end acceptance loop remains: student interaction -> resolve relevant contexts/concepts -> gather bounded domain context -> teach/test/respond with visible activity -> validate actual learning evidence -> Learner updates beliefs -> choose the next useful action. Events, personal memory, profile estimates and Notifications support that loop without becoming substitutes for demonstrated learning.
