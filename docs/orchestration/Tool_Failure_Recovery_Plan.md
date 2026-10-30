# Tool failure and recovery fix plan

Revised: 11 October 2026. Status: fixes applied in this checkout; final validation and implementation notes appear below. The numbered sections retain the original problems and acceptance criteria for review.

This plan prioritizes observed defects in tool resolution, execution, reporting, and recovery. Small additions are included where the current code needs them to resolve those defects. Each item specifies the problem, a targeted change, and the check that demonstrates the fix.

## Optimization requirements applying to every fix

The objective is accurate, necessary tool use with fewer unnecessary LLM calls, dependency reads, and repeated executions. Recovery must not introduce routine planner/classifier/critic calls that cost more than the work they avoid.

- Reuse the first necessary chat-model invocation for choosing tools or returning the final answer. A clearly general accepted answer should take one logical model invocation and zero domain calls, including its first-turn title. SDK transport retries are counted separately.
- Use deterministic server checks and a compact capability description for routing eligibility. Explicit LLM approval of no-tool answering must be part of that same response, not a separate confidence-check request.
- Defer optional context reads until the request or selected capability needs them. Reuse supplied context and successful request-local results; do not fetch the same learner/profile/source packet both before the model and again through a tool.
- Retry an eligible dependency inside its invocation helper without another model round between attempts. Generate retry/status messages from server state; never invoke an LLM just to explain retry progress.
- Extra model calls are allowed only for necessary tool-result synthesis, a real newly discovered dependency, or bounded repair of an actual failed response. No routine verification, reflection, reclassification, or second answer-writing call after an accepted final answer.
- Measure logical model invocations, provider attempts, actual dependency executions, cache hits, schema/input tokens, and time to a useful answer in the focused regression cases. A reduction in tool executions that increases routine model calls is not an acceptable optimization.

## Priority 1: fix incorrect outcomes and unnecessary response failures

### 1. Preserve successful actions when activity reporting fails

**Problem:** Activity publication is awaited inside tool execution. A completion-event error after a successful action can replace its saved receipt with an unavailable result saying “Nothing is confirmed.” A mocked probe reproduced this reporting path.

**Fix:** Separate the action result from progress-publication errors. Preserve a confirmed domain receipt even if its completion event cannot be written. Reuse existing operation IDs and domain receipt lookups when an outcome needs verification. Keep stale-attempt, expired-attempt, and deleted-conversation checks authoritative; do not swallow those errors as ordinary reporting outages.

**Locations:** `backend/app/langchain/activity.py`, `tool_activity.py`, `history_orchestration.py`, and `backend/app/chat/repositories/activity.py`.

**Verify:** A saved action followed by an activity sink failure remains saved in the model receipt and final response. Retrying does not duplicate it. An expired or deleted turn still cannot execute/publish protected work.

### 2. Stop marking unsuccessful tool results as completed

**Problem:** A tool returning `outcome=unavailable`, rejected, or `answer_preparation_failed` finishes normally and is marked completed. Logging also defaults several non-success domain outcomes to success.

**Fix:** Map the existing returned outcome/status to its actual business result before emitting terminal activity or logging it. Distinguish successful execution, partial completion, unavailable capability, rejected action, and awaiting confirmation. Preserve saved assessment/attempt identifiers when answer extraction fails; report the extraction failure without reporting the whole assessment as lost.

**Locations:** `tool_activity.py`, `activity.py`, `history_orchestration.py`, `workflow_tools.py`, and `frontend/src/components/chat/ChatActivity.tsx`.

**Verify:** Returned failure outcomes produce accurate activity and logging. “Assessment saved; extraction failed” retains the recovery card and never claims grading completed.

### 3. Let optional context failures reach an answer

**Problem:** Learner/profile reads, attachment extraction, and recent-assessment lookup can throw before the LLM is called. Recent assessments are fetched whenever the service and scope exist, even when the request does not need them. The planner's `required` flag is not consumed by orchestration.

**Fix:** Catch classified dependency failures around optional preparation, record the missing context, and continue with available information. Preserve authorization, scope, lifecycle, and integrity failures as their own outcomes. Avoid or safely degrade unnecessary recent-assessment reads. Apply requiredness to the actual request: a general explanation can proceed without learner data; an exact uploaded-document summary cannot proceed without that document's content. An attachment being present alone does not make it essential.

**Locations:** `orchestration_service.py` and `planning.py`.

**Verify:** A profile/learner outage still allows a general explanation. A document outage blocks unsupported document-specific claims and produces a useful limitation message. Unrelated supported parts of a compound request can still be answered.

### 4. Retain actionable error information

**Problem:** Dispatch exceptions collapse into unavailable and lose AppError.code. The frontend has `Turn.error`, but chatStore replaces it with a generic failure message. The learner cannot reliably distinguish retryable outage, invalid input, missing information, confirmation, or conflict.

**Fix:** Add a small typed failure receipt to the current dispatch path: safe code/message, category, retryable flag, task impact, and effect certainty where relevant. Classify at least transient dependency/rate limit, invalid arguments, authorization, not found, revision conflict, confirmation required, budget exhaustion, and lifecycle cancellation/expiry. Render safe canonical `Turn.error` instead of replacing every error with the generic text. Keep a generic fallback for unexpected errors.

