# Mentra LangChain + LangGraph Module â€” Full Implementation Plan

**Status:** Architecture plan aligned to the current implementation; workflow phases below remain planned unless explicitly marked implemented.
**Audience:** Human developers and AI coding agents
**Scope:** LangChain + LangGraph orchestration module
**Relationship:** This module coordinates AI, Learner Engine, RAG, assessments, and other Mentra capabilities. It does not take ownership of those domains.

---

# 1. Objective

Implement a reusable orchestration module that acts as Mentra's AI-facing coordination layer.

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
- managing short-lived workflow state;
- handling retries, timeouts, tool failures, and fallbacks;
- using LangGraph where workflows require explicit state, branching, resumability, or human confirmation.

Core rule:

> **LangChain/LangGraph orchestrates Mentra's modules. It does not become the owner of their data or business rules.**

---

# 2. Architectural Role

```text
Frontend
   â†“
FastAPI / API
   â†“
LangChain + LangGraph Orchestration
   â”œâ”€â”€ Learner Engine
   â”œâ”€â”€ RAG Engine
   â”œâ”€â”€ Assessment Engine
   â”œâ”€â”€ Answer Sheet / OCR
   â””â”€â”€ LLM Provider(s)
```

Preferred dependency direction:

```text
LangChain/LangGraph
       â†“
domain service interfaces
       â†“
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
    â†“
resolve intent/context
    â†“
load learner context
    â†“
retrieve RAG
    â†“
generate response
    â†“
extract learning evidence
    â†“
validate/resolve concepts
    â†“
submit evidence
```

---

# 4. Recommended Module Structure

Adapt naming to existing repository conventions.

The current implementation is intentionally smaller than this target structure. Extend the existing modules before adding new layers: `app/langchain/model_factory.py`, `app/langchain/llm.py`, `app/langchain/prompts/`, `app/langchain/chat_service.py`, `app/langchain/profile_evaluator.py`, and `app/langchain/learner_tools.py`. Do not create parallel provider/model/context abstractions that duplicate these responsibilities. LangGraph itself and the orchestration facade are not implemented yet.

```text
backend/app/langchain/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ model_factory.py          # Current OpenAI-compatible provider factory
â”œâ”€â”€ llm.py                    # Shared MentraLLM invocation and output validation
â”œâ”€â”€ prompts/                  # Separate versioned prompt modules + trusted registry
â”œâ”€â”€ chat_service.py           # Current simple chat workflow
â”œâ”€â”€ profile_evaluator.py      # Current structured broad-profile evaluation
â”œâ”€â”€ learner_tools.py          # Current learner-engine tool adapters
â””â”€â”€ ...                       # Add graph/facade modules only as workflows require them
```

Do not create unused folders merely to match this tree. Preserve the boundaries as features are implemented.

---

# Phase 0 â€” Contracts and Module Skeleton

## Goal

The initial model and prompt boundary already exists. Complete this phase by adding a stable orchestration facade only when more workflows need it; do not replace the working chat/profile service contracts prematurely.

## Tasks

1. Reuse the existing LangChain package and service boundaries.
2. Introduce an `OrchestrationService` only when a stable cross-workflow API is needed.
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
```

FastAPI should call this facade rather than constructing chains/graphs inside routes.

### Current status

- Implemented: FastAPI route delegates chat to `ChatService`; it does not contain prompt text or instantiate provider clients.
- Implemented: startup creates one `MentraLLM` and injects that same invocation component into chat and Student Profile evaluation.
- Implemented: `ModelFactory` constructs the configured OpenAI-compatible chat client, with configuration validation and bounded retry/timeout settings.
- Implemented: source-specific prompt modules (`chat`, `learner_context`, `student_profile_evaluation`) own prompt versions, and trusted services select their `PromptSource`.
- Implemented: `MentraLLM` composes registered instructions/context, supports structured output, and validates results.
- Implemented: learner tool adapters bind `learner_id` from authenticated server scope.
- Planned: facade, LangGraph graphs, RAG search/ingestion tools, streaming, graph persistence, and the richer workflows described below.

### Remaining acceptance criteria

- API routes contain no prompt logic.
- API routes do not instantiate LLMs directly.
- Domain modules do not import LangGraph.
- Provider can be changed through configuration.

---

# Phase 1 â€” LLM Provider Abstraction

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

The existing `MentraLLM` receives the trusted `PromptSource` for each invocation. Prompt source answers â€œwhere did this request come from?â€ and is selected by service/graph code, never by HTTP input or model output. Model purpose is a separate concern; add purpose-aware model selection only when workloads need different model configurations. If introduced, keep all model construction and invocation behind the same `MentraLLM` component.

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

# Phase 2 â€” Structured Output Layer

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
        â†“
schema validation
        â†“
concept resolution
        â†“
domain validation
        â†“
Learner Engine submit_evidence()
```

