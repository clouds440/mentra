# Mentra frontend renovation plan

Date: 14 October 2026. Status: implemented; validation evidence is recorded in [the renovation report](docs/Frontend_Renovation_Report.md).

Implementation adjustment: the user explicitly requested compact elements rather than bulky padding. The delivered system uses 32/36/40px desktop actions, 36px fields, 9px control corners, 14px panel corners and 16px panel padding. Touch icons retain 44px hit areas. These delivered dimensions supersede the larger proposed defaults below; feature positions and preservation requirements remain applicable.

## 1. Outcome and scope

Renovate the complete existing frontend into a quieter, sharper, more consistent learning workspace. Improve visual hierarchy, control alignment, responsive behavior, loading continuity, rendering cost and interaction feedback. Preserve the familiar locations of navigation, conversations, the composer, account controls, page actions, tabs and feature sections. Move a control when its relationship to the content is unclear, its placement causes crowding, or responsive evidence shows a collision.

The direction is restrained: neutral surfaces, readable text, a limited accent, modest radii, predictable spacing, crisp controls and small purposeful motion. The result should feel faster both because less work happens in the browser and because content stays stable while work happens.

Scope includes login/registration, onboarding/calibration, the application shell, chat/history/composer, attachments, voice, citations/source readers, Library/list/upload/detail, assessments/create/attempt/review, Progress/Learning/Events, Notifications, Settings/Profile/Memories/preferences, and every shared primitive used by these screens.

This is a renovation of existing capabilities. Backend workflows, saved records, routes, permissions, assessment semantics and API contracts remain constraints on the work. New dashboards, calendar modes, analytics, navigation destinations or product features are separate work.

## 2. Evidence and baseline limitations

The plan is grounded in the current checkout: route configuration, shell/navigation, global CSS/Tailwind, shared controls, feature pages, state/cache/refresh modules, Markdown/highlighting, frontend standards and Playwright configuration/tests were inspected. The working tree was clean before this document was added.

Historical UI work informed preservation requirements; the current source was checked independently. In particular, Events and Notifications are implemented in this checkout, even though older planning notes described them as future work.

No live browser visual audit, profiler session, fresh build or runtime test run was performed for this planning pass. Visual defects below are distinguished from source findings. Phase 0 must supply screenshots and measurements before treating proposed palette, spacing or placement changes as visually validated.

Existing `frontend/dist/assets` contains an entry JavaScript file of 669,063 bytes and entry CSS of 52,648 bytes, both dated 13 October 2026. These are existing uncompressed artifacts, not a fresh baseline, transferred sizes, route totals or proof of runtime slowness. Rebuild and measure the route dependency graph before setting final reduction targets. Numerous separate Prism grammar files already exist; their presence on disk does not mean every grammar is downloaded at startup.

### Current foundations to extend

- React/TypeScript/Vite/Tailwind and `lucide-react`; `cn` resolves utility overrides.
- Semantic palettes and bootstrap/provider synchronization for Light/Dark/System.
- `WorkspaceHeader`, `WorkspaceEmpty`, `page-container` and `workspace-*` patterns.
- `Button`, `Input`, `Textarea`, `Select`, `Popover`, `Toggle`, `FileInput`, `Pagination`, `Skeleton` and `Spinner`.
- Owner-scoped chat persistence, bounded message windows, durable turn recovery and dedicated chat scroll management.
- An owner-scoped 30-second page cache, request deduplication, invalidation and page refresh hooks.
- Shared Markdown rendering, worker-based code highlighting and some existing lazy feature imports.
- Playwright feature coverage using an isolated backend/database setup and theme bootstrap checks.

## 3. Source findings and targeted fixes

Paths in this document are repository-relative. A finding describes the inspected source; browser impact still requires the baseline where stated.