**Locations:** `history_orchestration.py`, existing error/activity contracts, `frontend/src/stores/chatStore.ts`, and chat failure rendering.

**Verify:** The LLM and learner receive appropriate next steps. Raw exception text, private arguments, credentials, and internal reasoning never become public messages.

## Priority 2: resolve failed calls predictably and continue safely

### 5. Add bounded retries for transient read failures

**Problem:** Tools have no shared automatic retry policy. Repeated calls depend on the model choosing them again, and the UI does not explain the retry.

**Fix:** Add a small reusable invocation helper used by current dispatch and the optional preparation reads. Retry only classified transient read failures. Start with an initial attempt plus at most two retries, short jittered delays, and a deadline check before each attempt. Honor Retry-After only when it fits the remaining budget. Keep successful read caches and ordered writes intact.

Two retries are an upper bound, not a target for every optional read. Use a smaller per-operation retry allowance when immediate general continuation is sufficient and another attempt would add little value. Perform these retries without returning to the model between attempts; deliver one terminal result for that logical tool call. Never ask the LLM whether to retry a classified transient error.

Count physical attempts consistently within the existing six-call limit; do not count the same attempt in both helper and wrapper. Keep the two-write limit. Do not retry invalid arguments, authorization errors, missing objects, required confirmation, stale attempts, or budget exhaustion as transient outages.

Model-provider HTTP requests already have two configured retries. Do not add another provider retry loop on top. Exposing those provider attempts through activity needs a verified client hook/adapter; if no suitable hook exists, keep the existing retry owner and treat exact provider-attempt visibility as a follow-up within this fix.

**Locations:** `history_orchestration.py`, `orchestration_service.py`, `history_management/budgets.py`, and a focused retry helper beside them. Provider visibility touches `model_factory.py`/`llm.py` only if necessary.

**Verify:** Transient reads recover within the limit; permanent failures do not retry; counters remain accurate; provider retries do not multiply with application retries.

### 6. Stop repeatedly selecting exhausted tools

**Problem:** The LLM can repeatedly request an identical failing tool until round/call limits intervene. There is no explicit exhausted-call state.

**Fix:** Track failed requests within the current turn by tool/action and normalized arguments. After permitted attempts are exhausted, return a compact prior-failure receipt without executing the same request again. A changed query can run only when it could remedy the failure; changing words should not bypass a known dependency outage. Keep successful independent capabilities available. If the remaining useful tools are exhausted, request a final answer using available evidence.

**Locations:** `history_orchestration.py` and existing request-local budget/cache state.

**Verify:** Repeating an exhausted request performs no additional dependency work. A genuinely corrected input can still succeed. One unavailable subsystem does not disable unrelated tools.

### 7. Improve unknown/disabled tool and argument resolution

**Problem:** Unknown and disabled tools both receive “Unknown tool.” Validation failures can happen before the announcement wrapper or budget counter. Malformed provider tool calls immediately fail the turn, without an opportunity for a safe correction.

**Fix:** Distinguish unknown capability, capability not enabled, invalid arguments, and malformed call protocol. Supply bounded, sanitized correction guidance based on the server's available tools and actual input schema. Reject calls outside authenticated scope. Enable another domain only through the existing authorized module-enabling path; do not indiscriminately register every adapter.

Allow at most one model correction for reparable call/schema errors within the existing round and time budgets, only after an actual invalid response. Reuse the next necessary model round to supply correction feedback where possible; do not run a separate validator/critic model. Count rejected/invalid attempts before execution so they cannot bypass admission limits. Never repair arguments by guessing IDs, user answers, consent, evidence, or ownership. Emit a failed/rejected activity update for pre-execution rejection, without implying the tool ran.

A mixed final-answer/pending-tool response still needs protocol validation. Do not simply publish its answer and discard unresolved actions. If it can be corrected safely, use the same bounded correction path; otherwise return a clear terminal failure.

**Locations:** `history_orchestration.py`, `tool_activity.py`, and tool selection/module-enabling code.

**Verify:** Unknown and disabled capabilities get distinct useful feedback. Correctable schema mistakes recover once. Unauthorized requests never execute. Invalid calls consume budgets and appear truthfully in activity.

### 8. Continue without tools only where the answer remains supported

**Problem:** Ordinary dispatch failures can reach the model, but there is no consistent rule connecting the missing tool to what the answer may still claim. Provider tool-binding fallback specifically warns about history/memory even when other capabilities are unavailable.

**Fix:** Pass the failed capability and its practical limitation into the existing final-answer context. Use a registered prompt fragment for recovery guidance. Update unsupported-tool-binding fallback to describe all relevant unavailable capabilities. Keep supported parts of the request and successful evidence; block only unsupported claims/actions. Do not present a guessed reliability percentage.

