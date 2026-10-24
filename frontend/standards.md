# Frontend Engineering Standards

> **Build for the requirements we have, while leaving clean boundaries for the requirements we expect. Do not implement future features before they exist.**

These standards describe the current React, TypeScript, Vite, and Tailwind CSS codebase. Update them when an important frontend convention changes.

## Compact visual system

- Default buttons and fields are 36px; small buttons are 32px and large buttons 40px. Coarse-pointer controls grow to 40px and icon controls to 44px. Keep glyphs compact while preserving usable hit areas.
- `rounded-control` (9px), `rounded-panel` (14px), semantic surfaces and restrained `shadow-panel`/`shadow-overlay` define shared geometry. `Card` is quiet by default; elevation is explicit. Workspace panels use 16px padding and pages use 16–32px horizontal padding.
- Use `buttonStyles` for real navigation links, `IconButton` for standalone icon controls, `FormField` for shared label/help/error association, controlled `Tabs` for workspace tabs, and native `Dialog` for modal frames. Features own URLs, drafts, mutations, revision checks and panel mounting.
- Numbered collection pages reuse `Pagination`: 28px desktop controls with chevrons only, accessible Previous/Next labels, equally sized page numbers, a visible current page and disabled boundaries. Coarse-pointer targets retain the shared 40px minimum. Keep page and filter state together and reset to page one when filters change.
- Loading overlays a spinner without changing button width or accessible labels. Track the active operation separately from disabling dependent controls; unrelated actions do not all spin.
- Motion is explicit and short: controls 100–150ms, overlays 130–160ms, navigation up to 200ms. New completed chat answers reveal as one formatted surface with a soft downward mask over 900ms, independent of length; history and reduced-motion answers appear immediately. Markdown renders synchronously before the reveal, with no raw-text fallback. Never apply transitions to every element, animate form dimensions, or delay dismissal for exit motion. Reduced motion and forced colors retain useful state/focus indicators.
- Workspace headers have one H1; actions wrap beneath the full-width description on narrow screens. The shell does not repeat route titles. Preserve sidebar/composer/account placement and record substantive changes in the renovation report.
- Mobile navigation is modal with inert background/closed content, bounded focus, nested-overlay Escape handling and focus return. Desktop collapse never removes history from an open mobile drawer.
- Route chunks load inside local boundaries, preserving the shell and session providers. Failed chunks offer explicit reload. Keep the chat boundary stable across draft-to-saved route changes.
- Quiet same-query refresh retains content and scroll. Different queries cannot display old results as current. Coalesce focus/visibility triggers, avoid overlapping automatic reads, and preserve mutation-triggered invalidation. Dirty material edits retain their original revision until explicit reconciliation.
- Completed message rows use shallow React memoization. Keep immutable message updates so revisions, citations, attachments and interactive cards still publish. Avoid equality functions that ignore metadata.
- Publish optimistic messages and busy state together. Keep the activity row and working logo mounted across acknowledgement; do not key them by server turn/attempt. Coalesce label bursts with a 650ms minimum display interval, retain meaningful feedback through routine reads, and use only the closed presentation vocabulary. Token deltas advance recovery cursors without entering rendered state. Stop feedback is immediate; final answers never wait for activity timers.
- Production static serving compresses JS/CSS and caches content-hashed assets immutably. HTML and theme bootstrap revalidate; missing assets return 404 rather than the SPA document.

Run `npm run check:ui` for palette text/control contrast and broad-transition safeguards alongside theme/build checks. `playwright.visual.config.ts` runs fixture-based production UI/typing checks independently of real domain suites; `FRONTEND_VISUAL_DEV=1` enables development lifecycle checks. See [the renovation report](../docs/Frontend_Renovation_Report.md) for evidence and limits.