| ID | Current evidence | Renovation fix | Acceptance |
| --- | --- | --- | --- |
| F01 | `styles/global.css` assigns transitions to every element and pseudo-element once theme-ready; `aside` also receives a broad rule. | Replace blanket transitions with explicit interactive/surface/motion rules. Preserve first-paint theme correctness; theme color easing must not override local transform/opacity behavior. | No universal transition selector; hover, theme switching and local motion work together without initial animation. |
| F02 | `ui/Card.tsx` defaults to a 2rem radius, strong border, large shadow and backdrop blur; workspace panels use different treatments. | Make the default card a quiet semantic surface; offer limited explicit elevation/padding variants and migrate auth/onboarding overrides deliberately. | Auth, forms, cards and panels follow one surface/radius hierarchy; blur is absent from ordinary opaque cards. |
| F03 | Color tokens exist, but radius, elevation, control geometry, typography and motion are scattered through utilities and CSS. | Define a small shared geometry/type/elevation/motion vocabulary and migrate repeated patterns. | Repeated roles have one definition; exceptions are named and justified. |
| F04 | `AppLayout.tsx` displays a non-chat route title in the floating controls; feature pages also display an H1. | Retain the floating navigation toggle and bell; remove the redundant visual route label after confirming page-title/clearance behavior. | One visible main title on ordinary pages; chat remains free of a repeated title; controls never overlap headings. |
| F05 | Shell/menu/composer controls commonly use 28–36px visual boxes; voice cancel and attachment remove are smaller. | Keep compact glyphs, enlarge touch hit areas and spacing where needed through a shared icon control. | All controls remain reachable at narrow sizes and coarse-pointer use; no overlapping invisible targets. |
| F06 | Mobile sidebar is translated offscreen when closed; inspected code has no modal focus, Escape, inertness or focus-return management. Collapsed state also removes `ConversationList` even while mobile navigation is open. | Give mobile navigation an explicit modal lifecycle; separate desktop collapse from mobile content visibility. | Hidden navigation cannot receive focus; Escape closes; focus returns; open mobile navigation includes history regardless of desktop collapse state. |
| F07 | Settings, Progress and Assessments independently implement tab keyboard logic and IDs; inline border styles coexist with shared segmented tab CSS. | Introduce one controlled `Tabs` primitive with stable IDs/roving focus; keep query routing and panel mounting policy in features. | One tab appearance and keyboard contract; deep links, draft retention and back/forward remain correct. |
| F08 | `Button` has only primary/secondary/ghost; navigation links and destructive actions restyle themselves. Material deletion uses primary styling. | Share button styles with link actions, add a restrained destructive variant and an icon-control wrapper. | Navigation remains a real link; destructive confirmation is recognizable; buttons are not nested in links. |
| F09 | `Button loading` inserts a spinner before children. Several material/event actions share one `busy` value, causing unrelated controls to display loading. | Reserve loading geometry; separate operation identity from disabled safety constraints. | Only the active action spins; other actions may disable when necessary; captions and widths stay stable. |
| F10 | Detail pages and feature forms repeat borders, headings, labels and action rows; assessment answers and conversation rename bypass shared fields. | Reuse compact field/section/action patterns and existing inputs, retaining native validation and feature semantics. | Consistent label/help/error spacing and focus; raw custom controls remain only where the interaction demands them. |
| F11 | Native dialog markup/styles are duplicated across source viewing, memory confirmation and material deletion. | Wrap native `<dialog>` with a shared modal frame/confirmation pattern; keep specialized reader content in its feature. | Consistent sizing, focus restoration, scrolling and cancellation; nested Select portals stay in the active top layer. |
| F12 | All route pages are eagerly imported in `App.tsx`; some deeply nested features are already lazy. | Split appropriate route/features, retain auth/session/shell lifetimes and add local loading/error boundaries. | Login does not fetch unrelated workspace route chunks; route loading never removes the persistent shell or loses active work. |
| F13 | `UnderstandingTable` clears data on every fetch; Library retains a previous result through filter changes without an explicit query-bound loading presentation. | Separate first load, same-query refresh and new-query replacement; bind visible results to the active query. | Same-query refresh preserves content/scroll; old-filter results are not presented as current; failures retain only correctly labeled current data. |
| F14 | `usePageRefresh` and Library/detail focus/visibility listeners overlap; Progress and child agenda can independently refresh. | Consolidate refresh triggers per feature/query, coalesce focus/visibility bursts and prevent overlapping reads. | One request per relevant trigger/query; hidden/offline work pauses; mutations/recovery freshness is preserved. |
| F15 | New assistant responses receive a one-second clip-path reveal of the whole answer. | Replace it with a brief optional appearance treatment, preserving mounted content and scroll anchors. | Completed content is immediately readable/selectable; no long code/card reveal or replay on restored history. |
| F16 | Learning estimates use a semantic table with wide columns; list cards contain title/status/actions that may crowd with long content. | Improve responsive table containment and card wrapping after long-content screenshots. | Page never overflows horizontally; table can scroll locally; titles/actions remain legible and operable. |

F16 is a responsive verification target, not a claim that clipping was observed. Palette contrast, excess whitespace, apparent alignment and density require rendered evidence. Maintain this distinction in the implementation issue ledger.

## 4. Visual system specification

### Surfaces and color

