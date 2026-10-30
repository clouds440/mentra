# LangChain and chat models

`ModelFactory` is the Mentra-owned entry point for provider model construction. `MentraLLM` is the shared request/invocation component used by chat and structured Student Profile evaluation. Every invocation supplies an internal `PromptSource`; that closed enum selects the relevant prompt module. HTTP input cannot choose a prompt source. Optional response schemas are validated in this same component.

Keep system instructions in a source-specific module under `prompts/`. Each module owns its prompt version; `prompts/registry.py` maps `PromptSource` to both the prompt and version. Add a new source and prompt module together, then route its service through the shared `MentraLLM`. Chat uses `chat`; profile evaluation uses `student_profile_evaluation`; granular learner context is an additional registered source fragment. The `/api/v1/chat` API accepts in-memory conversation history and returns one assistant message; it does not persist or stream the conversation.

Application startup creates one `MentraLLM` instance and injects it into chat and the profile evaluator. Each workflow chooses its source in trusted server code. The common component resolves instructions, constructs ordered LangChain messages, binds structured output when requested, and validates the result. Provider construction remains in `ModelFactory`; evidence validation and persistence remain in Student Profile services.

The current adapter is `openai_compatible`. Configure `AI_MODEL`, `AI_BASE_URL`, and `AI_API_KEY` for the chosen endpoint; changing those values is sufficient to switch among compatible services such as OpenAI, DeepSeek, and Groq. `AI_TEMPERATURE`, `AI_TIMEOUT`, and `AI_MAX_RETRIES` tune request behavior. No provider URL or model name is hard-coded.

DeepSeek uses the same OpenAI-compatible adapter. Add another adapter only when a provider has an actual API incompatibility.

Model configuration is checked when the model is requested and reported separately by readiness. Missing AI credentials do not prevent the backend from starting, so chat requests can return an actionable configuration error. Validation does not make a paid model request; an explicit caller must invoke the model to do that.

Embeddings are a separate RAG component and are not selected by or sent through the chat provider.

Persistent clients use `/api/v1/conversations/turns`; the older `/api/v1/chat`
endpoint is deprecated and stateless. Canonical transcripts and durable attempts
belong to `app.chat`. On-demand history/memory tools use `app.history_management`
with server-bound ownership and shared execution budgets; they do not replace the
stored transcript. See [persistent chat](../../../docs/chat/persistent-chat.md) and
[history management](../../../docs/memory/history-management.md).

The bounded LangGraph coordinator selects domain tools, shares a parent model
deadline, and uses `ToolExecutor` for public activity updates and recovery. Event
proposals and assessment tools retain domain-owned validation and persistence.

Assessment generation repairs malformed target/question output once before saving,
under the existing shared budget. Learner semantic advice is optional: adapter
failures become `ConceptAssistanceUnavailable`, allowing deterministic identity
resolution to continue. Neither invalid advice nor a missing exact concept match
requires another student turn. See [assessment workflow](../../../docs/assessments/chat-assessments.md).

Preparation validates explicit source ownership and eligibility without speculative
embedding/search calls. Only an agent-requested `search_study_material` call delivers
evidence, after the RAG service revalidates current source eligibility. Tool discovery
remains available for missing capabilities; general and self-contained queries can
answer directly. Current high-level profile preferences are read for every request.
Chat renders the agent's answer without automatic tool/RAG/web limitation banners.

`capabilities.py` owns the configured tool catalog. The main response model selects
operations semantically from recent conversation and concrete owned references; no
keyword router or direct-answer approval runs. A lean core is available without
executing it. Larger tools/UI references use bounded discovery, which drops unused
default schemas and reserves the requested domain instructions before admission.
Old keyword-policy comparisons live under `backend/testing/legacy_*` only.

