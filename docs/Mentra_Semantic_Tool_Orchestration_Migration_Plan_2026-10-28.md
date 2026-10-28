# Semantic tool orchestration migration plan

Date: October 28, 2026. Status: implemented and verified in local Docker; see [verification record](audits/semantic-orchestration-verification-2026-10-28.md) for evidence and limits. Public hosting acceptance and production latency SLOs remain installation-specific.

## 1. Decision and priorities

Remove natural-language keyword routing from interactive chat. The main response model interprets the current request in its conversation context and chooses whether to answer, ask for input, discover capabilities or invoke tools. The server retains authority over availability, permissions, schemas, budgets, execution, provenance and publication.

Priority order:

1. Correct, useful responses and appropriate tool use.
2. Accurate execution, honest outcomes and preserved user/domain records.
3. Low end-to-end latency and avoidance of unnecessary model/tool work.
4. Token efficiency through schema/context selection and reuse, without sacrificing the first three priorities.

**Keyword routing is not an input-cost optimization or a fallback strategy in the finished system.** There is no language allowlist, universal extra intent-classifier call, always-on reviewer model, new multi-agent planner or replacement domain engine.

This plan defines implementation and release gates, not a guarantee of perfect model judgment. The backend can verify permission and execution facts; it cannot prove that free-form text fully expresses a user's intended meaning. That remaining semantic risk is measured using conversation evaluations and explicit failure reporting rather than concealed behind a success flag.

## 2. Source baseline and working boundaries

The reported failure and relevant sources were inspected on October 28. The questionnaire release is commit `665ab1a`; HEAD advanced to `d80de4c` during inspection. Re-read HEAD, migration heads and working-tree changes before implementation.

Concurrent memory-capture work is present in settings, prompts, chat persistence, memory repositories, summarization and migration `20261028_0035_memory_capture.py`. The user explicitly approved including it in this release. Preserve its domain boundaries and verify the combined migration/worker paths before building release images.

| Current source | Responsibility and migration impact |
| --- | --- |
| `backend/app/chat/generation.py`, `api/routes/chat.py`, `api/routes/conversations.py` | Durable chat, deprecated stateless chat, explicit controls, typed follow-up admission and response serialization. Both chat entry points must use the new policy. |
| `langchain/orchestration_service.py` | Keyword-selected preparation, profile/memory context, attachments, assessment hints and automatic event capture. Remove semantic prefetch gates. |
| `langchain/planning.py` | Regex intent, direct-answer eligibility, mandatory domains, assessment creation/edit requirements and operation matching. Retire as a semantic authority. |
| `langchain/request_intent.py` | Practice/web/content/edit hints. Replace all uses that decide intent, tool access, preparation or completion. |
| `langchain/attachment_selection.py` | Current attachment IDs plus natural-language selection of older uploads. Replace older-upload guesses with visible references/model-selected IDs. |
| `langchain/capabilities.py`, `tool_selection.py` | Existing catalog, availability and schema discovery. Retain and make authoritative for capability admission rather than guessed task requirements. |
| `langchain/history_orchestration.py`, `tool_policy.py` | Model/tool loop, regex completion repair, direct-answer approval, finalization and fast receipts. Split into focused policy components. |
| `langchain/tool_execution.py`, `tool_cache.py`, `concurrent_reads.py` | Validated execution, bounded recovery, idempotency and read reuse. Retain; integrate typed receipts and action outcomes. |
| `langchain/workflow_tools.py`, `web_tools.py` | Domain adapters, keyword-dependent assessment answer submission and web refresh intent. Replace those semantic gates with typed operations. |
| `history_management/events/capture.py`, `events/proposal_service.py` | Keyword-gated pre-response event extraction. Move interactive capture selection into the main decision loop; retain event admission and user settings. |
| `langchain/chat_service.py`, `prompts/*`, `llm.py`, `model_factory.py` | Prompt composition, first-turn titles, provider handling and returned reply contract. Use one explicit final-decision contract. |
| `langchain/graphs/response.py`, `graphs/tool_coordinator.py`, `response_runtime.py`, `repositories/response_checkpoints.py` | Graph completion, nested checkpoints and resume. Version and migrate state without replaying completed writes. |
| `chat/service.py`, `chat/repositories/postgres.py`, `chat/response.py`, `chat/schemas.py` | Atomic publication, legacy turn state, errors, checkpoint expiry and evidence scheduling. Persist business outcome separately. |
| `frontend/src/stores/chatStore.ts`, `types/conversations.ts`, `types/chat.ts`, `services/conversations.ts` | Pending requests, polling/events, cache, terminal state and retry payloads. Consume authoritative outcome/control data. |
| `frontend/src/pages/ChatPage.tsx`, `components/chat/*`, `services/userError.ts` | Shared composer, partial results, errors, progress and questionnaire rendering. Remove success/failure inference from prose and legacy state alone. |

The incident at 19:04 PKT demonstrates three connected defects: `current` in ordinary English practice required web search; the completion guard replaced the answer with an unconditional saved-results fallback; normal graph return persisted `SUCCEEDED` with `REQUEST_OUTCOME_INCOMPLETE` and deleted the retry checkpoint.

## 3. Invariants

| Invariant | Enforcement |
| --- | --- |
| Availability never implies required use | No enabled/pending-tool list becomes a checklist of actions the model must perform. |
| Discovery never executes an operation | Requesting schemas cannot fetch private records, search the web, create assessments or mutate anything. |
| Execution is server controlled | Current owner, context, tool registry, argument validation, source permissions and domain admission are checked on every invocation. |
| No inferred external side effects | Tools retain their current confirmation and automatic-action rules. Tool selection is not a grant of permission. |
| Claims of saved/generated/graded work have receipts | Only authoritative owned receipts can produce domain confirmation cards and status. No fabricated IDs or prose quiz substitute. |
| Ordinary conversation needs no receipt | English practice, general explanations, supplied-text edits and informal questions may complete in one model invocation. |
| Useful results survive incomplete work | Publish validated partial content/cards with an honest outcome; never erase them with a generic fallback. |
| Completion is not execution termination | Graph termination and provider success are logged separately from task fulfillment. |
| Resume never repeats a completed write | Existing domain operation IDs, checkpointed task results and reconciliation remain authoritative. |
| Naming/choosing is not mastery | Questionnaire/preferences, tool selection, confirmations and generated questions do not create knowledge evidence. |
| No privacy expansion | Do not introduce blanket learner-data prefetch or expose additional private context because a capability is available. |

## 4. Target request flow