- Workspace pages share `WorkspaceHeader`/`WorkspaceEmpty` and semantic `workspace-*` surfaces for responsive panels, filter bars, tabs and cards. Counts must come from loaded data. Select listboxes fit their option content while remaining viewport-bounded. Chat actions overlay a full-width title, reserve title space only on hover/focus (always on touch/mobile), and remain keyboard accessible.
- Chat Stop calls the attempt-fenced server action, retains the saved stopped notice and reconciles server status; never treat aborting an HTTP request as cancellation. Attachment cards restore from message metadata, lazily load authorized raster previews, revoke object URLs and provide original downloads. Restored chats open at the latest message and follow late content resizing only while at the bottom.
- User and assistant messages reuse the shared plain-text Copy control. Keep it close to the message, brighten text/icon on hover or keyboard focus, and use no hover background. The disclaimer is the final item inside the conversation scroll content, bottom-aligned for short chats and hidden in empty chats; it scrolls out of view with messages. Reserve its height when anchoring a newly sent exchange.

## Project structure

- `components/`: shared application components grouped by responsibility. Keep feature-specific components in a named feature folder such as `components/chat/`.
- `components/ui/`: small, composable primitives such as buttons, fields, cards, and loading indicators. Do not put feature or domain components here.
- `components/navigation/`: application navigation and shell controls.
- `pages/`: route-level screens. Route screens should compose feature components instead of owning the entire application.
- `layouts/`: shared page structure and outlet boundaries used by multiple routes.
- `hooks/`: reusable React hooks, named with the `use` prefix.
- `services/`: communication with external systems, including the centralized backend API client.
- `stores/`: existing owner-scoped external stores such as persistent chat. Add a feature store only when multiple consumers need shared server state; keep caches bounded.
- `types/`: shared frontend types that have more than one meaningful consumer.
- `utils/`: small, domain-independent helpers used by unrelated areas.
- `styles/`: global CSS and Tailwind base directives; component styling otherwise uses Tailwind classes.

Create folders to meet a real architectural need, not to imitate a large project. An empty folder is preferable to speculative abstractions.

## Routing and application layout

- Use React Router routes in `App.tsx`; `AppLayout` owns the persistent application shell and renders active pages through an outlet.
- Route paths are lowercase and resource-oriented: `/` for Chat, `/library`, `/progress`, `/assessments`, and `/settings`.
- Navigation belongs in the application shell, not repeated inside individual pages. Keep desktop collapse and mobile drawer behavior accessible and operable.
- The desktop collapsed sidebar is 56px wide with a 48px brand row. The workspace has no top header bar: navigation and notification controls float in a pointer-transparent overlay, and chat fills the full main viewport without repeating its title. Other page titles remain visible without a bar; reserve clearance for their floating controls. The account popover retains full labels at 240px outside a collapsed desktop sidebar. Expanded desktop and mobile sidebars match the account capsule width; the shared Popover bounds the surface to the viewport.
- On an existing chat route, highlight the conversation row, while the Chat navigation item stays unselected and returns to the last viewed chat from other workspace pages. New Chat resets that return target to the empty chat.
- The account capsule displays the login username. The optional preferred name (“What should Mentra call you?”) belongs to the shared onboarding/Settings ProfileForm and may be cleared independently of the username.
- Keep page-specific behavior and UI with the relevant page/feature. Do not add routes, guards, onboarding, or account flows without a product requirement.
- `/login` and `/register` use `AuthLayout` and a shared username/password form. `RequireGuest` redirects signed-in users; `RequireAuth` guards the workspace and preserves the requested destination.
- The authenticated `StudentProfileProvider` owns profile restoration. `ProfileReady` handles loading/retry; `RequireOnboardingComplete` gates the workspace. `/onboarding` collects required information and optional calibration; `/calibration` resumes later from Settings.

## Components

- Chat assessment cards read canonical attempt history without page caching. Restore the latest meaningful attempt rather than allowing an unused empty retry to hide saved feedback; respect explicitly pinned attempts and deliberate retries held in the current owner session. Results remain owned by assessment persistence, never duplicated into chat metadata. Keep result actions, including View in assessments, as compact buttons in one wrapping footer row.
- `useChatScroll` owns restored-history positioning, prepend preservation and new-message anchoring. Stable exchange groups let the latest sent user message sit at the top while the answer fills a viewport-sized minimum; never append a separate tail spacer or re-anchor on answer completion. Respect manual scrolling and clear the temporary minimum on restored history. The disclaimer stays at the bottom of the conversation region above the composer.