`FinishResponse`, `task_outcomes.py` and receipt validation separate graph termination
from fulfillment. Ordinary replies need no receipt. Requested operations need actual
matching receipts; queued work is in progress, native questions await input, and
unfinished work remains partial/failed with useful content preserved. History/status
batch-project owner-scoped generation/grading states and expose the correct control.
Private write receipts survive read-context replacement; unknown writes cannot be
retried with altered arguments. Recovery data expires with the response's 30-minute
window. Graph checkpoints and canonical domain operation IDs remain authoritative.

Completed visible assessment handoffs are resolved in one bounded query returning
only IDs, title and question count. Follow-ups use those identities without searching
for the assessment again or prefetching its full questions. See the
[semantic migration and latency plan](../../../docs/orchestration/Mentra_Semantic_Tool_Orchestration_Migration_Plan_2026-10-28.md).

Ordinary practice defaults to native interactive delivery. Explicit written and
printable delivery remain available independently of question type. Compact schemas
cover ordinary generation; advanced paper structure is discoverable separately.
Eligible small requests use deterministic structure and one validated content stage,
preserving grading/concept checks. Durable public card references can appear before
final narration; activity never carries answer keys or arbitrary generated UI code.

Optional `web_search(query, website?, refresh=false)` is available independently of history and
RAG when enabled. The domain facade owns provider I/O and shared operational quota;
the LangChain adapter stages W references until the coordinator admits the exact
bounded result packet. Web calls never retry automatically. Cached results retain
their retrieval time and receive a fresh current clock. Historical W markers are
renamed only in prompt projections. `web_search` is a versioned prompt fragment.
Validated website origins supply activity badges and optional favicons. See
[web search](../../../docs/web-search/web-search.md).

Authenticated `web_research` is a separate bounded tool enabled by the backend's
`YOU_WEB_SEARCH_API_KEY`; ordinary search keeps its keyless free MCP transport.
Private chat summaries and answering budgets are documented in
[context compaction](../chat/SUMMARIES.md). Upfront semantic event capture uses
the Events facade before answering; it does not authorize unsolicited practice.

Model/tool calls participate in correlated metadata-only traces. Logs record
timing, parameter presence/types/counts and sanitized outcomes, not query or
response bodies. See [logging](../../../docs/observability/backend-logging.md).

## Prompt size and provider caching

Visible artifact edits load the conditional `response_edit` contract and retain the
complete target during budgeting. Compatible assessment revisions reuse accepted
structure/items; explicit `question_numbers` limit generation to changed questions.
Private keys remain service-owned, originals/attempts remain immutable, and new or
changed content retains validation. See [follow-up edit optimization](../../../docs/orchestration/Followup_Edit_Optimization_2026-10-27.md).

The universal chat contract stays in `prompts/chat.py`. Detailed assessment routing
uses `chat_assessment`, activated with bound/discovered assessment tools or existing
assessment context and retained through finalization. The coordinator includes the
same fragments when checking schema admission and constructing provider requests.

Assessment content generation uses `GeneratedAssessmentBatch`; public assessments
still use `GeneratedAssessment` with server-owned paper structure. Shared request,
learner and source data precedes changing batch data. Overviews cover only other
batches; full current-batch original questions and grounding excerpts are retained.

DeepSeek's automatic prefix cache still requires sending instructions/context.
Cache-aware adapter normalization preserves provider cache counters for streaming
and buffered calls. `model.usage` records actual input/output/total counts when
available, `cached_tokens`, `uncached_tokens`, and `token_estimate_method`.
`cl100k_base` is a local estimate; `utf8_byte_bound` means the verified vocabulary
was unavailable. Neither should be confused with actual provider usage. Docker
bakes its vocabulary; native runs can set `TIKTOKEN_CACHE_DIR` to the existing
`backend/.cache/tokenizers` folder when available. No request-time download occurs.

See [prompt efficiency and verification](../../../docs/orchestration/prompt-efficiency.md) for
measurements, live synthetic comparisons, caching semantics and limitations.