Keep the centralized semantic palette and Mentra accent identity. Refine both palettes together: a calm page background, distinct but close panel surface, slightly raised overlay and subtle hover/selected surfaces. Use borders for grouping and elevation only when depth helps explain interaction.

Tune dark text/background pairs by measurement. Small muted/subtle text, disabled states, syntax colors, control boundaries and selected states need explicit checks; do not infer readability from a token name. Target at least 4.5:1 for normal text, 3:1 for large text and meaningful control/focus boundaries. Decorative separators can be quieter when another cue supplies the relationship. Do not use color alone for status or selection.

Use semantic status treatment for success/warning/error/information. Domain state labels are still feature-owned; a shared status badge only provides presentation. Keep entity identity restrained to icons/dots/badges where it already has a purpose.

No new gradients, glass panels, hero illustrations or decorative icon tiles everywhere. Existing page icon treatments can become smaller/quieter where screenshots show they compete with titles. Avoid globally rewriting the logo.

### Geometry and spacing

Proposed scale, finalized against baseline screenshots:

| Role | Target |
| --- | --- |
| Base spacing | 4px steps; 8/12/16px within controls and rows; 20/24/32px between groups |
| Page padding | 16px narrow, 24px medium, 32px wide; preserve shell-control clearance |
| Page width | Keep current 5xl workspace cap and approximately 52rem chat cap initially; narrower inner forms remain aligned to page content |
| Control radius | 10–12px |
| Cards/sections | 14–16px |
| Modal frame | 16–20px; no oversized default 32px rounding |
| Default field/button | 44px minimum height |
| Compact desktop control | 36px where context warrants it; enlarge touch interaction geometry |
| Touch icon target | Aim for 44px effective box without changing the compact glyph size |
| Icons | 16px inline, 18–20px controls/navigation, 20–24px section identity; consistent stroke weights |
| Elevation | None/low for content; one restrained overlay shadow; remove habitual blur |

Map these to CSS variables/Tailwind theme extensions or shared classes, with one source for each role. Do not introduce a complex token generator. Exceptions include source-reader/code geometry and the existing sidebar width, which must be tested before adjustment.

### Typography

Keep the current local/system font stack initially; inspect the actual rendered font since `Inter` is listed but should not be assumed installed. Avoid a font download unless there is a demonstrated visual need and a loading plan.

Define roles: page title 28–30px desktop/24–26px narrow, section title 18–20px, body/control 14px, supporting text 12–13px. Reserve 10–11px for low-priority decorative metadata; promote actionable/help/error text when it is too small. Keep chat prose readable at current or slightly larger size after comparison, with generous line height and a controlled reading width. Use tabular numerals for counts/timers. Preserve code legibility and Markdown heading hierarchy.

### Interaction hierarchy

Each local task region has one dominant action. Secondary actions remain near their content; rare or destructive maintenance actions become quieter and visually separated. Do not force a single primary button across an entire page containing independent forms.

Action rows wrap with deliberate gaps and consistent order. Long labels remain intact or wrap naturally. No fixed width that clips translated, long or user-generated text. A card should only have a whole-card click target when it has one primary destination; keep other actions outside that target.

## 5. Shared component renovation

Extend existing primitives first. Add a new component only where inspected duplicate behavior or presentation justifies it.

| Shared boundary | Work |
| --- | --- |
| `Button` + reusable style function + `IconButton` | Native semantics, typed variants/sizes, stable loading slot, consistent focus/disabled behavior, restrained destructive treatment; link actions consume styles without pretending to be buttons. |
| `Card` and workspace surfaces | Align default radius/border/elevation; separate card content padding from elevation. Preserve caller overrides intentionally. |
| `Input` / `Textarea` / `Select` / `FileInput` | Align heights/radii/type/help/validation; support error description IDs; preserve Select native adapter, multi-select and keyboard/typeahead contracts. |
| Small `FormField` pattern | Shared label/help/error association; required/optional labels and grouped fields. Support externally labeled controls rather than requiring one rigid form layout. |
| Controlled `Tabs` | Shared visuals, roving focus, Arrow/Home/End, disabled behavior, stable IDs, tab/panel association; caller owns URL and automatic/manual activation choice. |
| Native `Dialog` frame + confirmation composition | Title/description IDs, size limits, focus return, body/footer scroll behavior, safe cancellation, native top layer and consistent backdrop. No redundant custom focus trap over native modality. |
| `Popover` | Retain anchoring/visual viewport behavior; add bounded, positioned entrance motion and coalesced measurement only after profiling. Dropdowns remain dropdowns, not modals. |
| `StatusBadge` / inline notice | Presentation only; feature labels and safe error vocabulary remain local. Distinguish status, warning, conflict and actionable failure. |
| Workspace header/section/action-row patterns | Same title/description/action hierarchy and narrow wrapping; detail pages can use breadcrumb + header without inventing another header system. |
| Skeleton/empty/pagination patterns | Match eventual geometry; shared loading announcements; consistent query-empty versus first-use messages; preserve offset/cursor semantics. |