1. Authenticate/admit the request and capture its canonical message, IDs, explicit UI selections and continuation metadata.
2. Build a bounded trusted context envelope: relevant recent messages, existing approved summaries/profile context, visible artifact/entity references, selected sources, current attachments and applicable account settings.
3. Bind a stable, budgeted set of lean tool schemas plus the capability catalog and final-response schema. This selection uses server configuration and concrete application state, not words in the request.
4. Invoke the main model. It may finish directly, present a questionnaire, request additional schemas, invoke admitted tools or combine compatible calls.
5. Validate and execute chosen operations through existing facades. Record typed receipts, materialize read results/citations deterministically and checkpoint completed effects.
6. Continue the same model/tool loop only when needed. Reuse context, reads, schema definitions and receipts.
7. Validate the proposed final outcome against the task ledger and actual results; publish content, cards and outcome atomically under the existing owner/attempt fence.
8. Continue background assessment/grading jobs through their existing workers. Project their actual status into linked task outcomes without claiming they have already completed.

No separate initial model planner runs before step 4. Domain generation, grading, transcription or admission calls remain where their responsibilities require them; measure them separately instead of hiding them in the main-call count.

## 5. Capability availability and smart enabling

### 5.1 Stable lean schemas and deferred schemas

Use a hybrid based on schema size and measured task frequency, without prompt keyword classification.

| Binding tier | Initial policy |
| --- | --- |
| Common control | `finish_response`, `present_questionnaire`, `enable_workflow_tools`. A questionnaire handles a single conversational decision as well as a related question set. |
| Lean frequent operations | Candidate fixed core: existing `web_search`, `search_study_material`, compact `assessment_generate`. Admit only configured/authorized tools and within the measured schema/context budget. Binding never calls them. |
| Concrete application context | A visible owned assessment, event, source selection or explicit interface action may seed relevant small schemas. This is optional availability, not an obligation or automatic lookup. |
| Larger/less frequent operations | Discover advanced assessment creation, revisions with large schemas, broad history operations, research and extended UI references on demand. |
| Legacy conversational tools | Keep standalone choices/forms and their payloads compatible and discoverable. Preserve all existing questionnaires and submitted inputs. |

The implementation must measure the candidate core before freezing its default. Prefer additional input tokens to an extra discovery round when that measurably improves correct common tasks. Do not bind every large schema indiscriminately or preserve a token ceiling that makes the requested operation impossible.

A deterministic admission order uses: common controls, explicitly selected UI operation, concrete owned task context, configured lean core, then deferred discovery. If space is tight, omit optional schemas while retaining catalog visibility. Never remove relevant user context or fabricate arguments to make a schema fit.

### 5.2 Catalog and discovery contract

- Catalog entries include exact operation names, short purposes, whether they read private data/create side effects/present UI, key preconditions and availability. They contain no private records or service credentials.
- Distinguish assessment creation from conversational questions; web search from ordinary use of words such as current; visible-history reuse from retrieval; event announcements from exam preparation.
- Discover exact tool names or a bounded domain bundle. Remove `all_tools` as a normal recovery strategy; a full catalog remains visible, while executable schemas stay budgeted.
- Return structured discovery outcomes: enabled, already enabled, unavailable or schema-budget-limited, with supported smaller alternatives. Do not charge a domain write or external-read slot for discovery.
- Do not execute calls against guessed/unloaded schemas. One bounded correction may load the named available schema and let the model generate validated arguments; it must not silently execute an earlier malformed call.
- Tool availability is intersected with the current owner/mode/provider registry on every resume. An old checkpoint cannot restore a removed permission.
- Keep enabled schemas through the current turn while useful; retire completed large schemas before further discovery to avoid context growth. A later turn starts from current trusted context, not an ever-growing historical toolbox.

### 5.3 Prompt composition

Separate compact selection guidance from extended domain instructions. Merely binding a lean assessment/web schema must not load a large domain prompt that steers an unrelated conversation toward that domain.

Keep minimum argument/precondition guidance with each bound operation. Load fuller revision, source, citation, research or UI-reference instructions when that capability is selected or its result requires them. Include each source once per model request. Stable public instructions/schemas may be cached by the application/provider; required instructions still go out when provider caching misses.

## 6. Context preparation without intent keywords

| Context | New preparation rule |
| --- | --- |
| Recent conversation | Include enough actual recent user/assistant context for the model to understand the ongoing exercise; the latest message is not classified in isolation. |
| Profile and summaries | Preserve currently authorized bounded context and preference-freshness checks. Coalesce reads and retain revision fences. Do not expand exposed fields or eagerly fetch detailed learner records. |
| Learner progress | Retrieve through model-selected owner-bound tools when needed. Available learner capabilities do not imply prefetch or evidence submission. |
| Assessments | Visible owned card IDs/titles/version references are lightweight context. Read full questions or historical assessments only when chosen/needed. No lookup because the text contains test or question. |
| Current attachments | Ownership, binding, supported format and limits are deterministic. Prepare explicitly attached text/images using existing bounded readers; do not infer grading versus explanation from keywords. |
| Older attachments | Expose bounded visible file references with IDs, names and types. The model selects the relevant owned file; exact filename/ID resolution is identity matching, not an intent classifier. Ambiguous references require clarification. |
| Study-material selectors | Validate selected scopes immediately; actual content retrieval occurs when needed. Selecting a source defines scope, not fabricated evidence that it was read. |
| Visible artifact edits | Offer visible assistant-message/artifact IDs and preserve recent complete originals within budget. The model may edit directly when the original is present. Retrieve the original when missing/too large; never reconstruct it from a lossy summary. |
| Web | No requests or searches for a word match. Explicit fresh-search intent becomes a typed operation parameter; remove regex cache-bypass interpretation. Preserve existing website, quota, timeout and source-validation rules. |
| Events | Remove the interactive pre-model regex capture gate and its automatic serial extraction pass. Main-model event selection invokes existing event admission/proposal logic, with original quote, account timezone and automatic-events preference. No automatic quiz from an exam announcement. |
| Memory capture work | Coordinate with the concurrent background pipeline. Its opt-in/settings, provenance, conflict rules, summaries and post-commit processing remain domain owned. It does not become a foreground router, confirmation of mastery or permission to expose more private data. |

Avoid preprocessing the same upload twice for chat and answer extraction. Use current immutable file/revision receipts, prepare expensive extraction only when needed, and preserve image/OCR fallback behavior. Changes must cover stateless chat as well as durable chat, without granting stateless routes durable mutation authority.