- Keep components focused and composable; avoid large components that combine unrelated presentation and behavior.
- Use semantic HTML and preserve keyboard access, visible focus, and disabled behavior.
- Do not spread backend calls throughout presentation components; use `services/`.
- Shared primitives accept `className` and extend native HTML attributes when appropriate.
- Prefer composition over a broad prop surface. Do not generalize a one-off component until a second real use case exists.
- Keep feature UI such as chat messages and composers outside `components/ui/`; reserve that directory for primitives.
- Use the established icon library (`lucide-react`) consistently. Give icon-only controls accessible names and titles where useful; do not use emoji as application icons.
- Use `components/brand/MentraLogo` for the decorative brand mark. Pass `working` only to the current response indicator; sidebar, empty-state and saved-message logos remain static. Instance-scoped CSS owns seamless rotation, a subtle 3.5% zoom cycle and an alpha-masked accent sweep that fades at loop boundaries. Reduced-motion users receive a static mark, and surrounding UI owns accessible status text.
- Chat activity replaces one current step instead of retaining a visible execution log. The frontend `activityLabels` mapper owns a closed user-facing vocabulary; never render raw backend tool identifiers, arbitrary activity messages or execution statuses. Current web-search websites keep their favicon identity until the next step; final citations retain consulted sources.
- Announce meaningful actions (web searches, documents, events, practice, learning progress and requested personal information). Routine profile loading, capability setup, unknown internal work and completed housekeeping remain under “Thinking”. Important failures/partial results, review requests and retries receive safe plain-language labels; optional tool failures go to the agent for judgment rather than a deterministic Response limitations box.
- Empty states should explain the current state honestly and offer only actions that work. Do not present mock data as saved learner activity or invent analytics.
- Reuse existing UI primitives, including Spinner/loading states and the accessible `Toggle` for binary preferences. Keep theme selection in the existing account drawer and use semantic Light/Dark/System tokens.
- Render Markdown with the existing `components/content/MarkdownContent` and shared Prism `CodeBlock`, used by chat and Library. Keep feature reference resolution in its feature adapter; never enable arbitrary HTML or duplicate the formatting stack.
- Web citations resolve only message-local validated W references. Reuse `WebCitation`, `WebCitations` and `WebsiteIcon` for external links and origin identity. Favicons use anonymous HTTPS origin requests without referrers; blocked/unavailable icons render a stable fallback. Never send search terms to a favicon service. Website activity badges use the existing attempt-fenced stream, not a new polling store.

- User-facing failures use the closed vocabulary in `services/userError.ts`, including persisted turn errors inside successful responses. Never render arbitrary server error/reason/warning strings. Keep optional tool/RAG failures in agent context; do not add deterministic source-warning or Response limitations banners. Explicit failed-turn/file-action errors remain actionable; preserve uncertain-action notices and retry/review guidance. Saved history stays unchanged.

## TypeScript

- Keep strict type checking enabled and avoid `any`.
- Give public component props and shared service contracts explicit types.
- Extend native React HTML attribute types rather than re-declaring standard element properties.
- Define frontend API types for the data the UI actually consumes; do not blindly duplicate every backend model.

## State

- Keep state local by default and lift it only when multiple components need to share it.
- Do not add a global state library until there is a demonstrated need.
- Treat server state (backend data and request lifecycle) separately from local UI state.
- `AuthProvider` owns authenticated identity and session restoration. Tokens live only in backend-issued HTTP-only cookies, never local/session storage or JavaScript state. Tab messages signal a session change; each tab verifies identity with `/auth/me`.
- Scope requests and caches to the authenticated owner and active query. Abort stale requests, fence late responses after account/filter changes, and clear personal drafts/caches on account transitions. BroadcastChannel is optional; blocked storage or missing tab messaging must degrade safely.
- Open tab channels through `utils/broadcastChannel.ts`: browsers may expose BroadcastChannel while rejecting its constructor. Upload receipt keys and completed receipts are memory-only, owner-scoped and filename-specific; account transitions must fence late upload responses.
- Original file downloads use the shared Files client's memory-only session cache. A SharedWorker shares immutable blobs across open tabs; unsupported browsers fall back to tab memory. Keep bytes out of IndexedDB, local/session storage and persistent HTTP caches. Logout/account changes clear the owner cache and abort pending reads; closing every tab ends the shared worker session. Evict revoked sources and changed calendar exports after their domain mutations. Components own and revoke their display object URLs, while the session cache owns the reusable bytes.
- Preserve drafts across related tab changes, with query-driven navigation and back/forward behavior where supported. Load personal collections on demand, merge affected rows and use server revisions/tombstones to prevent stale responses from restoring deleted data.

