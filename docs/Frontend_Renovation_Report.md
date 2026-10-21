# Frontend renovation implementation and evidence

14 October 2026. Companion to `Mentra_Frontend_Renovation_Plan.md`.

## Implemented scope

The existing route set uses the compact visual system: authentication,
onboarding/calibration, Chat, Library/list/upload/detail, Assessments/create/attempt,
Progress/Learning/Events, Notifications and Settings/Profile/Memories/preferences.
Shared changes reach inline assessment/choice/event cards, attachments, voice,
citations, source/history readers, account controls and dropdowns.

Default controls are 36px, compact actions 32px, and larger actions 40px. Coarse
pointers get 40px controls and 44px icon hit areas. Cards have 14px corners, controls
9px corners, panel padding 16px and restrained optional elevation. Both palettes
have measured text/control contrast. Dark mode uses neutral charcoal surfaces and
Mentra's accent. No font downloads or animation dependencies were added.

Shared boundaries include Button/link styles/IconButton, FormField, Tabs and native
Dialog. Existing Select/Popover/Toggle/FileInput and workspace patterns were refined.
Features own domain behavior/state. Route-local lazy boundaries preserve the shell
and session providers; completed message rows use shallow memoization.

## Layout-change ledger

| Area | Change | Reason |
| --- | --- | --- |
| Sidebar/composer/account/bell | Positions retained; compact shared geometry | Preserve familiar interaction |
| Workspace title | Removed duplicate shell title; retained page H1 | Clear hierarchy |
| Narrow page actions | Row beneath full-width title/description | Prevent squeezed descriptions |
| Material detail | Study in chat in header; maintenance grouped below details | Separate study from maintenance |
| Mobile history | Visible after desktop collapse | Repair missing conversations |
| Tabs/dialogs/forms/cards | Positions retained; common styling/behavior | Consistency |

## Workflow fixes and preservation

- Closed mobile navigation is inert. Open navigation owns focus/background
  inertness and restores its opener after nested overlays finish closing.
- Dialogs retain native top-layer behavior. Development effect replay cannot dismiss
  a reopened modal; Escape closes before parent unmount/focus restoration.
- Theme/calibration native radios cover their visible labels rather than tiny
  hidden focus targets.
- Refresh coalesces focus/visibility bursts and avoids overlapping Library/detail
  reads. Manual mutation refresh still invalidates/reloads promptly.
- Library/understanding results are query-bound; quiet understanding refresh retains
  rows. Different filters cannot present old results as current.
- Dirty material details retain their original revision/draft. Changed revisions
  offer explicit Reload saved details before Save proceeds.
- Loading controls retain width and accessible names. Material/event/notification
  and inline assessment actions identify the operation actually running.
- Chat scroll restoration, prepend anchoring, manual-scroll priority, bounded
  windows, turn recovery, atomic calibration, assessment history and event
  civil-date/timezone behavior retain their existing contracts.
- New Chat fences the old composer during the router handoff, preventing a late
  draft reset from erasing the first keystroke in the new conversation.
- Voice remains beside Send and fills the draft; sources remain contextual to `@`.
  Voice levels animate scale rather than layout height.

The deterministic browser AI fixture now requests the real study tool and consumes
its current source receipts. Old fixtures expected an obsolete eager prompt packet.
This changes test inference only; retrieval, authorization and persistence remain
real. Production backend behavior was not changed.

## Performance evidence

Fresh baseline entry JavaScript: 669.18 kB (201.32 kB gzip estimate). Renovated entry:
approximately 292 kB (93 kB gzip estimate), about 56% smaller uncompressed. This
compares the entry file, not total downloads for every route. Feature chunks load
on demand; Markdown/highlighting remains shared and worker/grammar loading retained.

The same 200-message development typing fixture recorded 25 tasks over 50ms before
message memoization, with a maximum of 255ms, and zero observed typing long tasks
after it. Raw measurements are in
`frontend-renovation/typing-before-memo-development.json` and
`frontend-renovation/typing-after-memo-development.json`. This is a controlled local
comparison, not a physical-device or provider latency benchmark.

