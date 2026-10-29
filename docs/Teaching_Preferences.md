# Teaching preferences

Mentra stores user-owned teaching defaults separately from evidence-based learner state. The existing profile JSON and versioned update endpoint are reused; no database migration, extra lookup tool or model call is needed.

| Control | Stored field | Values and behavior |
|---|---|---|
| Teaching approach | `learning_preference` | `balanced` (Adaptive), `examples_first`, `step_by_step`, `conceptual`. Changes explanation structure. |
| Participation | `participation` | `adaptive`, `interactive`, `mostly_explanations`. Interactive favors a useful ungraded activity within an active learning exchange; native input waits for the learner. It does not append exercises to ordinary factual requests. |
| Explanation detail | `explanation_depth` | `brief`, `standard`, `deep` (Detailed). Bounded guidance, not output truncation or a word quota. |
| Visual support | `visual_support` | `adaptive`, `prefer_visuals`, `mostly_text`. Independent of participation; requested visuals and necessary native inputs remain available. |
| Learning purpose | `learning_purpose` | `general` (question-led), `fundamentals`, `apply`, `exam`, `explore`. Shapes relevant teaching plans and next steps; never authorizes assessment creation. |

Defaults are Adaptive / Adaptive / Standard / Adaptive, with question-led purpose. Current requests/corrections take precedence, followed by task/workflow requirements, relevant topic evidence and saved defaults. Education supplies background vocabulary/prerequisites, not proof of topic mastery. Background/interests and goals affect only relevant examples/plans. Broad estimates remain separate, uncertain and evidence-based.

## Boundaries and compatibility

- `backend/app/langchain/response_style.py` locally resolves allowlisted selections into the existing `response_style` packet. Raw goal/background strings remain profile data, never server instructions. Invalid selections cannot become policy text.
- `backend/app/langchain/prompts/chat_ui.py` owns UI participation/visual instructions, including the shared post-input-tool receipt guidance. Only the final reply is displayed as answer text; teaching prose must remain in that reply alongside the activity. Never solve the activity for the learner.
- Existing on-demand visual references and common bound UI tools are unchanged. Preferring visuals does not preload frontend bundles or force charts into simple answers.
- Shared UI guidance makes participation selective: requested teaching/practice, an ongoing lesson or a currently pursued learning goal can justify a short check. Lookups, reports, conversions, charts and finished artifacts normally end when delivered. A visual alone does not justify an exercise; unanswered activities remain pending. Explicit requests still take precedence. Equation-based exploration is independently chosen when adjustable relationships help, without requiring explicit slider instructions. These policy changes add no runtime model calls or profile mutations.
- Historical profiles, calibration snapshots and evidence remain readable. Legacy `concise` keeps its runtime behavior; editing/display maps it to Adaptive + Brief. The legacy `interactive` alias maps to Adaptive + Interactive participation. Explicitly selecting Detailed after conversion works normally. No immutable snapshots are migrated or rewritten.
- Missing new fields receive defaults on reads. Older clients omitting new fields preserve current values on updates; explicit default values clear them. Existing optimistic version checks and conflict handling remain.
- Preference-only edits preserve context version, estimates, calibration and evidence. Existing education/background scope-change behavior remains.
- Settings and onboarding reuse one option catalog, shared Select/FormField primitives and a local illustrative preview. Preview choices never invoke AI, submit profile changes, grade a learner or write evidence. They are reset when a preference changes.
- Profile-owned preferences are recognized by memory validation rather than duplicated as memories. Evaluators cannot modify user-owned profile fields.

## Acceptance — 2026-10-28

- Production TypeScript/Vite build passed; theme and UI checks passed.
- 24 real-PostgreSQL profile checks passed in a disposable database, including legacy-client preservation and preference-only calibration/evidence preservation.
- 27 reply-policy, interaction and prompt-efficiency checks passed after the final receipt change.
- 8 real-auth onboarding/profile/calibration browser journeys passed. Five fixture browser checks passed, including mobile/desktop combinations, local preview, legacy conversion, draft conflict recovery and immediate refresh.
- All 10 configured-model scenarios passed: examples + native activity, mostly explanations, simple fact, explicit explanation override, preferred visual, mostly text, explicit diagram override, brief, detailed and irrelevant goal isolation. Synthetic inputs created no learner records.
- In the final sample, brief/detailed explanations were 101/401 words. Ordinary paths used one model round; the native activity used two existing rounds (tool then final reply), without discovery. Policy resolution and previews add zero model calls. These are scenario results, not guarantees of identical prose or timing on every request.

Live checks initially exposed missing visible explanations after native input, fixed by shared final-reply/receipt guidance. A test also incorrectly treated rhetorical question marks as learner prompts; it now checks unsolicited participation rather than punctuation. Temporary test services and raw outputs are removed after acceptance; reusable scripts/tests remain.

## Local Docker rollout — 2026-10-28

Rebuilt and restarted `mentra-backend:latest` (`a99afd87885e`) and `mentra-frontend:latest` (`966020025877`). Backend/frontend healthy; frontend HTTP and API readiness both returned 200. All five background services use the rebuilt backend image. The deployed backend accepted/resolved Interactive + Prefer visuals, and the served frontend bundle contains the preferences preview. No learner records were changed by smoke checks. This is a local Compose rollout, not a remote registry push or public deployment.