Avoid a universal resource framework, a second UI library, a second Markdown renderer or a new global state library. Shared presentation must not own domain mutations, route decisions, server revisions or assessment persistence.

## 6. Shell and layout map

Preserve the desktop sidebar on the left, New Chat near the top, navigation above history, account capsule at the bottom, and floating workspace controls. Keep chat filling the main viewport and other pages in their existing reading container.

Changes:

1. Remove duplicate non-chat visual route labels once every route has an accessible page heading. Standardize the floating toggle/bell hit areas and clearance using shell geometry, not page-specific guesses.
2. Align navigation glyphs, New Chat, history rows and account controls to a common inset. Keep current expanded/collapsed widths initially; preserve active conversation selection and Chat return behavior.
3. Preserve conversation titles using the existing contextual action overlay; ensure pointer, keyboard and touch behaviors agree. Enlarge row action hit areas without covering the title destination. Keep inline rename/delete contextual.
4. Mobile sidebar becomes a modal navigation region: labelled, background inert while open, appropriate initial focus, bounded tab order, Escape/dismiss and focus return. Closed sidebar content is inert/hidden from keyboard and assistive navigation. Resize to desktop cleans up mobile modality and scroll locks.
5. Decouple mobile history visibility from desktop collapse. Account popover closes/repositions correctly on route/collapse/viewport changes and retains its current expanded/collapsed sizing contracts.
6. Add a keyboard skip-to-main route target. Define route heading focus behavior for actual page navigation without stealing focus during query changes, chat updates or tab interactions.
7. Preserve `min-h-0`/`min-w-0` and one deliberate vertical scroll owner per page region. Use safe-area padding for controls/composer where needed; test on-screen keyboard and short viewports.

Only approved layout deviations: removing duplicate titles; local alignment/wrapping; grouping material maintenance actions; restoring mobile history; making content-dependent action rows consistent. Larger relocations require before/after evidence in the issue ledger.

## 7. Chat, rich content and inline workflows

Keep the centered message column, composer at the bottom, attachment action on the left, microphone next to Send, source search activated by `@` in the editable composer, and current activity near the active response.

- Reduce composer shadow/border weight and standardize inner padding; preserve multiline auto-sizing and max height. Compact controls use shared styles while attachment/copy hover remains the existing restrained text/icon treatment.
- Keep Enter/Shift+Enter/IME behavior, picker Arrow/Enter/Escape interaction and textarea focus. Never add a persistent source picker or separate voice page.
- Align attachment chips, selected material indicators, voice recording line, error/retry text and evaluation notice to the same inner grid. Allow long file names and mixed language text to wrap safely.
- Preserve transcribed text as an editable draft. Permission, recording, transcribing, cancel and retry states remain distinct; avoid layout-jumping status banners.
- Unify Copy controls, inline proposal/choice/assessment card geometry, citation chip spacing and action footers. No animation or hover affordance should make an immutable saved message look editable.
- Preserve `useChatScroll` restoration/prepend/anchor/manual-scroll contracts and bottom-only following of late content growth. Shell or motion work must not add a tail spacer or replay anchoring at completion.
- Replace the one-second reveal with immediate content visibility and at most a brief appearance accent for a newly delivered answer. Never animate saved history or reveal each token/card individually.
- Keep Markdown/code/source components shared. Preserve worker-based highlighting, language fallback, copy/download/wrap, local horizontal scrolling and safe link/source resolution.
- Standardize source-reader frame/header/tabs/toolbar; code, extracted text, image and original-source modes retain their distinct content requirements. Citation context and archived-source consent stay intact.
- Profile old messages during typing/activity updates. Memoize stable message rows and adapters only if profiling shows avoidable parsing/renders; verify source/citation/attempt changes still update. Preserve stable IDs and bounded message windows.
- Do not virtualize chat by default. Its current anchoring, browser find, variable-height media, citations and interactive cards make virtualization a separate evidence-driven decision.

## 8. Library and materials

### Library listing

Keep title/Add material at the top, filters above the grid, materials before learning contexts. Standardize filter labels/widths/baselines and reset paging when a filter changes. Use explicit current-query loading state.