Preserve source scope without inventing source use: a selected Library area does not force a retrieval for a greeting, but an answer represented as grounded in selected/owned material must have matching authorized evidence. Carry explicit grounding constraints in the task contract and enforce them at finalization. No matches can complete a search request honestly; it cannot support an invented source-grounded explanation. Revoked/deleted sources invalidate their reuse, and public web evidence cannot silently replace a requested private-source-only answer.

### 6.1 Explicit replacements for hidden operation gates

| Existing hidden gate | Typed replacement and preservation rule |
| --- | --- |
| `assessment_answer` checks English evaluation verbs before automatic submission | Separate `prepare` from `submit` in the operation contract, with `prepare` the safe default. The model chooses submission only for requested evaluation; an actual Submit button is an explicit structured action. Domain validation still requires canonical student answers, exact question IDs, complete eligible answers and current attempt revision. Upload extraction/ambiguous or partial answers remain reviewable and do not auto-grade. Preserve assistance, exposure and grading rules. |
| A past assessment card plus harder/it/question words becomes a revision requirement | Supply real visible card/version IDs. The model chooses whether the current request refers to them; unchanged question IDs/keys/attempts survive a compatible selected-question revision. A different conversation request is free to ignore those tools. |
| A word such as current or notes turns a capability into a required lookup | No typed requirement is created. Only the model's semantic requested-work declaration or an explicit interface operation establishes a task. |
| Old-upload pronoun or filename regex selects and reads a file | Exact IDs/names resolve identity among visible references; the model selects which file to use. Validate access again before retrieval. Naming an upload in supplied text does not itself trigger reading it. |
| Fresh/recheck phrases alter web cache policy | Add an explicit bounded refresh parameter to the actual web operation, respecting service freshness/quota policy. Its value is selected semantically; no request-text regex bypass. |
| Event keywords launch pre-chat extraction | Main-model selection supplies the original canonical user-message reference and candidate to existing event admission. Preserve automatic-events preferences, temporal validation and confirmation/review semantics; do not simply disable the existing product feature. |

Regex remains appropriate for exact citation markers, structured numbered-answer parsing, identifiers, file formats, numeric/date validation, URL/security constraints and known provider-protocol errors. These validate an already selected operation's data; they cannot select an operation, infer consent or manufacture a task requirement.

## 7. Model decisions and task ledger

Introduce small versioned Pydantic contracts in focused modules, for example `decision_schemas.py`, `task_outcomes.py`, `context_envelope.py` and `reply_finalization.py`. Names are implementation suggestions, not permission to create a generic framework.

| Contract | Required information |
| --- | --- |
| `FinishDecision` | Content, optional first-turn title, proposed outcome, concise task dispositions and referenced receipt/task IDs. No reasoning transcript. |
| `TaskEntry` | Stable task ID, operation/answer kind, parent/dependencies when needed, target reference, state, attempt, receipt/job references, effect certainty and allowed recovery. |
| `ToolReceipt` | Registry operation, owner-bound operation/task ID, attempt, actual domain status, effect certainty, public result pointers, provenance/revision, retry classification and public-safe reason code. |
| `ResponseOutcome` | Version, aggregate state, bounded task dispositions, pending input/work references, safe issues and server-derived control actions. |

The model describes requested work semantically during normal decisions, discovery or finalization. The dispatcher attaches actual calls and receipts to stable tasks. A look-up in one domain cannot fulfill a different mutation just because both have the same domain label.

The server validates reference existence, ownership, operation kind, receipts and disposition consistency. It does not turn capability availability into a task. Optional supporting lookups do not become user-requested work merely because the model considered them.

For compounds, preserve separate dispositions: for example a completed explanation, saved assessment job and failed optional search are not one undifferentiated success/failure. A missing **optional** enhancement may produce a completed answer with a specific warning; a required requested deliverable that remains unresolved produces partial/failed status.

A model can still omit or misunderstand a requested task. There is no dishonest promise that a deterministic ledger proves semantic coverage. Require coverage declarations in final decisions, evaluate them on held-out conversations and preserve explicit UI-requested operations as authoritative task records. Do not add an always-on second judge or reintroduce keyword requirement detection.

Domain confirmations and cards are built from verified receipts. Free-form prose remains subject to model-quality risk; prompts and evaluations must prevent unsupported action claims. Citations, saved IDs, grading state and rendered domain confirmations are independently validated.

## 8. Outcome and publication contract

### 8.1 Execution versus fulfillment

Retain the legacy turn execution states `RUNNING`, `SUCCEEDED`, `FAILED` for compatibility. Add versioned response outcome data; no new PostgreSQL enum is needed.

| Business outcome | Meaning | Legacy compatibility and controls |
| --- | --- | --- |
| `completed` | The requested response/deliverable is fulfilled by content and/or verified results. | `SUCCEEDED`; Send. |
| `awaiting_input` | A real clarification/questionnaire or domain confirmation is pending. | Delivered response may be `SUCCEEDED`; Send/answer controls, not Retry. |
| `in_progress` | Foreground handed off to a real owned generation/grading job that has not finished. | Foreground delivery may be `SUCCEEDED`; show actual job state and route Pause/Retry to that job when allowed. Never say questions/results are ready merely because a job exists. |
| `partial` | Useful requested work is available; other requested work is unresolved. | Foreground incomplete execution maps to `FAILED` with published partial content/results; Retry only for retryable unresolved tasks. |
| `failed` | No usable requested deliverable was produced. | `FAILED`; Retry only when server-classified as retryable and recoverable. |
| `paused` | User intentionally stopped unfinished work. | Preserve current `FAILED`/stopped compatibility, checkpoint TTL and Resume behavior. |

Graph node return, provider success, technical graph termination, response fulfillment and background job completion are separate observability fields. A normal graph END cannot override an explicit partial/failed task result.

Top-level workflow/finalization instrumentation must derive its outcome from `ResponseOutcome`, overriding current default-success decorators. Individual provider/SQL spans may correctly succeed while the enclosing user task fails. Export task outcome/reason codes to traces and dashboards; display business failure/partial state prominently rather than presenting graph END as fulfillment. Do not rely on an exception as the only failure signal, or throw away partial data merely to make a tracing UI red.

### 8.2 Finalization rules

1. Validate proposed content and receipts without another routine model invocation.
2. Reject fabricated/foreign/nonexistent references and reconcile actual domain state where effect certainty is unknown.
3. Derive outcome and controls from task states, pending native input, actual job receipts and supported recovery. A tool being enabled, attempted or mentioned is insufficient.
4. Preserve valid prose, cards, citations and completed effects. If requested work is missing, make one bounded repair only when the model's declared task or an explicit structured UI action establishes that work. Do not demand an action because of a regex.
5. Derive any fallback from actual facts: no universal saved-results sentence. If there are no saved results, do not mention saved results. For partial results, identify the concrete available item and unfinished part.
6. Publish outcome, assistant content/metadata, canonical controls, conversation revision and any retry state atomically under the owner/turn-attempt fence.
7. Retain partial/failed retry checkpoints when needed; remove completed checkpoints only when unfinished foreground tasks are absent. Existing linked jobs own their independent checkpoint lifecycle.