| Failed capability | Permitted continuation |
| --- | --- |
| Learner/profile personalization | General study help; disclose missing personalization when relevant. Never invent mastery or rankings. |
| History/memory recall | Use visible current context. Ask for a missing personal fact instead of inventing it. |
| Study retrieval for a general concept | General explanation with a clear grounding limitation. |
| Exact document content, quotation, or question lookup | Explain that the exact content could not be verified. General help must be clearly separated. |
| One independent action in a compound request | Answer supported parts and identify the unresolved action. |
| Mutation with unknown outcome | Explain that completion is unverified; no invented success or claim that nothing happened. |
| Grading/evidence processing | Preserve existing recovery controls; no invented grades or learner evidence. |

**Locations:** `orchestration_service.py`, `history_orchestration.py`, and registered prompt modules.

**Verify:** Optional failures produce useful limited answers. Required-source failures produce no fabricated citations/content. Tool-binding fallback does not claim that unavailable actions were performed.

### 9. Make write failures and manual retries truthful

**Problem:** Generic unavailable results cannot establish whether a write committed. A timed-out worker-thread operation may finish later. Retrying the whole turn does not undo earlier writes, and changed model arguments may describe a different operation.

**Fix:** Keep automatic write retries off unless the specific operation already has proven idempotency and receipt reconciliation. Reuse existing domain identifiers, fingerprints, revision checks, and receipts rather than introducing a new mutation framework. For unknown outcomes, check the operation receipt first; replay only when safe noncommit/replay behavior is established. Confirmed writes keep their saved receipt even if another part of the turn fails.

Preserve assessment versions, attempts, grading history, answer provenance, OCR confirmation, event review, and memory consent. Review whole-turn retry behavior for the current write tools so a retry does not silently repeat or reinterpret a completed action.

**Locations:** Current write adapters in `workflow_tools.py`, `event_tools.py`, `history_management/tools.py`, `chat/interactions.py`, and their domain receipt/replay paths.

**Verify:** A timeout after commit or manual response retry does not create a duplicate action. Unknown outcomes remain unknown until verified. No new generic automatic write retry is enabled by this work.

## Priority 3: fix state consistency, deadlines, and visible recovery

### 10. Keep references and retrieval warnings consistent after failure

**Problem:** Error cleanup restores history/memory scope, but other references/statuses can remain changed after a result fails delivery. Some state should remain because an action committed; some should not. Dynamic study search omits returned retrieval warnings.

**Fix:** Update references only when the model can use the result, or restore read-only additions if execution/result-budget delivery fails. Retain verified write receipts and recovery cards deliberately. Carry dynamic RAG warnings into the receipt/final response and preserve successful sources across later failed searches. Do not blanket-roll back committed domain state or successful parallel siblings.

**Locations:** `history_orchestration.py`, `workflow_tools.py`, and `orchestration_service.py`.

**Verify:** Failed delivery creates no unsupported citations. Earlier valid sources and committed cards remain available. OCR/coverage warnings survive dynamic retrieval.

### 11. Reserve enough time and result space for a final response

**Problem:** Repeated calls, nested work, and hidden provider retries share the 150-second timeout without an answer reserve. Errors can bypass normal result accounting. One slow read can hold up a parallel batch.

**Fix:** Retain the current total envelope and reserve approximately 20 seconds for finalization, subject to provider measurements. Stop optional work when that reserve is reached. Apply configurable time limits to lightweight reads, constrained by remaining time; do not use an arbitrary short timeout for expensive extraction/generation. Account for compact failure receipts and rejected attempts. Preserve matching tool/result messages when simplifying context.

If the final provider invocation also fails, show the specific safe failure and recovery action through existing canonical turn failure handling. Do not turn incomplete streamed text into a verified answer. More elaborate partial-answer publication is unnecessary for this fix.

**Locations:** `workflow_budget.py`, `history_management/budgets.py`, `history_orchestration.py`, `llm.py`, and `chat/service.py`.

**Verify:** Slow optional reads stop in time for finalization; all attempts/errors remain bounded. A provider outage still produces truthful recoverable failure state. Cancellation does not imply a background write was undone.

### 12. Show failed, retrying, and continuing states accurately

**Problem:** The UI exposes a generic failed step but no retry attempt or fallback explanation. It disappears at turn completion. SSE reconnect is separate from tool retry but can be confusing. Durable activity capacity can itself terminate useful work.

**Fix:** Extend the existing activity contract only as needed for tool attempt/max attempts, retry state, safe error code, and continuation message. Use a stable step ID for retries and keep tool attempts distinct from canonical chat attempts. Update backend emission, frontend validation, and rendering together, with compatibility for existing stored events.

Show concise messages such as:

- “Study material search timed out. Retrying, attempt 2 of 3.”
- “Study material is still unavailable. Continuing with a general explanation.”
- “The assessment is saved. Answer extraction failed; retry the upload or enter answers.”

Persist a compact relevant limitation/recovery note with the final message using existing response metadata, extending it only where necessary. Keep canonical RUNNING/SUCCEEDED/FAILED turn states. Reuse existing turn/domain retry buttons; do not add a new recovery workspace.

Keep SSE replay and stale-attempt fencing. Coalesce disposable progress/token events or reserve terminal-event capacity so the 256-event limit cannot replace a confirmed outcome. Announce meaningful transitions accessibly without reading every token or countdown update.

