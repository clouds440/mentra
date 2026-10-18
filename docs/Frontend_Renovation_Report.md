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