Require useful nonempty content, valid rendered input/results or a meaningful verified work handoff. Empty prose is acceptable when a complete native UI/receipt is the response; empty content with no usable result is a failure. Do not add filler solely to satisfy the old string-only reply adapter.

An assessment/grading enqueue receipt is `queued`, not generated/graded. Reuse the current fast public-title acknowledgement when the entire foreground response is an authorized job handoff and no requested explanation/other work remains. This decision uses typed task dispositions, not the current regex test for words such as also/explain/and.

### 8.3 Asynchronous status projection

Do not build a new general event platform for this migration. Persist stable job/task references in the outcome. Extend the chat read facade to batch-read owner-scoped linked generation/grading job states and derive the effective outcome. Fetch references for the current bounded message page in batches, without N+1 reads or private grading keys.

Existing job cards continue polling their job endpoints. On a terminal job update, refresh the source turn's outcome once; active-chat reload/focus also refreshes it. History/status/sync projections use the same server derivation, so a stale cached `in_progress` snapshot cannot misrepresent a completed/failed job indefinitely.

Fence merges by turn attempt and each job's actual revision. Do not compare hashes lexicographically or let an older HTTP response resurrect an earlier task state. Missing/deleted/expired jobs are explicit unavailable states, not assumed successes. Uncertain writes require reconciliation before a new execution.

## 9. Persistence and API migration

- Use an additive migration after the actual current Alembic head. Add nullable `chat_turn.response_outcome` JSONB and an orchestration policy/version marker, with bounded application-validated content. Keep immutable domain records in their existing repositories.
- Mirror the published outcome snapshot in assistant metadata for normal history rendering; use the shared projection for current linked-job state. Write both consistently in the publication transaction.
- Store receipt pointers/effect certainty rather than raw tool payloads, service objects, credentials or private keys. Domain IDs/receipts retain their existing authority.
- Existing request UUIDs, hashes, empty-field exclusions, canonical message sequences, original message IDs and assessment operations do not change. New optional request fields, if any are necessary, must preserve old fingerprints.
- Extend `ChatResponse`, turn/status/history/sync DTOs and terminal SSE payloads with the outcome and server control actions. Cover ordinary Send, Resume, legacy retry and typed continuation.
- Deprecated stateless `/chat` returns the same explicit outcome envelope but does not offer persistent Resume for nonexistent checkpoints. Keep its existing mode restrictions.
- Legacy successful messages without error markers remain historical completed responses with an explicitly legacy/unverified provenance version; do not fabricate task receipts.
- Legacy `REQUEST_OUTCOME_INCOMPLETE`/known server failure markers project as incomplete, even when the stored old state says `SUCCEEDED`. Do not infer historical failure from arbitrary assistant/user prose. Preserve original history; expose a corrective status rather than silently rewriting content.
- If an old failed response's checkpoint was already deleted, state that recovery restarts the response from preserved canonical context and existing domain receipts. Do not pretend the deleted graph step still exists or replay writes without reconciliation.
- Wire legacy failure correction into **admission**, not only display: under the owner/turn lock, an explicit retry of a known server-marked false-success turn must reconcile its effective failed state and create an authorized new attempt. Otherwise the old `SUCCEEDED` replay branch would simply return the same failure again. Preserve original IDs/receipts and the prior attempt's audit status. Maintain current-turn/history-order restrictions; recovering an older closed exchange uses an explicit new response linked to the old task, rather than rewinding newer history.
- Audit evidence scheduling: partial/failure status is not itself knowledge evidence. Keep original learner provenance/independence rules and domain grading projections; valid completed evidence must not be lost because another requested action failed.

## 10. Pause, resume, retry and policy versions

| Scenario | Required behavior |
| --- | --- |
| Pause during model/discovery/read | Cancel bounded active work; no late publication; retain completed graph state. Discovery alone is not an executed user action. |
| Pause during domain write | Preserve operation identity and effect certainty. Consult the domain receipt if completion is uncertain; never blindly rerun it. |
| Resume after process restart | Restore versioned task ledger, tool state, public receipts, budgets and trusted IDs; reauthorize capabilities and revalidate memory/source fences. |
| Retry a partial response | Retry only unresolved retryable tasks. Preserve completed reads where still valid, citations, saved assessments, attempts and original question identities. |
| Background failure after successful handoff | Unified control dispatches an owner-bound job retry with the required job revision, rather than trying to resume a nonexistent foreground node. |
| User types after Pause/Retry | Shared composer becomes Send; clearing restores its previous action. New facts, answers and confusion statements remain canonical new messages. |
| Explicit Resume button | Direct owned resume; no semantic classification call. |
| Typed continuation after a pause | Retain the existing conditional bounded semantic decision, not a universal router. Remove English phrase shortcuts so every language follows the same semantic contract. On failure default to a new message, preserving data. Measure this exceptional extra call separately. |
| Expired state | Respect the existing 30-minute response/stopped-generation retention policy. Remove unusable Resume/Retry controls and explain how to start a new response. Keep durable domain receipts and saved history. |
| Legacy checkpoint | Adapt known structures; drop obsolete transient requirement instructions while preserving canonical messages, tool results and completed effects. Never restore old regex requirements as obligations. |

Keep the current graph threading/owner/attempt lock discipline and short database transactions. Never hold a connection during a provider call. Store new checkpoint payloads as explicit versioned data; retain only the existing narrowly allowed legacy serializer types needed for transition. Unknown/corrupt versions must fail safely with data retained, not enable arbitrary deserialization or uncontrolled replay.

Distinguish per-attempt budgets from lifetime accounting. A user-authorized retry receives a bounded new allowance for the unresolved work, under normal owner admission; it must not inherit an already exhausted counter that makes recovery impossible. Preserve cumulative spend/effect telemetry and completed receipt identities, and never charge replayed cached tasks as new physical work. Automatic repairs/retries remain within their parent attempt's deadline/budget and cannot mint fresh allowances recursively. Checkpoint adapters map the old counters explicitly.

Pin the orchestration policy to a turn at admission. A feature/config change affects new turns; an adapter or explicit compatible recovery handles older ones. Do not execute half a response under each policy.

## 11. Frontend behavior