**Locations:** `activity.py`, `chat/repositories/activity.py`, `chat/response.py`, `ChatActivity.tsx`, `ChatMessage.tsx`, `chatStore.ts`, and corresponding frontend types.

**Verify:** The learner sees failure, retry, and continuation in the correct order. Refresh/reconnect preserves the final limitation. Reconnection never reruns a tool. Event capacity does not erase committed outcomes.

## Additional immediate fixes: capability questions and direct answers

### 13. Answer “what can you do?” from actual supported capabilities

**Problem:** No dedicated chat capability-description tool is currently registered. The planner is a deterministic module allocator, not an answering model. Questions such as “What can you do?” and “How can you help me?” currently fall into learning intent and allocate learner, profile, and RAG preparation. They can therefore depend on unrelated services just to explain Mentra's features. The chat prompt does not provide a comprehensive description tied to actual available capabilities.

**Fix:** Recognize capability/help questions and provide a concise, server-owned capability description to the existing answer model. Build that description from the same actual service/tool availability and authorization rules used by orchestration, with human-readable actions and limits. Explain supported activities, confirmation requirements, and unavailable features without publishing internal tool schemas, infrastructure, or private data. Distinguish configured support from verified current health; listing a capability must not claim it was just checked or executed.

Treat general capability-only questions as candidates for the strict no-tool gate in item 14. Only an approved candidate answers without learner/profile/RAG reads, recent-assessment lookup, extraction, or module-enabling calls. Describing an assessment or event capability does not create an assessment or event. Do not advertise planned capabilities as implemented; in particular, an implementation-plan file is not proof that web search is available. Questions about personal eligibility, current service health, or a particular document are not automatically general capability questions.

A mandatory new tool is unnecessary for this question. Supply the compact capability description as server context before answering. If an existing future workflow genuinely needs on-demand capability discovery, a read-only description tool can reuse the same source, but it is not a prerequisite for this fix. “What can you do with this document?” needs a capability explanation; “What does this document say?” needs document access. Mixed requests such as “What can you do, and show my upcoming events?” still execute the requested authorized read.

**Locations:** `planning.py`, `orchestration_service.py`, existing tool registration/selection in `history_orchestration.py`, and registered chat prompt context.

**Verify:** Capability questions make zero domain calls and answer even when unrelated context services are unavailable. Descriptions reflect disabled/missing services and authorization. Paraphrases work; mixed action requests still use the appropriate tools. No capability description produces mutations or unsupported product claims.

### 14. Allow no-tool responses only for clearly general queries

**Problem:** The model can already end the current tool loop without a domain call on later turns. On the first turn, `tool_choice=required` requires a function response, but the existing NewChatReply schema can itself satisfy that requirement; this does not inherently require a business tool. Neither behavior avoids eager preparation. Even greetings can still encounter recent-assessment lookup when the assessment service and history scope exist. The planner has no explicit execution mode for avoiding preparation/tool binding when the answer needs only supplied context or general knowledge.

**Fix:** Default to the bounded tool-assisted route. The deterministic planner may identify a general-query candidate, but cannot approve no-tool execution solely from keywords or its module allocation. In the first necessary chat-model response, require either an actual scoped tool selection or a final answer with explicit general-query/no-tool eligibility fields. The final answer and eligibility declaration must come from the same invocation. Apply server checks before accepting/publishing it. Do not add an early classification call followed by a separate answer call, or a second model/graph.

For eligible general-query candidates, defer unrelated prefetch and provide the compact capability description plus existing scoped context to that first invocation. Retain minimal authorized tool options or the existing module-enabling path so the model can select necessary work if it finds a dependency. Tool binding alone is not tool execution. If the model selects work, reuse that response in the existing dispatch loop instead of restarting planning or asking it to choose again. For requests already known to require sources/actions, preserve their necessary preparation and avoid speculative direct-answer generation.

The no-tool gate passes only when all of these conditions hold:

- The entire query is a greeting, general capability/help question, or stable general explanation/reasoning request. A general opening does not qualify a mixed request containing a lookup or action.
- No part requires personal/account facts, learner state, saved memory/history, current external information, current service health, or another authoritative lookup.
- No part requests a mutation, assessment generation/grading, event management, or another product action.
- No part relies on an uploaded/selected source, exact quotation, unresolved follow-up reference, or missing evidence. Visible conversation or pasted content alone does not qualify a non-general request for this shortcut.
- The LLM explicitly declares no tool dependency, no unresolved uncertainty about tool need, and enough information to answer every part. The server finds no conflicting source/action/context requirement.

Any failed condition, ambiguity, missing routing field, or disagreement between the model and server keeps the tool-assisted route. Reject a proposed direct answer that introduces personal/source/current claims or promises an action. Re-enter the tool-assisted path within the remaining budget; never publish the rejected candidate as if its requirements had been satisfied.

The user's requirement for “100% sure” means no accepted uncertainty about whether tools are needed. An LLM confidence score of 100% is not proof or an exemption from these checks; do not use a confidence threshold alone or promise mathematically guaranteed model certainty. Unknown means tools may be needed and the shortcut is denied. General capability answers also require the server-owned capability description from item 13, without claiming live health or personal eligibility was checked.

