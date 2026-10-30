# Prompt, tool discovery, and interaction optimization

Implementation and verification record, 27 October 2026. The [research and proposal](Tool_Discovery_and_Prompt_Optimization_Research_2026-10-26.md) explains the original system and alternatives. This document records what is implemented, measured, and still unverified.

The [follow-up review](Tool_Optimization_Review_2026-10-27.md) records additional correctness fixes, expanded verification, and remaining improvement priorities.

## Changes that affect ordinary requests

| Area | Implemented behavior | Benefit |
|---|---|---|
| Capability discovery | Central domain/outcome/tool registry; available tools only; retain newly discovered pending tools and re-enable pruned tools | Consistent discovery without carrying every schema |
| Candidate selection | Cheap request hints distinguish supplied-content transformations, personal history, preferences, agenda, Library, learner progress and external research | No extra routing model; fewer irrelevant schemas and discovery rounds |
| Prompt composition | Conditional web/domain instructions; shorter recovery contract; summaries no longer automatically bind memory/history tools | Lower routine input cost |
| Preparation | No speculative RAG search or broad learner reads on every request; explicit source ownership/eligibility validation remains | Removes unnecessary embeddings, retrieval and domain calls |
| Completion | Explicit requested lookup/action must have a domain attempt; requested practice must have a durable result; one bounded repair | Prevents unverified answers or prose substitutes from silently completing an action |
| Copyable artifacts | Universal prompt requests fenced `text` for reusable prose and correct language fences for commands/code, even one line; existing Prism component copies exact payload | Copy button without special user wording |
| Visible capabilities | Complete chat starters, visible Study material picker, grounded Practice this material action | Features appear where useful without feature-name knowledge |
| Source picker | Library/context lists load when needed, rather than on ordinary chat startup | Two startup requests removed in the browser fixture |
| Settings | Saved response updates shared profile immediately; focus/visibility fallback coalesces reads if cross-tab messaging fails; backend reads current profile each request | Next request uses saved preferences without login/logout |
| Concurrent profile editing | Original edit version preserved; foreground refresh retains unsaved draft; conflict requires explicit reload | Immediate refresh cannot silently overwrite another edit |

Routing hints are candidate selection, never authorization or a language allowlist. The model can discover other supported tools. Domain services still own permissions, provenance, state transitions and validation. Complete lookup measurements include both initial and final calls; reducing the initial prompt alone is not the objective.

## Practice and time to useful UI

Ordinary chat practice defaults to interactive delivery, independent of whether a question has a written answer. Written and printable delivery remain explicit choices, with legacy records retaining their previous rendering behavior. Compact generation schemas cover ordinary requests; advanced paper structure remains discoverable.

Eligible explicit-topic practice of one to three questions uses deterministic structure and one content-generation stage, retaining private key, rubric, question, marks, concept and domain validation. Complex requests retain the full workflow. Independent preparation reads run concurrently. A durable public assessment reference can render before narration completes, without streaming private grading data or executable model-produced UI. Pure creation can reuse the validated title without another model narration call; compound explanation requests keep their explanatory response. Workers drain queued work without the idle delay between processed jobs.

## Measured differences

The [general evidence](verification/General_Tool_Optimization_Evidence_2026-10-26.json) contains 42 first-request snapshots across 21 queries with web enabled/disabled, plus five complete scripted read workflows against archived reference source and current source. These are offline controlled estimates using the same tokenizer and synthetic services, not production latency measurements.

| Complete scripted task | Estimated input before → after | Reduction | Model rounds before → after |
|---|---:|---:|---:|
| Earlier-message lookup | 9,706 → 6,591 | 32.1% | 3 → 2 |
| Saved preferences | 9,429 → 6,320 | 33.0% | 3 → 2 |
| Agenda lookup | 9,276 → 4,557 | 50.9% | 3 → 2 |
| Explain Library notes | 5,936 → 5,062 | 14.7% | 2 → 2 |
| Latest-news lookup | 6,996 → 6,408 | 8.4% | 2 → 2 |

In the first three fixtures, discovery plus domain execution falls from two tool invocations to one. Some first requests grow because they now bind the correct capability immediately instead of deferring it behind discovery. The universal prompt itself grows to teach outcomes/copyable artifacts; smaller recovery and conditional fragments offset that cost. Do not describe every individual prompt as smaller.

The [implementation evidence](verification/Tool_Optimization_Implementation_Evidence_2026-10-26.json) preserves four paid synthetic provider calls, all passing, with automatic retries disabled: ordinary practice routing, Urdu routing, a fenced Bash artifact, and validated compact question generation. Observed individual call times were approximately 0.66–1.79 seconds. These calls used no application persistence and establish neither production p95 nor total chat latency. Further comparisons and regression checks were offline.

## Verification

| Check | Result |
|---|---|
| Expanded backend regression suite | 184 run: 135 passed, 49 checks skipped; see follow-up review for database limitations |
| General offline evaluation | 42 snapshots plus five scripted complete workflows; zero paid calls |
| Bounded configured-provider probes | Four calls, four passed, zero retries |
| Frontend production build | Passed, including strict TypeScript |
| Theme and UI standards checks | Passed |
| Mocked browser regression suite | 40 passed plus final focused 9-case suite, covering 41 distinct cases; includes card refresh/handoff and saved-card conversation actions |

Browser tests use mocked APIs. Backend fixtures preserve the real coordinator, schemas and relevant workflow validation while replacing providers/persistence where appropriate. Existing product-page fixtures were updated to the current combined page endpoint contracts. No application database was used for destructive test setup.

## Reproduce offline comparisons

From the repository root, archive the intended reference before changing the checkout:

```powershell
git archive --format=zip --output=.cache/smart-tools-reference.zip HEAD backend/app backend/testing
Expand-Archive .cache/smart-tools-reference.zip .cache/smart-tools-reference -Force
$env:TIKTOKEN_CACHE_DIR='backend/.cache/tokenizers'
.venv/Scripts/python.exe backend/testing/general_tool_evaluation.py --check
```

The reference archive must match the reported reference revision. The evaluator does not call a paid provider. `backend/testing/smart_tools_evaluation.py` additionally supports explicitly bounded live synthetic probes; avoid rerunning live mode merely to update offline counts. Original research evidence remains separate from implementation evidence.

## Deployment, rollback, and remaining work

Docker's engine was unavailable in this environment. Database integration checks, rebuilt-container parity, and production end-to-end latency remain unverified. These source changes have not been deployed. No schema migration is required: delivery uses existing assessment preferences JSON with backward-compatible fallback.

Before deployment, run the skipped database suites against isolated migrated storage, rebuild frontend/backend/worker images together, and smoke-test owned persistent chat, retrieval, generation, settings saves and next-turn preferences. Compare metadata-only routing, actual provider usage, model rounds, queue wait, request preparation and time to usable UI across general request families. Roll back the application images together if domain correctness, routing quality or latency regresses; retain canonical records and attempts.

The proposal's larger capability-embedding router, adaptive learned ranking and broad production latency dashboard are not implemented here. Current routing deliberately adds no model call or vector lookup; discovery remains the fallback for unfamiliar phrasing and languages. Native UI is available only for supported typed components. The current evidence supports lower controlled task cost and fewer unnecessary calls, not a claim that every request finishes within a fixed number of seconds.