| Surface | Change |
| --- | --- |
| Assistant message | Render useful content and result cards independently of outcome. Partial content stays visible. No fabricated result section when all result arrays are empty. |
| Outcome indicator | Small plain-language completed/waiting/working/incomplete/failed/paused state from the server. Ordinary optional warnings do not turn a useful completed answer into a fatal error. |
| Unified composer | Continue one Send/Pause/Resume/Retry button. Consume server flags/control targets; stop inferring Retry solely from `turn.state === FAILED`. Support foreground and background targets. |
| Grouped questions | Preserve all questionnaire questions/options, one atomic submission, accepted answers, navigation drafts and original-payload recovery. Awaiting input is not a failed tool call. |
| Progress/activity | Discovery says preparing capabilities, execution says the actual operation, handoff says work queued/running. Provider return and graph end do not show user-task success prematurely. |
| SSE/polling/cache | Terminal event means foreground stopped running, not necessarily completed. Merge outcome/control revisions into active, persisted and cross-tab state. No unresolved pending-send spinner after partial publication. |
| Errors | Use closed public-safe codes and specific actionable messages; keep traces/provider details private. No unconditional generic text replacing a valid partial result. |
| History/older clients | Parse absent outcome fields safely. Older successful records remain readable; known legacy failure markers receive a corrective status. Test mixed deployment and cached history. |

Keep existing sidebar, message/composer placement, accessibility, theme primitives and reduced-motion behavior. Do not create a second response toolbar or separate competing Send/Retry button.

## 12. Performance and budget policy

### 12.1 Model-call targets

| Path | Target interactive model work |
| --- | --- |
| Ordinary conversation, tutoring response, visible supplied-text edit | One main invocation; no classifier/reviewer/discovery requirement. |
| Related conversational questionnaire | One presentation request plus, at most, the final response round; investigate receipt-only acknowledgement when no other response work remains. Never one model cycle per question. |
| Bound independent tool set | One model selection, parallel compatible reads, at most one synthesis invocation. Domain-specific model work is accounted separately. |
| Cold deferred capability | At most one discovery round before the normal invoke/synthesis flow. Prevent repeated enable/disable loops. Frequently used lean operations should avoid this cost through the static core. |
| Simple assessment handoff | One main selection call when compact generation schema is bound; use actual public job receipt for acknowledgement. Generation happens in the durable worker. |
| Partial retry | No replay of completed write tasks; no rediscovery of already admitted still-available schemas. Refresh only invalidated/stale reads. |

These are architecture targets, not invented measured latencies. Explicitly record justified extra rounds for malformed provider protocol, necessary clarification, dependency changes and large multi-step requests.

### 12.2 Retained limits and optimizations

- Keep the current 150-second interactive deadline and provider input/output/context limits during migration. Background generation keeps its separate worker budget. Increasing a useful input budget is allowed when measured and within provider limits; keyword filtering is not.
- Preserve bounded domain calls/writes and separate presentation allowance. Count discovery separately. Publish which budget actually ended work; do not disguise a budget stop as success.
- Maintain a reserve for finalization/compact receipts. Optional low-priority context or completed large schemas are evicted before current user instructions, relevant visible originals or required provenance.
- Parallelize independent validated reads; serialize dependent work and domain mutations as required. Stage citation/reference commits deterministically.
- Keep existing normalized request/cache keys, singleflight and mutation invalidation. Source permissions, memory revisions, document revisions, current job states and external freshness remain part of reuse eligibility.
- Cache only public schema/capability metadata across owners. Never cache owner-bound tool closures, private packets or write receipts across users.
- Avoid unnecessary full-history, full-assessment or broad learner reads. Selecting a target by an already visible owned ID should not require another search to rediscover its ID; domain service revalidation still occurs.
- Streaming remains provisional until validated publication. Keep current activity/token recovery; do not display unfinished action claims or raw structured-output arguments. Measure first useful content separately from activity and terminal fulfillment.
- Limit protocol/schema correction to one bounded attempt in the existing overall envelope. Unsupported tools/provider modes report unavailability honestly; do not substitute unverified personal/current facts.

### 12.3 Provider and output compatibility

Use the pinned shared `MentraLLM`/`ModelFactory` and its existing non-thinking/tool-binding behavior where required. Native function calling may require choosing a tool protocol message; `finish_response` is a control decision, not a required business tool action, and consumes no external read/write slot.

Test ordinary completion, discovery, several native calls, first-turn title, malformed arguments, truncation, vision fallback and unsupported tool binding against the configured provider. A provider lacking tool support may still answer ordinary text with a validated final JSON envelope; domain actions remain explicitly unavailable. Do not claim they executed, repeatedly pay for unsupported bindings, or silently switch to a second provider with private user context. Keep first-turn title generation in the main response call with a deterministic provisional-title fallback; a title formatting error alone must not discard a valid response.

Do not stream the partially decoded `FinishDecision` arguments into public text. Preserve safe activity/provisional output and canonical final publication. If an optional direct-text optimization is added later, it must retain the same outcome/provenance contract and pass the same tests; it is not a reason to restore direct-answer keyword approval.

## 13. Verification corpus and release gates

### 13.1 Offline deterministic and database checks

| Area | Required cases |
| --- | --- |
| Intent independence | Same words used in tutoring, quoted text, preferences, code and real tool requests; no keyword enables a requirement or causes preliminary data access. |
| Domain availability | Disabled/unconfigured service, stateless mode, unavailable schema, registry change, schema-budget rejection and owner access failure. |
| Task/outcome integrity | No-tool answer, optional failure, required failure, mixed partial results, clarification, confirmation, queued generation, queued grading, unknown write effects and cancellation. |
| Receipt correctness | A read cannot fulfill a write; a queued job is not a result; attempted operation is not success; no fabricated IDs/citations, private keys or nonexistent result sections. |
| Recovery | Pause at every graph boundary, disconnect during admission/publication, restart, duplicate retry, changed instructions, concurrent tabs, expired/corrupt/legacy checkpoint and policy switch. |
| Persistence | Source turn, ledger, outcome, assistant metadata and revisions commit consistently; partial result survives; legacy UUID/hash replay remains valid; no duplicate domain/evidence writes. |
| Preservation | Accepted-assessment selected-question revision keeps unchanged keys/IDs/attempts; source/file ownership, immutable learner evidence and questionnaire behavior remain intact. |
| Asynchronous projection | Worker completion/failure/cancellation, stale HTTP response, deleted job, permission change and reload after job completion. No permanently green failed task or stuck working status. |
| Security | Untrusted content cannot choose owner IDs, tool registry, prompt source, permissions, confirmation decisions or checkpoint deserialization modules. |