After the gate passes, publish the already generated answer and skip unrelated domain preparation, execution, and additional model rounds. Preserve normal canonical turn publication, title generation/validation, activity, streaming, and provider/time budgets. Buffer a candidate answer until its route is accepted so unapproved text is not streamed to the learner. Extend/reuse the existing final-answer schema minimally for eligibility fields; first-turn NewChatReply continues to include the title in the same response. Strip internal routing fields before public publication. Distinguish structured-output formatting from domain tool execution. Use existing scoped chat context for interpretation without claiming to have retrieved unavailable information.

Consider the current request and visible context together. An incidental selected source or attachment does not force retrieval only when the request is clearly independent of it and the model/server checks agree. If that independence is uncertain, deny the shortcut. A generic “Explain photosynthesis” can qualify; “Explain my uploaded photosynthesis notes,” “What should I study based on my progress?”, and “Explain photosynthesis and make me a quiz” cannot.

Tool-assisted does not mean forcing an arbitrary tool call: retain normal scoped tool selection and validation, and use tools needed for the request. An uncertain task may need clarification instead. Keep this strict admission gate separate from item 8's degraded continuation after a tool was attempted and failed. Such a response must retain its failure/limitation report and must never be relabeled as a fully supported general no-tool answer.

**Locations:** `planning.py`, `orchestration_service.py`, `chat_service.py`, `history_orchestration.py`, and relevant prompt instructions.

**Verify:** Clearly general greeting, capability, and stable explanation queries answer with one logical model invocation and zero domain calls only after explicit model approval and server checks, including first-turn title handling. Test negative cases for mixed requests, personal/current facts, pasted source-specific tasks, selected/uploaded material, ambiguous references, missing routing fields, model/server disagreement, and a falsely asserted 100% confidence. All deny the shortcut. Rejected candidates are never streamed or persisted. Model-selected work is dispatched without an extra selection round. Tool-assisted clarification and post-failure limited answers remain available without bypassing the gate. Accepted direct answers retain normal persistence/failure handling and are not blocked by unrelated tool-service outages.

## Tool selection and schema-token fixes

### 15. Fix broad query routing and missed contextual tools

**Problem:** The planner receives the query and attachment/source flags, not a toolbox. `plan_request` uses regular expressions to select domains, with no embeddings, learned ranking, semantic search, or planner-model call. Most non-greetings that do not match personal/event terms become learning requests and select learner/profile/RAG. The initial selection ignores conversation meaning; orchestration separately adds all assessment tools when recent assessment cards exist.

Current probes show “When is my exam?” selects events, but “When is the exam?” and “Remind me tomorrow” select learner/profile/RAG. The latter may need clarification, but unrelated study reads are still unnecessary. “Give me a test” and “And make it harder” do not select the assessment domain from the query alone. Always-available assessment_generate partly hides this weakness, and recent cards can add assessments, but neither resolves follow-up meaning accurately.

**Fix:** Improve the existing deterministic selector using current-turn action/source cues and relevant visible conversational state. Track referenced assessment/event/source IDs from existing context rather than fetching every domain to infer intent. Handle synonyms and follow-up actions conservatively; ambiguous references get clarification or capability discovery instead of speculative reads. Use explicit tool/domain metadata instead of treating every unmapped tool as learner. Do not select mutation schemas for a read-only request merely because the domain matches.

Do not add an LLM routing call or vector-search subsystem for the current small toolbox. Keep local matching inexpensive and let the first necessary model invocation resolve semantic needs through the discovery path below. Retain the strict general-query gate: a narrow initial selection is not proof that no tool is needed.

**Locations:** `planning.py`, `orchestration_service.py`, and the domain/tool selection mapping in `history_orchestration.py`.

**Verify:** Query paraphrases and follow-ups select the relevant capability without unrelated preparation. Tests cover personal versus document exams, incomplete reminder requests, quiz/test synonyms, revision follow-ups, mixed requests, and read-only queries. Selection failure is recoverable without inventing unavailable information.

### 16. Make existing tool expansion accurate and discoverable

**Problem:** The current LLM sees only selected native function schemas and can call enable_workflow_tools for one to three of history/memory/learner/events/RAG/assessment per call. Expansion only updates an enabled-domain set; it does not check that tools for the requested domain exist. A probe requesting events with no event service returned enabled but exposed no event tools on the next model round. It returns module names, not the newly usable capabilities. Profile and attachment preparation have no equivalent independently discoverable tool in this path.

There is no one-call “full toolbox” option. The model can request the six discoverable domains through two calls, subject to the shared six-call/five-model-round limits, but it can expose only tools already constructed for available services. Missing adapters are not created by expansion. In particular, get_study_source_chunk exists in rag_tools.py but is not registered by this chat coordinator. Expansion cannot grant permissions or turn a planned product feature into an executable tool.

**Fix:** Keep and improve the existing expansion tool. Supply a compact server-owned catalog of actual available domains/actions, including important limitations, in the first necessary model context. Reuse this same metadata for capability answers and initial selection; do not send every argument schema as a catalog. The model must be instructed to request discovery when a needed action is absent rather than treating absence from the initial subset as product inability.

