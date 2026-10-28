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
The installed-name catalog and every response glyph are separate lazy assets,
requested only when used. The catalog contains import functions, not glyph data. Names never
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
typing, unchanged refresh and font-size change. That original measurement used the common-icon fast path, subsequently removed below.
Typing p95 was **13.1 ms**, with zero typing long tasks; the full observation window
included one 54 ms long task outside typing. These remain local machine measurements.
Both images and all application services were refreshed; disposable outputs were
removed after recording this evidence.

### Every response icon loads on demand

Removed the 15-icon eager registry after the follow-up requirement. `InlineIcon`
now has only a type import from Lucide. Its first actual icon lazily loads the name
catalog, then invokes only `dynamicIconImports[name]()` for that glyph. Catalog
entries are import functions, not eagerly loaded icon implementations. React/module
caching reuses repeated requests; placeholders remain local to each icon.

All **31** rich-chat/performance checks passed again. Network coverage verifies no
catalog request for an ordinary response, exactly one catalog and one Anvil module
request for 32 repeated Anvil icons, and no unrelated AArrowDown request. The same
200-message/100-icon fixture recorded zero completed-component/icon rerenders,
typing p95 **13.3 ms**, and no measured long tasks. The frontend image was refreshed.

## Recharts and canvas resize hardening

Added Recharts 3.10.1 with the matching React 18 react-is peer. Recharts JSON fences
support LineChart, BarChart, AreaChart, ComposedChart, PieChart, RadarChart and
ScatterChart. This is a validated data contract using Recharts component/dataKey
names, not executable JSX. The shared UI prompt owns the model usage rules.

| Boundary | Implemented behavior |
|---|---|
| Loading | Reused/generalized the diagram viewport gate into DeferredVisual with one shared observer. Text does not load charts; offscreen charts wait. Each chart family imports separately and shared dependencies are reused. |
| Validation | 24,000 characters, 200 rows, six series, three charts per response; 24 categories for pie/radar and at least three for radar. Unknown props, callbacks, unsafe field keys, missing/nonfinite values, duplicate series and invalid pie/radar data are rejected locally. |
| Data isolation | Original names/values stay in source/tables. Only canonical app-owned field names enter drawing data, preventing names such as fill/onClick from becoming shape props. Text remains React-escaped; no model resource fetching or code evaluation. |
| Interaction | Exact data table, source/copy, viewport-sized fullscreen, visible units, native Close/Escape/focus restoration, accessible keyboard tooltips and CSS theme colors. |
| Motion | Small charts use 250ms reduced-motion-aware animations. Above 120 row-series pairs, animations are disabled. Tooltips remain immediate. Single-point areas retain visible dots; null gaps are not invented as zero. |
| Stability | Parsed specs have a 30-entry owner-cleared cache. Figures and canvases are memoized and have no conversation/theme subscriptions. Loading, invalid data, rejected chunks and render errors stay local with data/source recovery. |
| LightRays flash | ResizeObserver previously cleared the canvas by resizing its backing buffer after drawing; repaint waited for another frame. It now marks dimensions dirty and performs resize/redraw in one animation-frame callback. No preserveDrawingBuffer overhead or shader/intro restart was added. |

Verification actually completed:

- **65 production browser checks passed** across chart, LightRays, rich-chat and
  200-message rendering suites. Coverage includes all seven families, settled bar
  height against axis values, negative/zero values, null gaps, mixed composed series,
  single-point areas, keyboard tooltip values/units, mobile dark fullscreen, exact
  data/source, failed entry/family chunks, malformed data, escaped resource-like
  labels, field collisions, lazy imports and count bounds.
- The new canvas frame-order regression **failed against the old build** in normal
  and reduced motion, then passed after the fix. Resize and redraw never straddle a
  test-observed frame; existing no-rerender/no-shader-recreation checks still pass.
- Three visible chart families recorded **zero** ChatMessage, MarkdownContent,
  RechartsFigure and ChartCanvas rerenders during typing, unchanged refresh and font
  changes. Typing p95 met the under-50ms budget while short animations were enabled.
  The separate 200-message/100-icon/native-bar fixture measured **13.4ms** typing p95
  with zero measured long tasks and no chart/diagram module requests.
- **Six configured-provider scenarios passed**. The actual generated bar-chart JSON
  was additionally validated using the exact frontend parser and supplied values
  20/30. Reusable check: `node frontend/scripts/verify-chat-charts.mjs` after the
  backend provider script generates its temporary report.
- Strict TypeScript/Vite build, UI/theme checks and dependency audit passed; npm
  reported **zero vulnerabilities**. Optional Mermaid/layout chunk warnings remain.

Both Docker images were rebuilt; backend, frontend and all five application workers
were recreated from the refreshed images. Local readiness/frontend responses and
container health were checked after rollout. Disposable logs, screenshots and model
verification output were removed after recording results here. No schema migration
or public deployment is involved; the deployment-specific gates above still apply.

## Common UI plus on-demand references