Start from existing `test_smart_tools`, `test_tool_recovery`, `test_orchestration`, `test_followup_edits`, `test_response_latency`, `test_response_resume`, `test_generation_stop`, `test_chat_questionnaire`, event/assessment/memory/source tests. Update assertions that encode old keyword behavior; do not simply delete meaningful safety tests.

### 13.2 Conversation and configured-model evaluation

Create a versioned synthetic conversation corpus with expected permitted/required/forbidden **behaviors**, task outcomes and rationale. Do not require exact prose or one exact tool sequence when equivalent correct paths exist.

Include the real failure pattern using synthetic conversation data, not exported student histories:

| Conversation | Expected behavior |
| --- | --- |
| English exercise followed by “my current phone is slow” | Continue language feedback without web search or false action failure. |
| Ask for current external phone prices | Obtain current evidence or clearly report inability; do not invent facts. |
| “I have a test tomorrow” | No automatic assessment; handle an actual personal event according to settings/admission, or discuss preparation. |
| Explicit quiz request versus getting-started questions | Assessment tool/job for the former; grouped conversational questions for the latter. |
| Pasted code/text containing current, schedule, notes, test or saved | Transform/explain the supplied content without unrelated tool work. |
| Follow-up to a visible code/essay/research artifact | Reuse its actual content and citations; no redundant lookup when the original fits. |
| Several saved entities and “change that one” | Resolve from actual references or ask a clarification; do not guess a write target. |
| Mixed explanation, search and assessment with one failed dependency | Preserve fulfilled components and report the exact unfinished work. |
| Urdu, Arabic, Spanish, other languages and mixed scripts | Same capability semantics and safety rules; no language-specific enabling allowlist. |

Use at least 40 distinct representative episodes; repeat the 12 critical routing/recovery episodes three times, with the remaining 28 once, for 64 evaluations per compared policy. Freeze model/provider/settings/corpus version and label expected behavior before interpreting results. Keep external writes stubbed or in disposable owned databases; run a small separate end-to-end provider/tool smoke against synthetic records.

No live dual execution on user traffic: shadow comparison may simulate decisions and costs but must not duplicate searches, model spend or mutations silently. Use prerecorded/synthetic replay for the main comparison.

### 13.3 Acceptance criteria

- All deterministic ownership, publication, receipt, idempotency and recovery tests pass. Zero unauthorized writes, duplicated committed actions or false-success outcomes in critical fixtures.
- Static import/call-site checks confirm removal of old interactive intent gates. The check targets semantic authority/call sites, not all regular expressions: security, exact-ID, format and citation parsers are deliberately retained.
- All 12 repeated critical episodes pass their must-use/must-not-use and outcome assertions; overall held-out semantic behavior accuracy is at least 95%. If a reasonable case is ambiguous, document allowed clarification paths rather than forcing one regex-shaped answer.
- Ordinary no-tool and visible-edit cohorts meet the one-main-invocation target. No universal classifier/reviewer added; no extra read on a mere keyword match.
- Five/20-question UI metadata remains intact; desktop/mobile one-submit and actual assessment grading continue to pass.
- Direct/warm successful-task median latency should stay within 10% of the corresponding correct baseline, unless an explicitly reviewed correctness fix explains the difference. Cold discovery is reported separately and may add one model round; improve the static lean core when frequent cold paths dominate.
- Report end-to-end latency, main/domain model calls, physical tool calls, discovery rounds, provider tokens/cache hits, duplicate reads, retries, false tool activation and missed requested work. Failed baseline tasks are failures, not fast successful comparators.
- Record median/range/raw samples for small controlled cohorts. Claim a p95 release/SLO comparison only with at least 100 successful observations per compared cohort; do not manufacture production p95 evidence from a few examples.
- Build/type/theme/UI checks, relevant browser flows, migrations against synthetic populated histories, configured-model checks, production-mode synthetic runtime and Docker readiness pass. Claims distinguish simulated tests, configured-model tests, local deployment and public infrastructure acceptance.

## 14. Implementation sequence and gates

| Phase | Concrete work | Exit gate |
| --- | --- | --- |
| 0. Freeze the contracts/baseline | Recheck dirty work and Alembic head; save synthetic corpus, correct-path call/token baselines, old checkpoint fixtures and current API compatibility snapshots. | Explicit must/must-not cases and preservation requirements are recorded. |
| 1. Outcome foundation | Add outcome/receipt/task contracts, additive persistence, public-safe API data and atomic partial publication. Introduce legacy adapters before changing routing. | Known failure cannot be published as completed or erase valid results; old clients/history still load. |
| 2. Semantic policy and preparation | Replace intent plan with trusted context/availability data; bind measured static lean core plus discovery. Remove keyword-driven prefetch, direct approval and required-domain repair. | Ordinary conversations/edits use one main call; explicit tool work still selects and executes correctly. |
| 3. Complete hidden-gate migration | Update old attachments, events, assessment submission mode, fresh-search flag, first-turn titles and typed continuation shortcuts. | No remaining natural-language keyword gate controls interactive tool availability, use, fetch or completion. |
| 4. Durable ledger/recovery | Connect action receipts, graph state, policy adapters, task-specific retry and background status projection. | Cross-process pause/resume/retry and async failures preserve data without duplicate effects. |
| 5. Frontend consumption | Outcome-aware messages, shared controls, background retry targets, SSE/poll/cache compatibility and truthful result sections. | Desktop/mobile normal, failed, partial, waiting and working flows pass. |
| 6. Evaluation and tuning | Run offline suites, held-out/configured-model comparisons, call/token/latency measurements; tune stable core/schema/context reuse without keywords. | Acceptance matrix passes; remaining model limitations and any justified performance tradeoffs are explicit. |
| 7. Release | Review diff/credentials, back up data, migrate, rebuild/tag, deploy all services, verify, clean owned artifacts and commit finalized work. | Healthy exact-source runtime, retained recovery assets and a clean documented handoff. |

Phases are implementation order, not permission to deploy a partially wired outcome system. A temporary containment patch, if required before the migration, may disable keyword-forced actions and misleading fallbacks; it must be labeled temporary and must not become the completed architecture.

## 15. File-level work packages