Cards get a predictable title/metadata/status/action structure. Long filenames/context lists cannot squeeze the title to zero width; status may wrap into its own line on narrow screens. Align footer links across card rows without empty padded blocks. Ready, preparing, failed and archived remain separate labels.

Distinguish an empty Library from no matches and no archived material. Reuse pagination appearance without converting an offset API into cursor pagination. Counts describe actual data, not invented totals.

### Add material

Keep the dedicated route and back link. Align upload/context fields to the same form width and field rhythm as assessment creation. Reduce unnecessary nested panel borders. Preserve duplicate-upload notices, context creation, unsupported-file states and real capability constraints.

### Material detail

Keep back navigation, title/state, details form, actions, tags, versions and replacement upload in the current sequence initially. Upgrade the header and section pattern. Keep Study in chat near the title/task; visually separate Archive/Reindex/Delete maintenance from ordinary Save. On narrow screens use an orderly wrapping action group; add a maintenance menu only if screenshots establish a real crowding problem and keyboard behavior is covered.

Use operation-specific feedback for save/archive/reindex/retry/delete/tag/version loading. Preserve revision conflicts and unknown-outcome recovery. Periodic refresh must not silently overwrite unsaved title/context/tag edits: track dirty values and offer deliberate reload/reconciliation if a new server revision arrives.

Version history stays visibly immutable. Label current versus earlier uploads accurately; source consent remains explicit. Processing status uses safe user-facing labels rather than raw job stage names. Destructive confirmation explains the actual deletion behavior and uses shared dialog/destructive styling.

## 9. Assessments and calibration

Keep Assessments/Create tabs, creation form, selected assessment/attempt, question flow and saved feedback positions. Standardize tab behavior, cards, fields, choice rows, question headings, result badges and wrapping footer actions.

- Keep navigation/back/review near question content; primary submission remains distinct from creating a new attempt.
- Use shared `Textarea` for written answers, preserving maximum length and draft/operation semantics.
- Maintain choice hit areas, keyboard operation and selected/correct/incorrect states with textual cues. Do not use distracting answer-selection animations.
- OCR/extracted answers still require review/confirmation; new concepts still require the existing explicit decision. No styling shortcut may imply consent.
- Submission/evaluation state preserves the visible question/review geometry. Only the current operation loads; errors preserve answers and the same recovery identifier where required.
- Drafts survive supported tab changes; splitting/lazy-loading must not reset the owner session or pinned attempt. Latest meaningful saved attempt selection and explicit retry behavior remain intact.
- Keep calibration answers local until the final atomic Finish request. Back/Next must not add network writes.
- Onboarding/login receive the same field, button, surface and typography rules, keeping their centered layout and existing return paths. Theme choice and logout remain reachable on short screens.

Saved assessments, attempts, grading history and evidence are data-integrity boundaries. Renovation cannot mutate originals, duplicate result persistence or change the meaning of practice/verification/calibration.

## 10. Progress, Events, Notifications and Settings

### Learning Progress

Keep Learning/Events tabs, overview/context selector, metrics, understanding table, reviews and suggestions. Improve metric-label wrapping and reduce redundant icon/panel decoration. Unknown values remain unknown; understanding, estimate reliability and recall confidence remain separate.

The understanding table keeps semantic headers and distinct measures. Provide a labelled local horizontal scroll region with keyboard access and a clear overflow cue if needed. At narrow widths, prefer this initially over a second card implementation that duplicates all data. Same-query refresh preserves rows and paging; search replacement has query-bound feedback. Search debounce is already implemented and should be tuned only with evidence.

### Events

Keep agenda, New event, inline editor/detail, filters, cards and proposal review in the Events tab. Align Search/status/date-range controls and make New event/detail actions wrap cleanly. Unify editor fields, detail labels, confirmation and operation feedback.

Preserve civil dates, IANA zones, temporal preview/gap/fold decisions, expected revisions, operation recovery, query-bound cursors and one reminder per event lifetime. Completion remains an event action rather than learner evidence. Date formatting can share a small helper where repeated, with separate civil-date and instant entry points; never convert date-only data through `new Date`.

### Notifications

Keep bell position, inbox route, unread filter and preferences link. Use a restrained unread marker with stable row geometry; status and action alignment remain consistent for long text. Keep cursor pagination and shared unread coordination.

Improve per-item feedback while retaining mutation/reload safety. Avoid multiple spinners across unrelated rows. Updates remain quiet: no new per-notification toast, sound or popup. Show meaningful actionable changes with existing inbox/badge behavior.