Production serving enables gzip and immutable caching for content-hashed assets.
HTML/theme bootstrap revalidate; missing chunks return 404 and SPA routing remains.

## Validation record

- Production build, theme check, UI contrast/style check and `git diff --check` passed.
- Final production browser run: **17 passed**, including 72 route/theme/viewport
  captures, navigation, tabs, draft protection, reduced motion and performance.
- Final affected workflow run: **58 passed** against a temporary dedicated
  PostgreSQL container with disposable migrated schemas.
- The preceding broad run passed 167 tests and exposed one New Chat draft race.
  That race was fixed and verified in both final runs above. The entire broad suite
  was not repeated after the fix.
- Docker production frontend build passed. The local frontend container was
  recreated and is healthy. Actual serving checks passed for gzip, immutable
  hashed assets, fresh HTML/theme, missing-asset 404 and SPA routing.
- Temporary test containers and the generated database credential file were removed.

The route matrix covers Light/Dark at 320, 390, 768 and 1440px. The final local
200-message production fixture observed zero typing tasks over 50ms; measured
layout shift was 0.043 for Library, 0.014 for Assessments and below 0.001 for Chat.
Raw results are in `frontend-renovation/production-performance.json`.

Visual evidence: [desktop before](frontend-renovation/library-desktop-before.png),
[desktop after](frontend-renovation/library-desktop-after.png),
[mobile before](frontend-renovation/library-mobile-before.png),
[mobile after](frontend-renovation/library-mobile-after.png),
[Progress](frontend-renovation/progress-desktop-after.png) and
[assessment](frontend-renovation/assessment-mobile-after.png).

Evidence distinguishes UI fixtures from real persistence integration. No application
data migration or public deployment is included. Physical mobile, Safari/Firefox,
field-user performance and a complete manual screen-reader audit were not verified.


## 18 October 2026 product hardening

Preserved shell placement while adding shared saved-chat search/exchange dialogs,
responsive mistake-practice selection and a scrollable progress-evidence view with
sticky controls. Material eligibility is fenced to the current selection, metadata
requests are bounded, and reference Markdown loads on expansion. See the
[verification report](Product_Deployment_Hardening_2026-10-18.md).


## 18 October 2026 simplified assessment creation