| Package | Expected edits/additions |
| --- | --- |
| Context and capability admission | Replace callers in `orchestration_service.py`; focused context/availability module; simplify `tool_selection.py` and `capabilities.py`. |
| Decisions and finalization | Versioned schemas and validators; split `history_orchestration.py` so model rounds, discovery, dispatch and outcome validation are readable independent responsibilities. |
| Domain adapters | `workflow_tools.py`, `web_tools.py`, event capture/admission integration, old-attachment access and visible artifact retrieval. Existing public domain facades remain intact. |
| Durable state | Graphs, response runtime/saver, chat service/repository, DTOs and the next additive migration. Keep ownership and state transitions repository owned. |
| Prompt policy | Core chat, UI, assessment, web, source/history, response-edit and continuation prompts; registry versions and prompt tests. Do not embed long prompt prose in orchestration code. |
| Frontend | Types/services/store, ChatPage/composer, message outcome UI, activity labels and job-card terminal refresh hooks. Preserve native questionnaire and assessment components. |
| Compatibility/removal | Remove obsolete `ExecutionPlan` intent authority, direct-answer approval types, mandatory-domain flags, `_attempted_domains` completion semantics and keyword-only request helpers after all callers/tests/legacy adapters are migrated. |
| Verification/docs | New outcome/semantic-routing/corpus fixtures; extend named existing suites, benchmark scripts and provider smoke; update architecture/native-interaction/recovery/production docs and both standards files. |

Before deleting anything, search all imports, prompt registry references, tests, worker entry points and old checkpoint serializer references. Transitional adapters must have a removal condition based on retained-state compatibility, not an arbitrary cleanup date.

## 16. Rollout, rollback and cleanup

1. Capture the final source revision, current schema head, deployment configuration and existing image IDs. Preserve a verified database backup and recovery images; never include credentials/backups/private transcripts in Git.
2. Apply additive schema changes with established migration locking and a tested restoration procedure. Reconcile the concurrent memory migration head; test upgrade with populated synthetic legacy turns and jobs.
3. Deploy readers/frontends that understand optional outcome fields before enabling new semantic writers, or perform a coordinated maintenance-window update of backend, frontend and all workers. Drain/pin running responses; never switch their policy mid-attempt.
4. Enable the new policy through the coordinated versioned release, persisting `semantic-v3` on its turns. Release/image selection is deployment control, not an intent classifier. Reauthorize/reconcile older retained work through the defined adapter.
5. Verify ordinary conversation, real web retrieval, grouped questions, assessment queue/generation/grading, partial failure, memory/source fences and pause/retry using synthetic owned records. Check readiness, active worker stability and served frontend version.
6. Preserve versioned backend/frontend tags linked to the final commit and verify the running application source/assets match. Reuse existing dependency/model layers when dependencies are unchanged; full source builds must remain reproducible.
7. Roll back to the last tested compatible semantic release, not silently to the known broken keyword-mandatory policy. If no compatible previous semantic release exists, disable affected mutations with honest capability-unavailable responses while rolling forward; preserve reading, user history and receipts.
8. Keep additive schema and retained receipt/state data during application rollback. New writes must not be replayed by old code. A database restore is an explicit recovery operation that loses later writes, not a routine rollback step.
9. Remove only owned disposable databases/containers, test screenshots/traces, scratch scripts/logs and unreferenced test images. Retain regression tests, useful synthetic verification records, application logs, backups, rollback assets and all student data. No global prune or blanket filesystem cleanup.
10. Commit only the finished authorized changes after verification; respect concurrent work. Do not push or claim public deployment unless authorized and verified. Real public domains/TLS/proxy acceptance remain installation-specific.

## 17. Completion checklist

- [x] Current context, APIs, semantic gates and concurrent memory-work interfaces reconciled.
- [x] Keyword-based routing, preparation, direct eligibility, old-upload guessing, cache-refresh intent and mandatory tool checklists removed from the interactive pipeline.
- [x] Exact-ID, source-format, citation, URL/security, numeric-answer and provider-protocol validation retained.
- [x] Tools can be visible/enabled and unused without causing failure or speculative private reads.
- [x] Selected operations retain authorization/schema/domain admission and side-effect controls.
- [x] No universal classifier/reviewer; simple response/visible edit uses one main invocation; discovery and cache behavior measured.
- [x] Task/receipt/outcome consistency enforced through graph, persistence, API, logging and frontend.
- [x] Queued work, pending questions and partial results represented honestly; no empty saved-results claim.
- [x] Failure/partial state retains useful output and the correct recovery action, including background job retry.
- [x] Legacy fingerprints, checkpoints, summaries, source permissions, learner evidence and accepted-assessment identities preserved by compatibility paths and regression checks.
- [x] Focused browser/provider/database/runtime checks pass; performance observations are qualified in the verification record. No production p95 or full-suite success claimed.
- [x] Release source, image revision labels, recovery assets and scoped cleanup covered by the final release procedure; deployment verification recorded separately from public hosting acceptance.

This checklist is the implementation handoff: a missing gate is unfinished work, not a reason to mark the migration complete because the graph reached END.

## 18. Implementation review: latency and remaining gaps

The user reaffirmed that smart tool use, response quality and latency outrank small input-token savings. Optimize the complete interaction, including tool selection, execution, synthesis and recovery. Do not optimize only the first request's token count.

The first synthetic configured-model run after introducing outcomes exposed receipt-reference errors. Providing explicit server receipt references resolved onboarding and quiz failures. Subsequent measurements on the 40-case base corpus plus repeated critical cases showed a 2.75-second median across 64 episodes, but still contained failing cases; this is diagnostic evidence, **not release acceptance or a production latency claim**. Direct paths generally used one model call; cold agenda/memory/history paths used three to five. Each avoidable round repeated several thousand input tokens as well as adding latency.