### Settings and Memories

Keep Profile/Memories/Notifications tabs and current section order. Align form widths and section/action spacing. Migrate repeated section chrome; preserve visited-memory draft retention and active-view behavior.

Memories keep list/detail/editor/confirmation workflow and provenance visibility. Standardize review, save, cancel and deletion presentation without making saved/proposed/deleted states ambiguous. Background refresh cannot reset an active editor. Theme remains in the existing account controls; avoid duplicating its state or adding independent theme selectors without a current requirement.

## 11. Motion specification

Motion should explain a state change and finish before it attracts attention. Implement primarily in CSS. No animation dependency is required for this plan.

| Interaction | Allowed motion | Duration |
| --- | --- | --- |
| Hover/focus/selected surface | Color/border/opacity; no layout change | 100–140ms |
| Button press | Optional tiny icon/control response; avoid scaling text-heavy buttons | 80–100ms |
| Chevron/disclosure | Rotation; content appears without broad height animation | 120–160ms |
| Anchored popover | Opacity + at most 2–4px translation after placement | 120–160ms |
| Modal open | Opacity + at most 4–6px translation on dialog content | 150–180ms |
| Mobile sidebar | Small bounded slide with scrim fade | 180–200ms |
| Desktop collapse | Existing width motion retained only if profiling passes; use instantaneous layout if it causes excessive reflow | Up to 180ms |
| New completed response | Immediate content visibility; optional small opacity treatment without moving/obscuring the answer | 100–140ms |
| Loading | Existing spinner/working logo; quiet skeleton pulse where helpful | Existing restrained loops |
| Voice level bars | Prefer scale transform from a fixed-size container over changing layout height | 80–120ms |

No staggered lists, bouncing, parallax, whole-page slide transitions, animated counters, animated table reordering, animated composer height, blur transitions or one-second content reveals. Do not keep `will-change` on every control. Never animate an operation into appearing successful before the server confirms it.

Positioned overlays animate an inner surface so transforms cannot distort anchor measurement. Fast close/reopen, Escape and click dismissal must work without waiting for motion. Prefer entrance-only motion initially; delayed unmount must not leave focusable hidden controls. Modals cannot lose native top-layer semantics for exit animation.

Reduced motion receives immediate state changes and static nonessential indicators. Do not remove useful status text. Theme switching does not animate dimensions. Loading motion pauses when a component is hidden/inactive; the working logo remains instance-scoped and only active during current work.

## 12. Performance and state optimization

### Measure first

Use a fresh production build and representative seeded accounts. Record initial route chunks/compressed transfer, request graph, time to usable content, main-thread long tasks, React commits, layout shifts, interaction latency and memory after repeated navigation. Separate browser rendering time from API/provider latency. Do not attribute model/search wait to frontend inefficiency.

Profiles: login cold load, restored chat with 50/200 loaded messages, typing in rich chat, response delivery with code/images/cards, sidebar collapse/open, Library filters, Settings revisits, assessment answer navigation and Progress search/pagination. Use fixed fixtures, viewport, throttling and hardware conditions for comparisons.

### Planned changes

1. Route splitting in `App.tsx` for appropriate feature pages, keeping auth/profile providers, ChatSession and persistent shell mounted. Add route-local fallbacks and recovery for failed chunks; no automatic reload loop or unbounded retries.
2. Load expensive source readers and optional feature cards when opened/needed. Preserve current Prism worker/grammar loading rather than eagerly bundling language support. Measure actual chunk duplication before changing Vite splitting.
3. Profile message/sidebar/card renders; stabilize props/callbacks and memoize proven expensive boundaries. Snapshot/store changes must still publish citations, attachments, interactions, revisions and assessment feedback correctly.
4. Coalesce refresh/focus/visibility triggers and use a single in-flight query owner per feature. Do not replace the existing page cache with another data layer. Preserve cancellation, owner transitions, bounded cache, invalidation and live-job/attempt exclusions.
5. Keep current-query data during quiet refresh, use first-load skeletons and scoped busy indicators. A different filter/query must not inherit an old empty state or show old data as current. Dirty drafts survive refresh; conflicts become deliberate user decisions.
6. Profile `Popover` geometry updates before optimizing. If needed, schedule one read/write per animation frame and avoid unchanged style commits/observer feedback loops; cancel frames/listeners on close.
7. Reduce blur/large shadow and broad transition use. Prefer transform/opacity for motion. Voice bars can use transforms without changing the row's height; compositor benefit still needs tracing.
8. Reserve image/preview geometry when dimensions are known, lazy-load authorized offscreen media, cancel stale loads and revoke object URLs. Do not preload private files or every route's media.
9. Preserve bounded pagination. Consider sidebar/list virtualization only if measured large accounts still fail budgets after simpler fixes, with browser-find/focus/scroll constraints recorded.