Library card actions now use small shared secondary buttons with separate icons.
Creation uses one topic field, optional material selection, inclusion instructions,
keyboard-operable multi-format cards and a bounded question count. Advanced settings
are resolved through the existing shared assessment pipeline. Responsive light/dark
UI, material eligibility, draft retention, retries and exact linked targets were
covered in 51 browser checks. Live synthetic English/Urdu planning checks passed;
see [the assessment engine contract](Assessment_Engine.md#simplified-creation--18-october-2026).


The final two-column mobile format layout passed three additional deployed-image
checks at 360 light, 390 dark and 1440 light (overlapping the 51-case set). Local
backend/frontend and all three workers were refreshed; readiness passed and each
container had zero restarts. The disposable PostgreSQL fixture was removed with
its test-only volume. Application data volumes were preserved.

[Mobile creation](product-improvements/assessment-create-mobile.png) ·
[Desktop creation](product-improvements/assessment-create-desktop.png)

[Mobile format selection](product-improvements/assessment-formats-mobile.png)

## 2026-10-19 — Frontend action and disclosure consistency

Audited route pages and feature controls for bare action links, small interaction targets and inconsistent selection states. Preserved the shell, page placement, inline citations and plain Copy controls.

| Area | Improvement |
| --- | --- |
| Library, progress, events and memories | Compact shared secondary buttons for standalone navigation and practice actions |
| Chat, assessments, notifications and settings | Consistent bordered recovery controls with visible keyboard focus; chat recovery actions have separation |
| Assessment history | Full-width selectable rows with a visible and accessible selected state |
| Source lists and disclosures | Padded source rows; shared disclosure hover/focus styling while retaining native markers and keyboard behavior |
| Event editor and calibration | Bordered radio choices with selected states; shared calibration skip control |
| Quiz navigation | Shared coarse-pointer sizing for numbered question controls |

Validation: production TypeScript/Vite build, theme checks, UI checks and diff whitespace checks passed. All 51 existing browser regression cases passed, including nine workspace routes at 320, 390, 768 and 1440px in light and dark themes. Inspected mobile assessment, progress and event screenshots. API fixtures isolate these checks from real records; this is frontend validation, not backend integration coverage.

The local Docker image rebuild was attempted but could not connect to Docker Desktop's Linux engine. No running container was updated.

## 2026-10-19 — Mobile chat centering and quiet controls

The assistant avatar occupied a permanent 42px side column, shifting text and interactive cards to the right on phones. Below 640px the avatar now sits above a full-width response, giving the content the same 16px side margins as the composer. Desktop placement is unchanged.

Mobile chat navigation and notifications now sit in opposite top corners with 16px glyphs, 30px quiet circular surfaces and 44px hit areas. Unread notifications use a small dot while the accessible label retains the count. Safe-area spacing protects the controls and composer. The composer uses 16px mobile input text to avoid iOS focus zoom and caps long drafts at the smaller of 12rem or 30dvh. Empty chat has top clearance for the floating controls.

Verification: production build and theme/UI checks passed. Browser geometry checks cover equal response margins, corner positioning, touch targets, drawer opening and long drafts in a shortened viewport at 320/390/430px in both themes. These are Chromium emulation checks, not physical iPhone keyboard verification. The full selected regression suite ran against the rebuilt local Nginx frontend with API fixtures. The frontend container was rebuilt and replaced successfully; backend and workers were left running.

Screenshots: [320px light](product-improvements/chat-mobile-light.png), [390px dark](product-improvements/chat-mobile-dark.png).

### Compact mobile composer

The phone composer now starts as a single row with attachment on the left and microphone/send controls on the right. Text grows naturally into multiple lines, up to the existing viewport-aware height cap, and clearing it restores the compact row. While the textarea is focused the microphone is hidden; it returns on blur. The send control remains in the same position. Recording and transcription retain their dedicated voice surface and stop/cancel controls. Desktop layout is unchanged.

Verified compact height, wrapping, shrinking, microphone focus behavior and stable send position at 320/390/430px in both themes. The production build, UI/theme checks and 33 selected browser cases passed. Screenshots above show the updated composer.

The send button uses a smaller 30px visible surface and 15px glyph within its 44px touch target. The six mobile geometry cases passed again after this final adjustment.


## 2026-10-19 — Dedicated mistake-practice workspace

Assessments now includes a **Practice my mistakes** tab with a quiet revision setup card, multiple-topic/assessment dropdowns, an automatic practice action and paginated mistake history. Cards show feedback, repeated/partial/corrected state and a direct link to the source assessment attempt. The filtered action uses the compact label **Practice selected**. Existing assessment result cards link here instead of duplicating controls.

Revision creation uses the existing durable generation progress card. Refresh retains a queued job through the URL; a lost-response retry reuses the operation ID. Generated assessment cards show the server-owned Revision assessment tag and source-assessment links. Original results remain intact.

Validated the workspace at 320px light, 390px dark and 1440px light, with no document overflow, working filters and source links. The generation recovery test covers an interrupted request and navigation to the tagged result. Backend/frontend images and all workers were refreshed locally after the synthetic live-model check passed.

Final validation: **62 browser cases passed against the rebuilt frontend container**, covering the new tab plus assessment, chat, saved-search, product, follow-up and route-matrix regressions. Production build, theme/UI checks and whitespace checks passed. API readiness confirmed database, AI configuration, embeddings and Qdrant; all three workers are running. The disposable integration-test database was removed after verification.

Screenshots: [mobile](product-improvements/mistakes-mobile.png), [dark mobile](product-improvements/mistakes-dark.png), [desktop](product-improvements/mistakes-desktop.png).


### October 20: stable page caches and assessment review

Settled pages no longer refresh on timers, focus, visibility changes or reconnect. Owner-scoped in-memory caches persist until relevant writes, explicit refresh, bounded capacity eviction or account changes. Successful writes invalidate dependent domains and notify mounted views and same-owner tabs. Generation, grading and ingestion continue to poll only while unfinished, and completion invalidates their dependent views. Authentication checks still verify session access without resetting page content.

Mistake practice lives in Assessments; old Progress links redirect with filters and revision jobs intact. Mistake cards reuse the assessment answer component, resolving choice IDs to labels. Assessment list cards summarize the latest graded attempt with correct/incorrect counts (partial credit is included in incorrect and disclosed separately). Unattempted and ungraded attempts have distinct status badges. Summaries use one bounded, owner-scoped query for each page of assessments.


## October 22: chat, sidebar and mistake-history polish

The conversation now uses a 60rem maximum width (previously 52rem); the composer remains 52rem. Empty-chat suggestions use a compact responsive grid. The sidebar has a distinct semantic surface, quieter section spacing and a raised account capsule without the top divider. Light surfaces reduce glare and improve separation; dark surfaces are slightly darker. Both palettes retain checked text/control contrast.

Mistake history requests ten records in recent-first order, with learning-context, assessment and topic filters. Card/list choice and pagination live in the URL. Compact list rows disclose answer/feedback on demand. Practice setup opens in the existing native Dialog; source records, priority-based practice selection and operation-ID recovery remain intact. Learning-context filtering respects per-question revision lineage. The shared owner-scoped cache retains visited mistake pages for five minutes and remains capacity-bounded, mutation-invalidated and cleared on account changes.

Concepts and mistakes use the same Pagination primitive: chevrons without visible Previous/Next text, 28px desktop controls, matching page-number height and accessible labels. Touch controls retain the shared 40px minimum. Closed Select fields now let Escape reach their parent dialog; open dropdowns consume it first. Updated `frontend/standards.md` records these conventions.

Validation: production builds, theme/contrast checks, targeted Python static checks, ten PostgreSQL revision-practice integration tests and 39 distinct fixture-based browser cases passed across the selected suites. Coverage includes source links, retry IDs, filtered empty states, page caching/invalidation/owner isolation, Concepts navigation, mobile chat, sidebar resizing, tabs, account menus and modal Escape/focus restoration. An additional focused backend run verifies recent-first ordering across multiple assessments. Browser fixtures verify presentation and request contracts; they do not claim live AI generation or a full authenticated-user audit.

Screenshots: [wide chat](product-improvements/polish-chat-wide.png), [light mistake cards](product-improvements/polish-mistakes-light.png), [mobile mistake list](product-improvements/polish-mistakes-mobile.png), [dark account menu](product-improvements/polish-account-dark.png).

The local frontend/backend images and five workers were rebuilt/refreshed together. All 39 selected browser cases passed against the refreshed frontend container. API readiness reports database, AI configuration, embeddings and Qdrant OK; the login page returns HTTP 200. The disposable test database container was removed. No production deployment was performed.

### Follow-up: modal-only practice and actual compact grids

Removed the duplicate mistake setup panel. The only practice entry point is now the toolbar button beside the shared grid/list toggle; filters and question-count options appear inside its Dialog. Both mistake history and assessment feedback now use the shared `ViewToggle` and a two-column grid, including on phones. Cards stay 224px high, use two-line ellipsis previews and truncate metadata. Full mistake/result content opens in a shared Dialog; result review retains next/previous and colored numbered navigation. List view retains full content. Compact-grid paragraphs explicitly reset inherited chat Markdown margins to preserve consistent geometry.

Dark background, card/paper, surface, input and popover tokens were slightly darkened again. Text tokens remain legible and the shared contrast checks pass. `frontend/standards.md` now documents actual grid geometry, compact previews, full-content review and the single practice entry point.

Validation for this correction: all 25 affected browser cases passed against the rebuilt local frontend, including 320/390/1440px mistake grids, long-text truncation, full review dialogs, modal-only practice filters, source links, practice recovery and assessment results. Production build and theme/contrast checks passed. The local frontend container is healthy. Screenshots: [320px mistake grid](product-improvements/polish-mistakes-grid-mobile.png), [desktop mistake grid](product-improvements/polish-mistakes-grid-desktop.png), [assessment result grid](product-improvements/polish-results-grid-mobile.png).