## API access

- Route backend HTTP communication through `services/api.ts`; do not scatter `fetch(...)` through components.
- Use the environment-configured `VITE_API_URL`. A browser must be able to resolve this URL; do not use a Docker-only service name in the browser bundle.
- The shared client owns JSON headers/parsing and converts standard backend errors into useful typed errors. Keep it small; add retries, caching, auth, or streaming only when required by a real feature.
- Requests include cookie credentials. `services/auth.ts` requests cookie transport, enforces a request timeout, and uses actual backend contracts. Clear client identity only after successful logout; keep retryable network errors distinct from an unauthenticated response.
- Pass AbortSignals through the shared client, which owns credentialed requests, timeout cleanup and typed `ApiError` details. Do not automatically retry a mutation with a new operation UUID after an unknown outcome; use the feature's recovery contract and retain the UUID only for the same payload.

## Events and Progress integration requirements

Events lives inside the Events tab of Progress, alongside the Learning view. Existing `/events?event=...` links redirect to `/progress?tab=events&event=...`; new links use the latter. The agenda/editor, pending proposals and generic Notifications inbox are implemented. Follow the [Events delivery plan](../Mentra_Events_Implementation_Plan.md) and [current backend contracts](../docs/events.md).

- Keep event DTOs/client calls in feature types/services. Send no owner field; respect expected revisions, operation recovery, bounded pages, query-bound cursors and `PAGE_CHANGED` reloads. Present conflict, unavailable context and retryable `EVENTS_UNAVAILABLE` states distinctly.
- Preserve date-only values as civil dates with their event IANA zone. Render aware timestamps deliberately in the selected zone; never parse a date-only string as an instant and shift its calendar day. Use server temporal preview for gap/fold choices and single-reminder validation.
- Completing an event is a lifecycle action, not learner evidence. Learning views need genuine bounded public learner reads; unknown estimates remain unknown and empty views must not fabricate progress charts or percentages.
- “Your understanding” searches and pages the complete owned collection through the Progress API, using shared Input/Pagination controls with stale-request fencing. Topic confirmation explains its effect, scopes loading to the chosen decision, and bulk review preserves partial successes. Render status/reason codes through learner-facing labels; show follow-up reviews only when supported, explain each section, and never imply confirming a topic means mastering it.
- Capture, event reminders and memory preferences are independent. A pending/skipped/cancelled/delivered ledger describes scheduling history; never present a pending ledger as a delivered inbox notification. Generic Notifications and its shared polling coordinator own inbox delivery and unread state.
- Reuse shared editor/detail forms and primitives when the feature ships. Keep loaded pages/detail projections bounded, reconcile by server revision, and pause hidden/offline polling. Browser acceptance must cover account changes, lost responses, timezone/date boundaries, accessibility, narrow screens and Light/Dark/System.

## Utilities

> A function belongs in global utilities only when it is domain-independent and useful from multiple unrelated areas. Otherwise keep it close to the feature using it.

`cn(...)` is the current shared Tailwind class composer: it combines conditional classes and resolves conflicting Tailwind utilities for consistent primitive overrides.
It uses `clsx` for conditional class inputs and `tailwind-merge` so caller overrides replace conflicting utility classes.

## Styling