The UI policy now has two tiers in the same `chat_ui.py` resource. CHAT always
includes the compact common guide; `present_choices` and `request_input` are bound
without discovery. Mermaid, icons, semantic colors and simple inline bars are
immediately usable. Advanced charts, disclosures, custom hex colors and native
multi-bar references load through `enable_workflow_tools(ui=[...])`. All domain
capabilities remain in the catalog and retain existing authorization/validation.
No extra classifier or per-response review call was introduced. Selection is not
restricted by a keyword/language allowlist.

Reference activation is scoped to the current turn, deduplicated in stable order,
retained through final/budget-limited model rounds, and checked against the combined
instruction/schema budget before admission. Failed admission restores previous
state. Requesting bars also binds the existing `present_visuals` tool. Exact tool
and module discovery still works. Compatible examples in history can be reused;
other unfamiliar advanced formats require their reference before first use.

| Verification | Result |
|---|---|
| Backend suites | **53 passed** in Python 3.12 with disposable PostgreSQL: UI tiers, prompt efficiency, assessment intent, orchestration and chat persistence. |
| Real-auth browser journeys | **6 passed**, covering choices, custom input, forms, native bars, cold assessment creation and grading/restoration. The configured dev API proxy was used; an initial preview-mode harness could not reach the isolated backend and was corrected before acceptance. |
| Configured AI | **13 synthetic scenarios passed**, including proactive topic clarification, Spanish forms, explicit prose-only output, icons, Mermaid, advanced references and chart follow-up edits. No domain records created. |
| Chart contracts | Both actual generated chart JSON objects passed the exact frontend validator; values remained 20/30 and the requested follow-up 25/30. |
| Common paths | Plain answers, icons and Mermaid used one model round. Choices/forms/proactive clarification used two (create card, then final response), with no discovery round. |
| Rare paths | First chart, disclosure and custom-color use loaded their reference in one discovery round, then answered. Native multi-bar cards used discovery, card creation, final explanation. |
| Follow-up | A fresh turn reused the compatible chart example and changed only the requested value, in **one model round with no lookup**. |

Prompt-size comparison against commit `44ce086`, using the same LangChain
approximate counter and compact tool-schema JSON:

| Packet | Before | After |
|---|---:|---:|
| Always-on UI guide only | 1,430 | 458 |
| UI guide plus every initially bound tool schema, including discovery | 1,594 | 1,328 |

That is about **68% less guide text** and **16.7% fewer UI-related initial input
tokens even after binding both common input tools**. These are estimates for the
changed packet, not percentages of the full request or billed cost. Core/history
and domain context are excluded. The provider-reported input usage and per-round
wall times were recorded by the reusable verification script. More importantly,
common input workflows remove a discovery round, while rare first-use formats
intentionally pay an extra round instead of sending their full guide every time.
Provider caching can help but is not assumed or guaranteed.

One intermediate live chart check exposed an incompatible generated format; the
compact guide was strengthened to require loading an unfamiliar advanced reference
before first use. The full final 13-scenario run and frontend chart validation then
passed. This is targeted quality evidence, not a guarantee that every subjective
presentation choice will be optimal.

Local images/services were refreshed after verification. Disposable database,
browser outputs and synthetic-provider logs were cleaned after recording these
results. Reusable tests and verification scripts remain. Unrelated audit artifacts
are outside this change.

## Visual repair and export acceptance — 2026-10-27

The saved React/Angular response failed in the browser because a blanket data-URI guard matched the ordinary label `Data: TanStack Query + Zustand`. The API turn succeeded; it was not a model or backend Mermaid failure. The guard now distinguishes actual resource URIs, with the exact saved diagram covered by a browser regression. Render failures show an explanation and retain source.

Comparison bars accept `group`, `series` and optional named `color`, share scale/unit validation, and assign stable series colors. Complete legacy comparisons can be paired for display without rewriting saved data. Chart series accept safe named or six-digit hex colors, with optional category palettes. Mermaid supports a restricted safe style subset and readable label contrast.

Generic icons accept Lucide names, public HTTPS image URLs, or SVG path data with optional viewBox/variant. Assets load on demand with bounded shared caching, size/time limits and placeholders for failures. No framework-specific logos were added. Arbitrary SVG markup is not injected.

Mermaid and all seven chart families offer SVG and PNG downloads. Export code loads only after a click. Chart exports wait for stable geometry, inline computed styles, include title/units/legend and retain the current theme background. Downloads do not require another model request.

The saved response contained no colored-text directives. The renderer was working; central UI guidance now gives concise benefit/caution usage and a native-comparison example. All UI usage instructions remain in `backend/app/langchain/prompts/chat_ui.py`, including the on-demand references.

Verification before export work: 74 targeted browser checks passed, two backend comparison-contract checks passed, and 16 configured-provider scenarios passed. Actual generated chart payloads passed the frontend validator. The 200-message performance scenario recorded p95 13.4ms, no long tasks and no completed-message rerenders. Final export/build and rollout results are recorded below when complete. These checks use synthetic fixtures, not edits to learner records.