### Initial budgets and completion rules

These are proposed lab gates, not achieved measurements:

- No increase in required initial JavaScript/CSS transfer for any audited entry route without a documented reason. Aim for at least 20% lower initial transferred JavaScript on auth/secondary routes where splitting removes unrelated code; verify cold and warm navigation separately.
- Already-loaded UI changes acknowledge input within approximately 100ms on the reference device. Profile slow-device behavior; use a 200ms p95 local-interaction ceiling as an initial investigation gate, excluding network/provider work.
- No layout shift caused by spinner insertion or refresh replacement in the fixed fixtures. Use a 0.1 overall layout-shift ceiling as a broad lab guard, with traces attributing individual shifts.
- No avoidable new main-thread tasks over 50ms from simple menu/tab/control motion in the reference traces. Trace data, not a claimed frame rate, determines success.
- No duplicate concurrent read for an identical active feature query from a single focus/visibility burst. A server-required recovery/reconciliation request is a separate operation and must remain.
- Repeated route/dialog open-close cycles leave no accumulating listeners, observers, animation frames, object URLs or requests. Memory should stabilize after warmup; inspect retained objects rather than imposing an arbitrary megabyte cap.

Finalize absolute time/size budgets after Phase 0. A faster warm route cannot conceal a worse cold load or broken freshness behavior.

## 13. Accessibility and responsive acceptance

Baseline widths: 320, 375/390, 768, 1024 and 1440px; add 1920px for reading width. Cover a short 568px viewport, landscape, 200% zoom, large text, on-screen keyboard, coarse pointer, keyboard-only and reduced motion. Test Light/Dark plus System switching and first paint.

Required behaviors:

- One main landmark, clear heading hierarchy, accessible controls, visible focus and a useful skip target.
- All menus/tabs/dialogs/navigation usable without hover. Modal close returns focus to a meaningful connected target; removed triggers fall back deliberately.
- Hidden tab/sidebar content is not accidentally tabbable. Lazy boundaries never strand focus or erase drafts. Disabled/loading controls are truthful and status is announced once at the appropriate region.
- No page-level horizontal overflow except intentionally contained code/table regions. Long titles, filenames, URLs, source excerpts and mixed RTL/LTR text fit safely. Test `dir="auto"` in composer/appropriate user text without forcing application navigation RTL.
- All primary actions and modal footers remain reachable on short screens. Scroll locks are scoped, restored and do not prevent Select/source-reader scrolling.
- Touch targets and adjacent spacing stay usable; visible hit area or padding enlargement never covers a neighboring control.
- Skeletons/refreshes do not flood screen readers. Error text connects to fields and uses the safe vocabulary; focus moves to a failed field when appropriate, preserving entered data.
- Theme persistence, OS changes, blocked storage and cross-tab switching keep the bootstrap/provider contract. Visual contrast review supplements existing theme logic tests.

## 14. Implementation sequence and review units

The user authorized implementation after this plan was written. Each phase produces focused changes, before/after evidence and relevant regression checks; the report records the delivered work and validation limits.

| Phase | Work | Depends on | Exit evidence |
| --- | --- | --- | --- |
| 0 — Baseline | Capture route/state screenshots and traces; fresh build/chunk/request inventory; classify issues and establish budgets. | Current checkout | Baseline artifact set, measured bottlenecks, layout-change ledger, agreed reference device/fixtures. |
| 1 — Foundations | Tokens/type/geometry/elevation; explicit transitions; Button/IconButton/link styles; Card/fields/status patterns. | 0 | Shared component matrix in both themes; existing consumers migrated enough to demonstrate real usage. |
| 2 — Navigation and interaction | Shell title/clearance, mobile modality/history, Tabs, native dialog frame and Popover consistency. | 1 | Keyboard/mobile/short-screen checks; route/query and overlay regression evidence. |
| 3 — Chat and content | Composer, message/card/action hierarchy, voice/attachments/citations/source reader, brief response treatment. | 1–2 | Chat scroll/recovery/voice/RAG/code/interaction/assessment regressions; rich-content screenshots. |
| 4 — Workspace pages | Library/detail/upload, assessment/create/attempt, Progress/Events, Notifications, Settings/Memories, auth/onboarding. | 1–2; shared content from 3 | Complete route/state matrix; draft/query/history invariants pass. Can be delivered as smaller feature diffs. |
| 5 — Measured optimization | Route/chunk loading, expensive renders, refresh coalescing, overlay measurement, media lifecycle. | 0 baseline; repeat after relevant phases | Production before/after measurements; cold/warm and freshness behavior verified. High-value splitting can occur earlier after baseline. |
| 6 — Consolidation | Remove obsolete duplicate styles/unused helpers, enforce standards, full regression and production verification. | 1–5 | Final evidence matrix, clean production build, theme/browser checks, documented residual limitations. |