If output remains invalid after bounded retry, skip the durable mutation and preserve the user-facing interaction where possible.

---

# Phase 3 â€” Tool Layer

## Goal

Expose Mentra capabilities without leaking domain internals.

## Learner tools

Read tools:

```text
get_active_learning_contexts
get_relevant_learner_context
get_study_recommendations
get_verification_candidates
resolve_concept
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
search_learning_material
get_document_context
get_source_details
```

RAG performs retrieval. LangChain tools are adapters.

## Assessment tools

Possible adapters:

```text
get_assessment_targets
create_assessment_request
submit_assessment_evidence
```

Each tool must have a narrow purpose, typed input/output, domain-service call, minimal returned data, clear errors, and independent tests.

---

# Phase 4 â€” Prompt Architecture

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

Dynamic learner state comes through ``app.learner.engine.LearnerEngine.get_relevant_context(...)``.

RAG context comes through the RAG service.

## Prompt budgets

`ContextBuilder` should enforce independent budgets for system instructions, conversation history, learner context, RAG, and tool results.

If compression is needed, remove low-value context before damaging the current user request.

---

# Phase 5 â€” Conversation Context

## Goal

Separate conversation memory from long-term educational memory.

Conversation history answers:

> What have we been discussing in this chat?

Learner Model answers:

> What does Mentra believe this student knows?

They are not interchangeable.

The existing `/api/v1/chat` currently accepts in-memory conversation messages; it does not persist chats or provide summaries. Add explicit history limits before expanding this contract. Initially use bounded recent messages plus an optional compact conversation summary.

Do not replay unlimited history.

LangGraph checkpoints are workflow execution state, not automatically the canonical conversation database.

LangChain/LangGraph memory must never replace the Learner Engine.

---

# Phase 6 â€” Intent and Request Planning

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

# Phase 7 â€” Core Tutoring LangGraph

## Goal

Implement Mentra's primary adaptive conversational workflow.

```text
START
  â†“
prepare_request
  â†“
resolve_intent_and_context
  â†“
load_learner_context_if_needed
  â†“
retrieve_RAG_if_needed
  â†“
build_model_context
  â†“
generate_answer
  â†“
response_available
  â†“
extract_learning_evidence_if_assessable
  â†“
validate_and_resolve
  â†“
submit_evidence
  â†“
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

# Phase 8 â€” Learner Context Integration

For relevant requests:

```text
query
  â†“
`LearnerEngine.get_relevant_context(...)`
  â†“
compact LearnerContextPacket
  â†“
ContextBuilder
  â†“
LLM
```

The LLM should receive only relevant concepts, misconceptions, and state.

For `What should I study?`, call ``LearnerEngine.get_study_recommendations(...)`` and let the LLM explain the result. Do not ask the LLM to scan the entire learner model.

---

# Phase 9 â€” RAG Integration

## Goal

Use RAG as a domain service rather than scattered retriever calls.

```text
user query
    â†“
resolved learning context
    â†“
RAGService.search(query, context_ids, concept_ids, ...)
    â†“
ranked chunks + provenance
    â†“
ContextBuilder
```

Prefer active material, then related material. Dormant material is used only when explicitly or strongly relevant; archived material only when requested.

RAG output should preserve content, document/source ID, chunk ID, relevance information, context ID, and citation metadata.

If RAG finds nothing, do not fabricate source-grounded claims.

---

# Phase 10 â€” Evidence Extraction Workflow

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
    â†“
is assessable?
    â†“
structured evidence extraction
    â†“
concept resolution
    â†“
confidence checks
    â†“
`LearnerEngine.submit_evidence(...)`
```

Raw LLM labels never become learner keys.

---

# Phase 11 â€” Assessment Generation Workflow

Recommended flow:

```text
START
  â†“
resolve requested context/scope
  â†“
Learner Engine:
  recommendations + verification candidates
  â†“
Assessment Engine:
  construct assessment specification
  â†“
LLM:
  generate question content
  â†“
structured validation
  â†“
Assessment Engine:
  persist canonical assessment
  â†“
END
```

The Assessment Engine owns assessment records. Learner Engine owns targeting. LLM generates language/content.

Every persisted question should map to canonical concept IDs, difficulty, marks, rubric/model answer, and question type.

This can begin as a service/chain and become a graph when branching/state justifies it.

---

# Phase 12 â€” Grading Workflow

```text
student answer
    â†“
load canonical question/rubric
    â†“
grade with structured output
    â†“
validate grade
    â†“
map concept-level performance
    â†“
submit evidence to Learner Engine
    â†“
generate feedback
```

Structured grading should support score, max score, concept-level results, misconceptions, grading confidence, and feedback points.

Do not reduce every result to correct/incorrect.

---

# Phase 13 â€” AnswerSheetGraph: OCR + Human Confirmation

This is a strong LangGraph use case.

```text
START
  â†“
load uploaded answer sheet
  â†“
OCR / segmentation
  â†“
OCR confidence check
  â”‚
  â”œâ”€â”€ high confidence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚                              â”‚
  â””â”€â”€ low confidence             â”‚
          â†“                      â”‚
      INTERRUPT                  â”‚
          â†“                      â”‚
 student confirms/corrects       â”‚
          â†“                      â”‚
       RESUME                    â”‚
          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                     â†“
                grade answers
                     â†“
              submit evidence
                     â†“
                    END
```

This workflow benefits from explicit state, branching, persistence, interruption, and resume.

Never update learner state before confirmation when OCR confidence is insufficient.

---

# Phase 14 â€” CalibrationGraph

## Goal

Implement adaptive first-run calibration across multiple turns.

```text
START
  â†“
collect minimal study context
  â†“
choose initial target
  â†“
ask question
  â†“
WAIT FOR USER ANSWER
  â†“
evaluate
  â†“
submit evidence
  â†“
choose next target based on uncertainty
  â†“
repeat until stopping condition
  â†“
complete calibration
```

Do not hard-code the entire sequence in advance. Learner Engine should influence target selection.

---

# Phase 15 â€” Streaming

Support token/event streaming from orchestration to FastAPI/frontend.

Potential event types:

```text
response_start
content_delta
tool_started
tool_completed
citation/source
response_completed
error
```

Never expose internal chain-of-thought.

High-level UI activity may say things like `Searching your study materialâ€¦` or `Checking your learning progressâ€¦`, not raw reasoning.

---

# Phase 16 â€” Failure Handling

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

# Phase 17 â€” Guardrails and Tool Permissions

Categorize tools:

```text
READ
SAFE_MUTATION
SENSITIVE_MUTATION
```

Sensitive mutations such as learner evidence or finalized grading should happen through explicit validated workflow nodes rather than unrestricted agent behavior where possible.

Do not give the model generic database or filesystem access.

---

# Phase 18 â€” Graph Persistence and Checkpointing

Use persistence for workflows that genuinely need pause/resume/recovery:

```text
multi-turn calibration
OCR confirmation
long assessment workflows
human confirmation/approval
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

# Phase 19 â€” Observability

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

# Phase 20 â€” Token and Context Budgeting

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

# Phase 21 â€” Caching

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

# Phase 22 â€” Security and Privacy

Before external LLM calls, send only required learner fields and RAG chunks.

The model often needs:

```text
"Recursion: low mastery; repeatedly confuses the base case"
```

not the student's entire history.

Uploaded material should be sent externally only when required by the operation and allowed by Mentra's privacy configuration.

---

# Phase 23 â€” Testing Strategy

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
chat â†’ learner context â†’ LLM
chat â†’ RAG â†’ LLM
student answer â†’ evidence extraction â†’ Learner Engine
recommendation request â†’ Learner Engine â†’ response
assessment request â†’ targeting â†’ generation
OCR low confidence â†’ interrupt â†’ confirmation â†’ grading
calibration across multiple turns
```

## Failure tests

Explicitly test LLM timeout, invalid structured output, RAG timeout, learner errors, tool exceptions, graph resume, duplicate requests, and cancelled streams.

