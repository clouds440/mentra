# Frontend loading and page caching

`components/ui/Skeleton.tsx` provides `bar`, `text`, `card`, `button`, `table`, `list`, `chat` and `form` shapes. Use `rows`, `columns` and `className` to fit the data region. It uses semantic theme tokens, an accessible loading status and reduced-motion support. `PageLoader` centers a small spinner with no visible text when the application shell cannot render yet. Buttons support `loading` while preserving their action label.

Page shells and navigation render independently from data. Data regions use skeletons in chat, sidebar history, assessments, Library, material details and uploads, Progress, Events, notifications, settings, memories, attachment contexts and source/reference viewers. Existing chat messages and forms remain visible during background work.

`services/pageCache.ts` stores at most 128 page responses in memory for 30 seconds. Concurrent reads share a request; cancelling one consumer does not cancel another. Account changes abort requests and clear the store before rendering the new identity. Successful writes and explicit refreshes invalidate cached responses; requests from an earlier cache generation cannot repopulate it. Authentication and profile restoration, live chat, assessment attempts and responses with active document jobs bypass caching. Existing chat storage continues to own conversation revision synchronization, history and pending turns.

Mounted page views refresh on focus, reconnection, visibility and once per minute while visible. Editable notification preferences and assessment attempts avoid background replacement while being edited. The cache is not persistent and does not provide offline access.

`services/userError.ts` supplies outcome-only error copy using status/code. Arbitrary backend messages, schema validation messages and stored job/turn errors are not rendered as product alerts.

Validation: `npx playwright test --config playwright.loading.config.ts`, existing voice browser tests, `npm run build`, `npm run check:theme`.
