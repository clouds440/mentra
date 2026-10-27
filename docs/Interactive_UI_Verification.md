# Interactive chat UI: implementation and verification

27 October 2026. Implements the [interactive UI plan](Interactive_UI_Implementation_Plan.md), including chat typography, static numeric bars and minimal rendering overhead. Contracts and model guidance are documented in [Native chat interactions](chat-interactions.md).

## Delivered behavior

| Area | Implementation |
|---|---|
| Custom topics and small forms | Existing choice cards now open attached short/long text fields. Compact forms reuse existing controls, with server validation and canonical persisted receipts. Labels and IDs have no hidden behavior. |
| Static numeric bars | Typed `present_visuals` tool supplies difficulty, rating, quantity and comparison bars. Exact values/scales and percentages remain visible. No automatic conversion of prose percentages and no live progress requirement. |
| Durable interactions | Existing ownership, transactions, revisions, pending sends and operation IDs are reused. Legacy request fingerprints remain compatible. |
| Workflow review | Existing Events cards remain authoritative. A real checkpoint pause is prepared before pending review; workflow operations are serialized and terminal proposal races reconciled. |
| Rich responses | Shared Markdown supports Mermaid, allowlisted semantic/custom colors, explicit bars, callouts and disclosures. Raw HTML stays disabled; copy preserves readable content and literal code. |
| Mermaid | Lazy local rendering, strict configuration, bounded source/edges, theme support, accessible metadata, source/copy, expanded dialog and sanitized SVG download. |
| Main chat font | Bundled Inter with license and italic assets. Settings offers Small/Medium/Large (15/16/18px), Medium default. Browser-local persistence and cross-tab sync; scoped to main chat. |
| Central instructions | `backend/app/langchain/prompts/chat_ui.py` is composed once through the existing CHAT registry. Domain prompts retain their domain rules. |

## Hardening findings resolved

| Finding | Fix and regression coverage |
|---|---|
| Sidebar toggle rerendered LightRays | Memoized component and stable outlet context. Repeated collapse/expand and typing preserve canvas identity, render count and shader program count; existing canvas resolution still follows resizing. |
| Unknown outcome could reuse an old answer payload | Preserve original payload/UUID, freeze the uncertain form and expose explicit original-answer retry. Older operations cannot clear newer pending sends. |
| Optional diagram failure could disrupt chat | Local error boundary preserves source and surrounding text/composer. Failed chunk loading is covered. |
| SVG rewrite/cache work could grow | One-pass ID/reference rewriting; memoized expanded SVG. Owner-scoped LRU limited to 30 entries/two million characters, one million per SVG; owner changes fence late jobs. |
| Encoded CSS could load resources | Normalize escapes/comments before rejecting resource-loading syntax; sanitize generated/exported SVG. External requests are checked in browser coverage. |
| Rendering edge cases | Nested rich directives, very small/large exact numeric values, optional blank selections and future interaction kinds now have explicit behavior and coverage. |
| Font preference changed while chat unmounted | Re-read persisted preference on subscription; cross-tab and blocked-storage behavior retained. |
| Events initialization race/unnecessary work | Reconcile terminal state after checkpoint preparation; automatic admission avoids preparing an unused graph. |
| Compound practice request missed | Recognize explicit requests following punctuation while preserving negative exclusions. |

## Rendering performance

Native bars and semantic colors use DOM/CSS. Static cards have no conversation subscription. Completed messages and Markdown are memoized; authoritative refreshes preserve unchanged identities while checking all metadata. Chat font size uses one inherited CSS token. Ordinary safe single-line text bypasses Markdown parsing; directive parsing runs only when required. Custom colors/diagrams share one theme observer. Mermaid loads near the viewport and yields before layout; ordinary bars do not request it.

Production Chromium measurement from `renovation-rich-performance.spec.ts`:

| Measurement | Result |
|---|---|
| Conversation | 200 messages, 200 static bars and inline color |
| Completed ChatMessage / MarkdownContent / static ChoiceCard rerenders during typing, unchanged refresh and font change | **0 / 0 / 0** |
| Typing input-to-next-frame p95 | **7.6 ms** |
| Long tasks in measured window / typing | **0 / 0** |
| Mermaid requested for native cards | **0** |
| Real metadata change | Correct affected meter updates from 3 to 2 |

These are local machine measurements, not a universal latency guarantee. First-use diagram download/parsing/layout costs more than plain text; surrounding text is not gated on it. The optional Mermaid/layout chunks still produce Vite size warnings and remain lazy.

## Verification actually run