Expansion should return exact available tool names and separate newly_enabled, already_enabled, unavailable, and rejected items. Enable only constructed, authorized capabilities. Repeated requests for already-enabled tools should reuse the receipt, not consume extra dependency/model work. Missing service availability and temporary execution failure remain distinct.

Allow requesting specific capabilities/domains through this path instead of exposing every tool in each requested domain. If the narrow catalog is insufficient, permit one bounded request for the complete available catalog. Loading all full schemas is a last-resort option only if needed and within the context/answer reserve; it is not the normal response to uncertainty. Keep scope and authorization checks, global execution budgets, and the strict no-tool gate intact.

Normally, schemas requested through discovery become available on the next necessary model round, because the model needs their actual argument definitions. Avoid repeated catalog/enable loops and any separate planner call. If the initial selector already knows the needed operation, bind it upfront and avoid discovery entirely. Do not execute a tool with invented arguments merely to save that necessary schema-reading round.

**Locations:** enable_workflow_tools, selected/dispatch checks in `history_orchestration.py`, actual service/tool registration, and registered prompt context.

**Verify:** A missed event tool becomes available after expansion; a missing service never reports enabled. Repeated expansion is bounded and accurate. All-catalog fallback shows only real authorized capabilities. Unregistered tools remain explicitly unavailable until a product-required adapter is added and tested. Discovery does not reset call/write/deadline budgets.

### 17. Narrow schemas sent to each model round

**Problem:** All registered objects are constructed server-side and then filtered before binding; server construction alone is not transmission or execution. The initial LLM gets a subset, but assessment_generate is always selected when its service exists, as are present_choices and the expansion tool. All tools within enabled domains are selected together, and enabled domains accumulate after expansion. Recent assessment cards expose the full assessment domain even on an unrelated follow-up. Each model round binds its selected full descriptions/argument schemas again; final rounds omit domain tools. Provider caching may affect billed tokens, but Mentra does not avoid transmitting those schemas by retaining them locally.

Mocked schema-capture probes using actual constructors and announcement wrappers, all relevant services present, and no recent-card widening:

| Request/selection | Schemas bound | Local schema-budget estimate |
| --- | --- | --- |
| Hello, later turn | 3 | 746 |
| Hello, first turn including NewChatReply | 4 | 884 |
| Explain photosynthesis / What can you do? | 9 | 1,697 |
| Show my agenda | 5 | 1,559 |
| Remember my preference | 5 | 1,357 |
| Learning selection after enabling events | 11 | 2,511 |
| All currently registered discoverable domains | 18 | 4,480 |

These estimates cover schemas only, use the repository's conservative token policy with a cached tokenizer, and are not provider-reported usage. The full selected schema JSON was 17,903 UTF-8 bytes. Snapshot services were fakes; no live domain actions were performed. Actual selections vary with available services, recent cards, and title handling.

**Fix:** Bind tools by relevant operation, not only domain. Retain a small discovery option and the required final-answer format; expose quiz creation, concept resolution, event mutation, and other heavier action schemas when the request/context justifies them. Preserve requested interactive assessments through explicit routing or discovery instead of keeping the large generation schema on greetings and every unrelated turn. Only bind clickable-choice schemas when needed for the interaction, keeping ordinary text clarification available.

After discovery or successful work, recompute the relevant subset from the remaining request and verified results rather than permanently sending the union of every domain touched. Retain capabilities needed for dependent steps, uncertain task resolution, and recovery. Do not prune pending tool results, reference IDs, or required evidence to shrink schemas.

Preserve validated pre-execution user announcements. The repeated tool_name/user_message literals currently enlarge every schema and force the model to reproduce server-known constants. Consider deriving these fixed values from the selected tool name on the server, still constructing and validating the same safe activity event before execution. This is an optimization of redundant fields, not removal of action reporting. Keep descriptions/constraints that determine correct arguments, provenance, permissions, and confirmation; shorten only redundant prose.

**Locations:** `history_orchestration.py`, `tool_activity.py`, registered prompt instructions, and per-tool descriptions/schemas.

**Verify:** General candidates carry only essential discovery/final-output overhead; read requests omit unrelated write schemas; requested quizzes/actions remain reachable; expansion can shrink after use without losing dependencies. Compare schema bytes/tokens, selection recovery, and model rounds against the audited snapshots. Lower schema size must not increase wrong calls or unsupported direct answers.

### 18. Guard schema expansion without discarding needed context

**Problem:** Initial conversation trimming budgets the initial tool subset. Later expansion can enlarge schemas; subsequent rounds check the larger cost and may fail with CHAT_CONTEXT_LIMIT rather than returning a specific expansion limitation. Schema conversion/counting is repeated, and token/schema overhead is not separately visible enough to explain selection costs.

**Fix:** Check the actual requested schema increase before admitting expansion. Select only required operations and retain room for tool results and finalization. If the request cannot fit, return a typed expansion limit with a narrow alternative or clarification; never silently claim the requested tool is enabled. Preserve conversation exchanges, source constraints, and call/result pairs. Cache stable converted schema definitions/token costs where safe, keyed by schema/prompt version and relevant configuration; do not cache owner-bound execution closures or private user context across accounts.