Final acceptance: **76 browser checks passed (2.3 minutes)** against the production build, including every chart-family SVG, PNG signatures, Mermaid SVG/PNG, fullscreen, icon fallback, colors, lazy loading, rerender isolation and LightRays resize/sidebar behavior. Production TypeScript/Vite build, theme checks and UI checks passed. One export check caught unresolved theme attributes in SVG; computed styles now replace those attributes, and the full final suite passed.

Local rollout: rebuilt isolated UI contexts into `mentra-backend:latest` (`4ae2a8c42fe3`) and `mentra-frontend:latest` (`c47459e75010`). Backend and frontend healthy; frontend HTTP and API readiness both returned 200. All five workers/summarizer roles use the rebuilt backend image. Database remained at `20261025_0031`. Unrelated in-progress learner/topic changes were excluded from the images and commit. No remote registry push or public deployment was performed.

## Live visuals, stable drafting, and Events — 2026-10-28

- Composer autosizing measures an offscreen, noninteractive textarea instead of temporarily collapsing the visible field. Collapsing the visible field clamped the chat scroll position even when its final height did not change. The conversation uses native minimum-height sizing; actual composer resizing is reconciled before paint. A visible disclaimer stays visible while typing/wrapping/deleting, and intentional upward scrolling remains authoritative.
- Recharts accepts `enableControls: boolean`, default false. Only illustrative/exploratory data should enable it; canonical comparisons and recorded facts stay read-only. Compact point/series selectors, one slider and an exact numeric input sit below the chart with Reset. Numeric scatter X values are editable too. Changes are local, validated and frame-coalesced; they update the current table, source and SVG/PNG export without rewriting the message. Reset restores the original data. Controls load only for enabled charts. Interactive chart updates skip transition animation to track inputs immediately; ordinary chart animations are unchanged.
- Standard Markdown images use `![alt](https://host/image.jpg "Attached caption")`. Captions stay in the image container and fullscreen viewer. Native lazy loading/async decode keep text rendering independent of image downloads. Known public HTTPS sources only; blocked/broken images retain their labels and a local fallback. Linked-image sources remain available in the caption. The image URL guard is shared with generic icon assets.
- The centralized UI guide and native receipts describe actual ordering: final answer text first, native cards below; Markdown visuals appear at their written positions. Model checks cover control selection, supplied-data preservation, image captions and native-card placement.
- Events use contained agenda/suggestions panels with responsive filters/cards. Viewing and editing use the existing Dialog primitive. Editing checks dates and saves in one submit, retaining a manual choice only for an explicitly edited ambiguous local time. Direct Add event approves the suggestion as-is through the existing revision-fenced backend endpoint: no editor, preview step or extra Save click. Edit details remains an independent optional action. The current page retains bounded terminal receipts so refresh cannot erase a just-saved confirmation. Calendar export, status actions, reminders and deletion remain available in the details dialog.

Reusable coverage: `renovation-live-visuals.spec.ts`, existing Recharts/rich-content/LightRays/performance suites, real event journeys and the focused `verify_chat_ui.py --only ...` configured-provider checks. Final acceptance results follow below.

Final acceptance: **92 production browser checks passed (2.5 minutes)**, plus **8 focused final chart-control checks** after freezing hidden chart/table updates during fullscreen editing. **Nine real event/scroll checks passed**, and the isolated one-click proposal journey passed with assertions for exactly one approval POST, zero temporal previews and no editor dialog. A concurrent run of that journey exceeded its default test deadline; the isolated final run completed in 18.8 seconds. Initial development-mode chunk assertions were a harness mismatch; final asset/fallback/performance acceptance used production bundles.

**27 backend interaction/prompt/reply-policy checks passed**, as did production builds, UI/theme checks and targeted static checks. **Five configured-model scenarios passed** (exploratory controls, fixed comparison, captioned image, native input placement and static visual placement); both actual generated chart payloads passed the exact frontend parser with supplied values preserved. No learner records were created by model checks.

The 200-message/200-bar performance fixture recorded **zero completed message/content/card/icon rerenders**, typing p95 **9.8ms** and **no typing long tasks**. One 80ms non-typing task was recorded; this is measured local fixture evidence, not a guarantee of text-equivalent cost for arbitrary charts or remote image downloads. Editable charts coalesce slider updates to one frame, skip update animation and freeze the hidden inline plot/table during fullscreen interaction. Controls/data changes remain local and explicitly resettable.

Local rollout: rebuilt/restarted `mentra-backend:latest` (`6580bd454ec9`) and `mentra-frontend:latest` (`23fc81e5c9a1`). Both are healthy; frontend HTTP and API readiness returned 200, and every background service uses the rebuilt backend image. Deployed asset checks found the lazy ChartControls bundle and captioned-image viewer; the running backend exposes the updated UI guide. Disposable test database/volume and temporary reports/traces were removed. No registry push or public deployment was performed.