| Check | Result and scope |
|---|---|
| Frontend production build | Strict TypeScript and Vite passed. |
| Theme/UI standards | Both checks passed. |
| Production UI/browser suites | **41 passed**: rich-chat, rich-performance, smart-tools, LightRays and existing performance suites. |
| Real-auth/database browser journeys | **6 passed** against isolated PostgreSQL: custom topic/forms/static bars, mobile choices, cold first-chat and existing assessment creation/restoration/grading. Only AI is a deterministic fixture. |
| Backend database/domain/prompt tests | **75 passed** in the Python 3.12 application image: 52 interaction/Events/prompt/MCQ checks plus 23 assessment-intent/orchestration checks. |
| Configured AI provider | **4 synthetic scenarios passed**, including typed custom input, form, static comparison with normal explanatory continuation, and direct answer without unnecessary UI. No learner/domain records created. Reusable script: `backend/scripts/verify_chat_ui.py`. |
| Dependency checks | `npm audit --audit-level=high`: zero vulnerabilities. Image `pip check`: no broken requirements. |
| Configuration/diff checks | Compose configuration and `git diff --check` passed. |

Earlier broader checks exposed an incorrect MCQ fixture score, a cold-start fake-model target assumption, a browser harness missing its evidence-worker phase, obsolete result-view assertions and the compound request issue above. These were corrected and their full affected suites rerun successfully. Grading policy, learner evidence rules and private assessment keys remain authoritative.

## Local delivery and deployment boundary

No new tables or data migration are required. Existing saved choice cards retain their definitions; custom input needs a new/input-enabled card. Historical conversations are not rewritten.

Both Docker images were rebuilt. Backend, frontend, assessment worker, Events worker, files worker, RAG worker and summarizer use the refreshed images. Backend/frontend health, frontend HTTP 200, API readiness, running interaction schema fields, bundled font/CSS and font license were checked after rollout.

Disposable test databases, traces, screenshots, temporary baseline/config files and test/build logs are removed after recording results here. Reusable regression tests and the configured-provider verification script remain; runtime data and tokenizer caches are retained.

This verifies the local Compose rollout. `.env.production` is absent; public deployment still requires deployment-specific configuration, origins, TLS/proxy/firewall, secrets, backups and capacity checks in [the production runbook](production-readiness.md). No public deployment or push is performed by this change.

## Diagram label/fullscreen follow-up

The installed Mermaid renderer reads the global `htmlLabels` option. Setting only
`flowchart.htmlLabels` left labels inside `foreignObject`, which the SVG sanitizer
correctly removed. The app now sets both flags to false, producing native SVG text
without relaxing sanitization. A new regression reproduced the empty-label failure
before the fix; all eight diagram-family checks now require visible nonempty text.

Expand now opens a viewport-sized native dialog instead of the shared small modal
frame. The diagram fits the available area below a persistent Close control;
Escape dismisses it and restores focus. Desktop viewport dimensions and mobile
dark-mode text, fullscreen bounds, Close visibility and focus restoration are covered.
The production build, UI/theme checks and 27 rich-chat/performance browser checks
passed. The frontend image was rebuilt and the local frontend service refreshed.

## Inline Lucide icons

The existing rich Markdown transform accepts `:icon[BookOpen]` (PascalCase or
kebab-case). Existing Lucide dependencies are reused; no new package is required.
Common explanation icons render synchronously. The full installed-name catalog and
uncommon glyphs are separate lazy assets, requested only when used. Names never
become arbitrary module paths, URLs, SVG or DOM properties.

Unknown/invalid names, pending loads and catalog/glyph import failures render an
empty, fixed one-em CSS placeholder. A local error boundary isolates render errors.
Icons inherit text color/size, are decorative beside essential words, and are hidden
from screen readers. Plain-text copy omits icon tokens while preserving code examples.
The transform caps rendered icons at 32 per response; lazy component definitions
are bounded to 64. Model usage instructions remain in the shared chat UI prompt.

Production build and UI/theme checks passed. **31 rich-chat/performance browser
checks passed**, covering installed/uncommon names, unknown names, invalid paths,
catalog and glyph network failures, copy, count limits and ordinary prose/code.
The configured-provider check passed all **five** scenarios, including icon tips.
One earlier browser run timed out with a blank startup page during concurrent image
building; the complete suite passed after the build finished.

The performance fixture includes 200 messages, 200 bars and 100 icons. Completed
ChatMessage/MarkdownContent/ChoiceCard/InlineIcon rerenders were all zero during
typing, unchanged refresh and font-size change. Common icons requested no catalog.
Typing p95 was **13.1 ms**, with zero typing long tasks; the full observation window
included one 54 ms long task outside typing. These remain local machine measurements.
Both images and all application services were refreshed; disposable outputs were
removed after recording this evidence.