---

# Phase 24 â€” Evaluation

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

# Phase 25 â€” Initial Graph Set

Do not create dozens of graphs.

Recommended initial set:

```text
1. TutoringGraph
   Main adaptive conversational learning workflow

2. CalibrationGraph
   Multi-turn adaptive onboarding

3. AnswerSheetGraph
   OCR â†’ confirmation interrupt â†’ grading â†’ evidence

4. AssessmentGenerationGraph
   Add when assessment generation develops meaningful branching/state

5. GradingGraph
   Add when grading develops meaningful branching/state
```

Assessment generation and grading may initially remain ordinary orchestration services/chains.

---

# Phase 26 â€” Integration Contracts

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

Expected conceptual interface:

```python
search(query, context_ids=None, concept_ids=None, limit=...)
get_source(...)
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

# Phase 27 â€” Request Flow Examples

## Explain a concept

```text
"Explain transitive dependencies again."
        â†“
TutoringGraph
        â†“
resolve concept/context
        â†“
Learner Engine â†’ relevant learner context
        â†“
RAG â†’ active Database Systems material
        â†“
LLM â†’ personalized explanation
        â†“
no mastery evidence merely because the student requested an explanation
```

## Student answers

```text
Mentra: "Why does this violate 3NF?"
Student: "Because a non-key field depends on another non-key field."
        â†“
response generation
        â†“
evidence extractor
        â†“
structured candidate evidence
        â†“
concept resolution
        â†“
Learner Engine submit_evidence()
```

## What should I study?

```text
request
  â†“
intent = STUDY_RECOMMENDATION
  â†“
`LearnerEngine.get_study_recommendations(...)`
  â†“
top relevant recommendations
  â†“
LLM explains naturally
```

No full learner-model dump.

## Old knowledge becomes relevant

```text
Current context: Python

"Is a Python dictionary like a database table?"
        â†“
Python = active
Database Systems = explicitly relevant dormant context
        â†“
Learner + RAG retrieve both selectively
        â†“
LLM produces cross-context explanation
```

---

# Phase 28 â€” Agent Implementation Rules

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

# Phase 29 â€” Implementation Order

```text
1. Module skeleton + orchestration facade
2. Provider factory/configuration
3. Structured-output schemas
4. Tool adapters + registry
5. Prompt/context builder
6. Conversation-context strategy
7. Intent/planning
8. Basic non-graph chat path
9. Learner Engine integration
10. RAG integration
11. TutoringGraph
12. Evidence extraction + submission
13. Streaming
14. Failure/degraded-mode routing
15. Recommendation flow
16. Assessment generation workflow
17. Grading workflow
18. CalibrationGraph
19. AnswerSheetGraph with interrupt/resume
20. Graph persistence/checkpointing where required
21. Observability/tracing
22. Token budgeting
23. Caching/invalidation
24. Security/privacy pass
25. Full integration/evaluation suite
```

Each phase requires implementation, typed contracts, unit tests, relevant integration tests, and documentation of new public behavior.

---

# Architectural Invariants â€” Do Not Violate

1. **LangChain/LangGraph is orchestration, not the owner of domain truth.**
2. **Learner Engine owns learner identity, evidence policy, mastery, retention, and context lifecycle.**
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
- the configured LLM can be swapped without rewriting workflows;
- tutoring requests selectively retrieve learner context;
- RAG retrieval is context-aware and provenance-preserving;
- general recommendations come from the Learner Engine rather than an LLM scan;
- assessable student responses can produce validated learner evidence;
- non-assessable questions do not create fake mastery evidence;
- adaptive assessments consume learner recommendations/verification candidates;
- grading produces structured concept-level evidence;
- low-confidence handwritten OCR can pause and resume through confirmation;
- first-run calibration can span multiple adaptive turns;
- streaming works without exposing hidden reasoning;
- graph state is bounded and does not duplicate domain databases;
- failures have explicit degraded/error paths;
- prompts have bounded learner/RAG/conversation context;
- model/tool calls are observable and testable;
- fake models allow deterministic graph tests;
- no external module is bypassed through direct database access;
- Mentra's learner intelligence remains intact when the LLM provider changes.

At that point LangChain/LangGraph is doing exactly what Mentra needs: **connecting the intelligence of the system without becoming the intelligence of every subsystem itself.**