Add schema count/token estimate and discovery-round count to existing safe model logging. Confirm actual provider usage when available; local schema caching reduces local conversion work, not the provider's input tokens. Validate that pruning and catalog overhead save more than they add.

**Locations:** expansion admission/model-round checks in `history_orchestration.py`, `token_policy.py`, and existing workflow logs.

**Verify:** Near-limit expansion returns an actionable outcome, preserves required context, and leaves final-answer room. Stable schemas reuse local computation; changed schemas invalidate cached estimates. Logs distinguish schema costs, model calls, and real dependency executions without storing private arguments.

## Feedback that should guide these fixes

- Keep the existing graph, budgets, caches, domain jobs, and public service boundaries. Extract only small helpers needed to prevent duplicated retry/error handling; no orchestration redesign is required.
- Treat task importance and write certainty separately from retryability. A transient failure may still block an exact answer; a nonretryable optional failure may still allow useful help. A small failure classification is necessary, a general severity framework is not.
- Fix incorrect reports and optional preparation first, then add read retries and bounded resolution. Write replay stays operation-specific.
- Keep existing logs truthful for partial/unavailable/queued outcomes. Add retry counters and exhaustion events to the current logging path where they help diagnose these fixes; a separate observability project or metrics rollout is not required.
- The presence of an adapter or announcement label does not prove the tool is registered. Check actual selected/dispatch tools before changing availability. Missing registration is only a defect when the current product workflow needs that capability.
- Preserve successful siblings in parallel reads and confirmed effects when another step fails. Failure of one optional capability should not fail the whole interaction.

## Verification and completion criteria

The previous audit ran eight existing focused unit tests successfully and five mocked routing/reporting probes. Two probes reproduced misleading completion activity and replacement of a simulated successful action receipt after reporting failure. The repeated-failure and malformed-call probes establish the current resolution behavior; they do not prove the factual quality of an actual fallback answer.

Add focused regression tests alongside each fix: optional versus required context failure, returned business failure, completion-report outage, transient retry/exhaustion, unknown/disabled/schema correction, timeout after commit, manual retry, parallel mixed outcomes, source rollback, deadline reserve, SSE/terminal rendering, capability descriptions, and direct answers without domain calls. Use fake dependencies and clocks. Run relevant backend tests and frontend/browser checks when those paths change; no live outage is needed.

Include call-count assertions: accepted general answers use one model invocation; transient tool retries use no intervening model invocation; cache hits do not repeat dependency work; needed tool results use only necessary synthesis rounds; title generation and no-tool approval add no separate call. Compare against the current path on the same cases, including first/later turns, compound requests, and failed dependencies. Changes must not routinely increase model calls or tool/schema overhead merely to confirm that tools were unnecessary.

The tool-selection audit additionally ran 14 mocked schema/expansion snapshots and 12 existing focused title/coordinator tests successfully. Add tests for domain misses, missing-service expansion, operation-level selection, repeated discovery, full-catalog fallback, and near-limit expansion. No live provider behavior or billed-token savings were measured; verify these from usage metadata when implementing.

The fixes are complete when the current tool path reports truthful outcomes, retries eligible reads within existing limits, stops exhausted calls, continues on supported evidence, preserves committed actions, and gives the learner an accurate recovery message. Capability questions describe actual supported features. Only clearly general queries with explicit model approval and passing server checks use the no-tool shortcut; any uncertainty denies it while retaining normal chat publication and safe degraded recovery.

## Implementation record

- Execution and recovery now share `ToolExecutor`, the turn's existing call budget, and the workflow deadline. Transient reads get at most three attempts; optional preparation normally gets fewer. Retry-After is respected when it fits. Writes get one attempt and retain operation-specific domain replay protection; an unknown write outcome stays unverified. No additional provider retry loop was introduced.
- The existing workflow logger records `tool.result`, `tool.failed`, `tool.rejected`, `tool.retry_scheduled`, `tool.exhausted_skip`, `tool.cache_hit`, `provider.attempt`, and `model.round`. Domain dispatch spans distinguish success, rejection, deferred work, and degraded results. Failed execution events include safe error codes, categories, attempts, impact, and certainty; tool arguments and exception text are not added to these events.
- Ordinary activity-sink failures preserve domain receipts and stop repeated reporting attempts within the turn. An independent canonical-attempt check still fences writes. Token previews stop before durable recovery-event capacity is exhausted. Actual failed/partial/waiting outcomes are displayed truthfully, and final limitations survive canonical storage and refresh.
- Preparation is request-specific. General candidates skip learner/profile/RAG/recent-assessment/extraction reads. Required-source failures are passed as missing evidence rather than fabricated source content; independent supported parts can continue. Initial learner and search packets can be reused by matching later tools.
- Registered capabilities form a compact server catalog. Initial schemas are selected per operation, with bounded exact-name/domain discovery and an admitted full-toolbox fallback. Missing services are not reported as enabled. Used schemas can be pruned during expansion; exhausted dependency schemas are omitted. Schema admission includes the actual instructions, current context, and finalization reserve.
- General answers require strict boolean eligibility fields in the same model response, conservative query checks, and a content guard. Accepted first answers include the title in that one invocation. Missing fields, uncertainty, mixed action/final responses, and actual invalid calls use a bounded correction route. An otherwise valid approved answer survives a malformed title. This is an execution guard, not a guarantee of factual infallibility. The deprecated stateless endpoint retains its existing ordinary-chat contract; the new eligibility path applies to persistent chat orchestration.
- Read delivery failures roll back newly added references and retrieval metadata. A committed write gets a compact receipt if its large details do not fit. SDK attempts are observed using the existing HTTP client, verified with the actual SDK and a local mock transport. No live provider outage or billed-token saving was measured.
- Final regression checks exposed an overly broad shortcut for explicit selected materials. Selected sources and current attachments now deny direct-answer eligibility; inaccessible explicit inputs retain their API rejection before any model invocation, while dependency outages can still produce a limited answer. Browser checks also exposed stale memory-page recovery; conflict and cross-tab reloads now invalidate the page cache, and fixed public error messages preserve actionable recovery guidance.
- The architecture test exposed pre-existing database imports in assessment chat and the learning/profile projection. After the user requested all test failures be fixed, their persistence logic was relocated into the corresponding repository packages, preserving compatibility imports and the original transaction logic. No schema or migration change was required.

