# Frontend Engineering Standards

> **Build for the requirements we have, while leaving clean boundaries for the requirements we expect. Do not implement future features before they exist.**

These standards describe the current React, TypeScript, Vite, and Tailwind CSS codebase. Update them when an important frontend convention changes.

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
- Keep page-specific behavior and UI with the relevant page/feature. Do not add routes, guards, onboarding, or account flows without a product requirement.
- `/login` and `/register` use `AuthLayout` and a shared username/password form. `RequireGuest` redirects signed-in users; `RequireAuth` guards the workspace and preserves the requested destination.
- The authenticated `StudentProfileProvider` owns profile restoration. `ProfileReady` handles loading/retry; `RequireOnboardingComplete` gates the workspace. `/onboarding` collects required information and optional calibration; `/calibration` resumes later from Settings.

## Components

- Keep components focused and composable; avoid large components that combine unrelated presentation and behavior.
- Use semantic HTML and preserve keyboard access, visible focus, and disabled behavior.
- Do not spread backend calls throughout presentation components; use `services/`.
- Shared primitives accept `className` and extend native HTML attributes when appropriate.
- Prefer composition over a broad prop surface. Do not generalize a one-off component until a second real use case exists.
- Keep feature UI such as chat messages and composers outside `components/ui/`; reserve that directory for primitives.
- Use the established icon library (`lucide-react`) consistently. Give icon-only controls accessible names and titles where useful; do not use emoji as application icons.
- Empty states should explain the current state honestly and offer only actions that work. Do not present mock data as saved learner activity or invent analytics.
- Reuse existing UI primitives, including Spinner/loading states and the accessible `Toggle` for binary preferences. Keep theme selection in the existing account drawer and use semantic Light/Dark/System tokens.
- Render Markdown with the existing `components/content/MarkdownContent` and shared Prism `CodeBlock`, used by chat and Library. Keep feature reference resolution in its feature adapter; never enable arbitrary HTML or duplicate the formatting stack.

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