Suggested first coherent implementation slice: foundation tokens and controls, remove broad transitions, align default cards, repair shell/mobile focus and duplicate title. This supplies a visible consistent base before page-by-page restyling. Avoid changing every page in one unreviewable patch.

Maintain a layout-change ledger: component/route, current location, proposed location, concrete reason, screenshot, narrow behavior and preserved shortcut/deep link. Most changes should record “position preserved; alignment/spacing refined.”

## 15. Verification, standards and definition of done

### State matrix

For every feature, cover first load, populated, empty, filtered empty, quiet refresh, recoverable error, mutation pending, conflict/unavailable and long content where applicable. Use genuine fixture data; no fabricated progress or analytics.

Cross-cutting cases: account change during request, filter change during response, route unmount during dialog/media work, back/forward, slow/offline recovery, blocked storage, modal nested Select, rapid open/close, double activation, dirty form + refresh and server revision change. A mutation with an unknown outcome follows its existing recovery contract and is never blindly replayed.

### Existing checks to reuse

- `npm run build` and `npm run check:theme` in `frontend`.
- `ui-system.spec.ts`, `workspace-polish.spec.ts`, `loading.spec.ts`, `auth.spec.ts`, `student-profile.spec.ts` for foundations/shell/loading/onboarding.
- Chat/history/cache/images/interactions/assessments, `voice.spec.ts`, `rag.spec.ts`, `code-display.spec.ts`, `tool-recovery.spec.ts`, `web-search.spec.ts`, `response-latency.spec.ts` where affected.
- `assessment-proposals.spec.ts`, `quiz-local.spec.ts`, `progress.spec.ts`, `events-notifications.spec.ts`, `memories.spec.ts`, `user-errors.spec.ts` for feature migration and preserved state/error contracts.
- Extend only meaningful behavior gaps: mobile focus/inertness/resize, shared Tabs keyboard/query lifecycle, dialog focus/nested portals, loading geometry, query-bound refresh, reduced-motion handling and deterministic visual comparisons.

Run focused tests per diff; run the applicable full frontend suite at consolidation. Use the existing isolated migrated test database setup. Fresh production Docker frontend build is required before claiming production readiness; changes to environment/images require recreation if deployment is separately authorized. No deployment or database migration is part of this planning task.

Capture representative screenshots at mobile/tablet/desktop in both palettes, with long content and short viewports. Disable motion for deterministic comparison; separately verify enabled and reduced motion. Fix baseline diffs by inspecting geometry and interaction, not by mass-accepting screenshots. Expand browser-engine coverage where available and record physical mobile/Safari limitations honestly.

Update `frontend/standards.md` and `src/styles/README.md` to describe implemented conventions. Add a small UI/motion/performance checklist and, where useful, narrow static checks for new raw theme colors, universal transitions and duplicate shared patterns. Prefer an exception list to a scanner that forbids valid native controls or feature-specific styling. No new Storybook/build stack is required; use a development/test component matrix if needed.

### Done means

1. Every existing route and significant state has been renovated; the scope inventory has no forgotten secondary screen or dialog.
2. Shared controls/surfaces/fields/tabs/modals/status/loading patterns look and behave consistently in both palettes.
3. Familiar placement remains; every move has a recorded reason and responsive evidence.
4. Motion is subtle, bounded, cancellable and reduced-motion safe; useful content/actions are immediate.
5. Performance improvements have production measurements and no freshness, ownership, draft or recovery regressions.
6. Critical persistence, assessment history, atomic calibration, temporal semantics and API boundaries remain intact.
7. Relevant tests, production build, visual/accessibility checks and document diff hygiene pass; any untested environment is explicitly listed.

### Final handoff artifacts

Provide the implementation summary, route coverage checklist, layout-change ledger, before/after screenshots, production performance comparison, commands/results and remaining limitations. Keep this document updated against the implemented source; proposed work must never be marked complete merely because a token or primitive was added.