### Verified cache scope and gaps

There is no general shared cache of tool results across turns. Cache hits in this implementation mean turn-local reuse, not a distributed or durable tool-results cache.

| Layer | Existing behavior and safeguards | Fix or remaining limitation |
| --- | --- | --- |
| History and memory reads | `ToolBudget.cache` stores typed-input results within one owner-bound turn; memory writes clear recall entries. | The added executor cache now expires affected read results along with the adapter cache. |
| Learner reads | Concurrent reads can share tasks; failed tasks are removed; concept changes clear learner entries. | Both cache layers and initial learner prefetch now invalidate after a mutation. Identical adjacent parallel reads share one physical admission and preserve separate model result IDs. |
| Study search results | The approved source selection stays fixed within the turn; successful packets and source tokens are reused. | No search-result cache is shared across turns. Unsuccessful delivery clears undelivered sources and cached packets. |
| Live assessment status | Grading state can change while a turn is running. | Executor result reuse is bypassed for `assessment_status`. Assessment writes invalidate affected read snapshots. |
| RAG query embeddings | A service-local, owner/model/version/dimension/token-limit/query key, 60-second lifetime and 128-entry bound; protected by the inference lock. | This caches vectors, not retrieval results. Eligibility and active generations are checked on each search. Eviction follows insertion order rather than true LRU. |
| Attachment extraction | Stored in PostgreSQL for immutable attachment bytes; every access verifies the owner, bound conversation and deletion state. | No coordinated extraction single-flight/claim; concurrent attempts can duplicate extraction. Stored reader revision is provenance, not an automatic invalidation policy. |
| Schema token estimates | Bounded cache of public schema JSON and tokenizer availability. | Contains no account data or bound domain closures. |

Remaining cache improvements should be separate, explicit changes: canonical argument normalization across both turn-cache layers; coordinated attachment extraction if duplicate work is observed; and reader-version migration rules if extraction must be refreshed. A shared cross-turn result cache would require authorization, revisions, source-generation and invalidation design first. Absence of that cache is not a correctness defect in the bounded turn-local design.

### Optimization evidence

The following schema-token estimates compare the original audit snapshots with current real tool definitions under the same local tokenizer. They exclude surrounding prompts, results, provider-specific billing and cache discounts.

| Initial request | Audited schema tokens | Current schema tokens |
| --- | ---: | ---: |
| Later-turn greeting | 746 | 272 |
| General explanation | 1,697 | 272 |
| Agenda read | 1,559 | 315 |
| First-turn greeting including title | 884 | 342 |

`python -m testing.tool_schema_snapshot` reproduces the current snapshots offline. Focused regression assertions establish one model invocation and zero domain calls for an approved general first answer/title, and two model invocations for a read plus synthesis even when that read retries. No routine classifier, critic, retry narrator, or second title invocation was added.

### Final validation

Checks use disposable PostgreSQL schemas in the existing local test container and mocked providers; application data is not used.

- Complete backend discovery: **486 tests passed** on the final recovery/source-selection code, including the additional duplicate-read and explicit-source boundary regressions. Focused recovery checks also passed all 36 cases.
- Complete browser coverage: **77 cases passed** against the final recovery code in two batches (31 affected-suite cases and 46 remaining cases), covering authentication, memory/cache reconciliation, RAG/source permissions and citations, chat history, assessments, onboarding, retries, persisted limitations, voice and mobile layout. All failures from the initial full run were resolved or confirmed as a development-reload interruption and rerun successfully.
- Frontend TypeScript/Vite production build passed. The existing large-bundle warning remains; no unrelated bundling changes were made.
- The subsequently requested Attach files hover was verified in production Chromium in both themes: text and paperclip brighten together, keyboard focus matches, and disabled hover remains muted. The final build and centralized theme checks passed again.
- `git diff --check` passed. Repository relocation comparison confirmed that transaction/domain logic is unchanged.
- Provider retry visibility was tested using the actual SDK with a local mock transport. No real provider traffic or billed-token benchmark was required.