| Gap or opportunity | Required change | Acceptance measure |
| --- | --- | --- |
| Saving a small first-call prompt adds discovery and repeated context later | Benchmark a stable expanded lean core: search, compact assessment creation, relevant learner context/recommendations, agenda lookup, history lookup and saved-memory operations. Bind only configured capabilities; defer large schemas and detailed domain prompts. | Compare total model rounds, actual input/output tokens, correctness and latency by task family. Retain one-call ordinary conversation and zero incidental tool executions. |
| Old 8,192-token ordinary budget leaves too little room for real results after new schema/context instructions | Raise ordinary input allowance to 12,288 and recovery to 13,824 within the configured 16,384 context and 2,048 output reserve. Clamp actual admission to context minus output/protocol reserve. These are ceilings, not padded payload targets. | No premature result-budget finalization for common tools; no silent loss of relevant originals/provenance. Do not enlarge output, deadlines or tool/write limits as a substitute for efficient routing. |
| Long opaque provider call IDs cause incorrect final references and repair calls | Expose short server receipt aliases, preserve native IDs for retained-state compatibility, and validate exact operation matches. | No invented receipt acceptance; no repair on normal single/compound operations; successful write remains distinct from a read. |
| Recent follow-up edits trigger unnecessary history recovery | Mark complete visible artifacts explicitly, retain their originals, and tell the main model to reuse available text. Ask about a genuinely ambiguous target before a broad history search. | Visible edit is one model call, zero retrieval calls, and preserves original content/citations. Missing original remains an honest retrieval/clarification path. |
| Native input or a job-only handoff pays for redundant prose synthesis | Permit a typed empty final decision beside the native action; synthesize the acknowledgement from actual validated results. Continue normally when an explanation is also requested. | One model selection call is supported and tested without skipping requested explanation, cards or failures. Measure actual provider uptake rather than claiming this happens every time. |
| Same-chat worker status changes without a new message or conversation revision | Refresh existing source-message metadata on worker transitions; batch server projections and fence client merges by job revision. Coalesce overlapping refreshes while retaining a pending refresh. | Completed/failed generation or grading updates without reload; stale HTTP response cannot restore an older status. |
| Resuming an already delivered background handoff could rerun the main response and enqueue duplicate work | Resume the owned worker job, reuse the delivered response/receipts, and preserve other pending tasks. A changed instruction still uses the normal amendment flow. | Background-only Resume requires no new model call and cannot create another assessment/job. |
| Memory capture and foreground finalization share a transaction | Resolve the canonical source message inside that transaction; verify opt-in, source attempt, retries, deletion and summary fences together. Background capture remains outside foreground model latency. | A memory-capture enqueue cannot fail an otherwise valid reply due to a missing transient job field; no duplicate or unsupported memory/evidence. |
| Stateless route accidentally exposes learner mutations | Filter write-capable tools from that mode using trusted operation metadata. | Stateless chat can read permitted context but cannot resolve/create a durable learner concept or launch persistent assessment/event/memory writes. |

Use a shared warmed provider transport for representative benchmarks; report cold-start effects separately. Record first useful content separately from activity and background fulfillment. Keep the synthetic fixtures honest: a fake no-result web lookup must include the real dated result envelope, and a visible original must actually be included in the conversation. Re-run the full corpus after changing the core, receipt contract or prompt policy. Additional input is justified only by a measured improvement in useful response delivery or reliability.

**Rejected experiment:** prebinding history and memory operations saved discovery for those tasks but increased unnecessary history reads during English tutoring/visible rewrites and caused a foreground preference save in a normal conversation. That candidate failed the corpus (58/64). Keep history/memory schemas discoverable; retain only the lean recommendation/agenda additions, and optionally expose assessment revision/question schemas from an actual visible assessment. Broader availability is not automatically smarter tool use. Further measurements must use this corrected candidate, not the rejected one.

### 18.1 Final optimization review

| Finding | Implementation / decision | Verification |
| --- | --- | --- |
| Automatic preparation exhausted the six-call interactive budget before an uploaded answer could be processed | Separate bounded server preparation (at most eight reads, twelve physical attempts) from the unchanged six model-selected calls and two writes. Continue to share dependency failures/cache data, deadlines and authorization. This is not a larger model loop. | Regression checks assert preparations do not consume the coordinator budget; exercise a populated chat plus attachment, discovery and answer preparation in the browser. |
| Discovery admission omitted the detailed instructions it would activate | Admit the complete prospective prompt, schemas, current evidence and result reserve together. Keep explicitly requested unused tools; prune unused defaults and, if necessary, the unrequested questionnaire schema. Preserve pruning through current-policy checkpoint restoration. | Existing schema admission, questionnaire compatibility, runtime restoration and protocol tests. |
| Assessment selection recomputed ranking inputs separately for recommendations and verification | Use the existing owner-bound `get_study_targets` snapshot once, alongside learner-context and profile reads. Do not cache it across subsequent concept mutations or turns. | Assert one ranking read per selection and retain owner/context/format admission tests. |
| Completed assessment worker results were visible to the student but absent from the next prompt | Batch-resolve only visible generation-job references to owned assessment IDs, title and count. Never load private grading keys/full assessments merely to identify a card. | Discussion, revision, typed grading and uploaded-answer browser flows. |
| A final explanation failure could hide already usable native results | Publish validated available cards with an explicit partial outcome and the real failure code. Retain private write receipts for recovery; no extra salvage model call or replay of completed effects. Lifecycle cancellation/deletion/context invalidation remains fenced. | Partial-result and persistent recovery tests; background retry uses the existing job. |

Configured-provider verification on the corrected candidate passed **64/64 synthetic episodes**, including all repeated critical cases. The mixed-cohort median was **2.976 seconds**; tools were simulated, and local tests/builds ran concurrently, so this is neither production end-to-end latency nor a controlled before/after speed comparison. One observed English correction used one model invocation, 6,673 input tokens and 1.627 seconds; agenda used two invocations, 13,480 input tokens and 2.600 seconds; recommendations used two invocations, 13,575 input tokens and 3.085 seconds. Actual token counts include repeated context across calls. Retain correctness and invocation-count evidence; do not turn these few samples into a p95 claim.

### 18.2 Remaining optimization priorities and limits

1. Measure queue wait, preparation, provider time, tool/domain time, publication, first useful content and background completion separately using existing content-free timings. A fast queued acknowledgement does not prove a fast completed assessment. Use at least 100 successful observations per cohort before accepting a p95 claim.
2. Preserve full originals, useful bounded learner packets, source evidence and compact visible artifact identities even when they cost more input. Spend additional input when it avoids retrieval, reconstruction, repairs or a second main invocation. Never send the student's entire concept inventory.
3. Keep independent reads concurrent and independent generation/grading batches bounded. Reuse successful checkpointed sections on retry; do not parallelize concept mutations, ordered learner evidence or ambiguous side effects. Cache reads by exact inputs plus their authorization/freshness dependencies, never by approximate meaning across students.
4. Continue testing the one-invocation native-handoff path. It is supported without skipping validation, but the provider often chooses a second explanatory invocation; current acceptance must report that actual behavior.
5. Investigate streaming validated answer content as a separate measured change. The typed final decision is currently buffered before public text is released; do not stream raw tool JSON, unverified success claims or rejected questions merely to improve a first-token metric. Keep cancellation and replacement of provisional text correct.
6. Frontend route/card/diagram splitting already exists. Large optional diagram chunks remain a cold-load opportunity; measure which chunks are fetched by ordinary chat before changing bundling. A build-size warning alone does not prove a response-latency regression.
7. Do not trade correctness for a smaller core automatically. Keep the core stable and capability-driven; expand only when held-out conversations show fewer rounds without incidental reads/writes. Do not introduce keyword routing, a universal pre-classifier or a second mandatory reviewer.