- Use Tailwind CSS utilities and the global base rules in `src/styles/global.css`.
- Use the shared `Select` for all single/multiple choice dropdowns. Its listbox renders through `Popover`, remains anchored to the trigger and supports keyboard/typeahead interaction. Native select elements are hidden form adapters only.
- Use `FileInput` for full file-picker fields and the existing icon picker for chat. Never expose the native file chooser chrome. Use `Toggle` for every interactive binary setting or confirmation; theme radios remain a mutually exclusive choice.
- Nested dropdowns consume Escape only while open; a closed field lets Escape dismiss its parent dialog.
- Menus and dialogs use the central `popover` surface and overlay scrim tokens. `Popover` handles portal placement, viewport margins, resize/scroll, outside dismissal and Escape; modal dropdowns portal inside the active dialog top layer.
- Feature pages share `page-container`, `page-title`, `page-description` and `field-control` for layout, typography and fields.
- Reuse semantic theme tokens and common spacing, radius, focus, and responsive patterns. Both palettes live centrally in `styles/global.css`; avoid raw palette colors or component-specific theme branches.
- Avoid arbitrary one-off values when an existing utility or established pattern fits.
- Preserve visible keyboard focus and responsive behavior. Shared UI primitives should have consistent defaults while allowing appropriate `className` overrides.
- Respect reduced-motion preferences for non-essential motion.

## Mock data

Keep temporary sample content isolated from page components and label prototype interactions clearly. Do not treat frontend mock data as persistence, a backend contract, or a permanent product convention.

## Naming

- React components and component files use `PascalCase`.
- Hooks use `useCamelCase`; utility functions use `camelCase`.
- Shared types and interfaces use `PascalCase`; prefer descriptive names such as `ButtonProps`.
- Follow existing file and export conventions; avoid adding barrel files outside a useful shared boundary.

## Testing

Test behavior and boundaries that matter. Do not write tests merely to inflate coverage.

Prioritize meaningful primitive behavior, user interactions, and important rendering or state behavior. Run `npm run build` for strict TypeScript checks and a production build, and `npm run check:theme` for theme behavior. `npm run test:e2e` uses Playwright with real auth/profile APIs and an isolated migrated PostgreSQL schema; `test:auth` / `test:profile` select subsets. Only the AI evaluator is a test double, not authentication or persistence. See [auth test setup](../docs/frontend-auth.md) and [profile tests](../docs/student-profile.md).

## Dependencies

> Do not add a dependency for something that can be implemented clearly and safely in a few lines, but also do not reimplement complex, security-sensitive, or well-solved infrastructure merely to avoid a dependency. Every dependency should have a reason to exist.

- Assessment types share the compact runner and paper primitives. Keep immutable IDs separate from printed nested references; never expose grading keys in generation progress or printed papers. See [Assessment engine](../docs/Assessment_Engine.md).

- Standalone card/footer navigation and recovery actions use compact shared button styling. Keep inline prose citations as links. Application disclosures use `ui-disclosure` for a consistent padded focus target while retaining native disclosure markers and keyboard behavior.

- Conversations use a 60rem maximum reading width on wide screens; the composer retains its 52rem maximum. On narrow screens both keep the same side margins.
- On phones, assistant avatars sit above the response instead of reserving a left column. Chat text and composer share equal side margins. Floating menu and notification glyphs stay quiet while their hit areas remain 44px. Mobile composer text is at least 16px, and long drafts are height-bounded by the viewport.

- The mobile composer starts in one row with attachment and send controls at opposite ends; text grows vertically as needed. Hide the microphone only while the textarea is focused, retain its recording controls, and keep the send button position stable.

- Mistake history requests ten recent records per page, with learning-context/assessment/topic filters and URL-backed card/list views. Reuse the owner-scoped page cache (five-minute reuse for visited mistake pages, bounded by shared capacity); relevant writes, explicit refresh and account changes invalidate it. Practice setup opens in the shared Dialog and preserves operation IDs for uncertain retries.

- Grid/list collection toggles reuse `ViewToggle`. Grid view means two equal columns using `workspace-compact-grid`, with fixed-height compact cards, two-line ellipsis previews and truncated metadata. Full content opens in the shared Dialog; long text never expands grid rows. Mistake practice has one toolbar action beside the view toggle; its filters and generation options appear only in that dialog.
