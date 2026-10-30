# Showcase capture notes

The root README gallery was captured on **30 October 2026** in Chromium against
the running local Docker application. A separate synthetic account was created
for the tour; no existing learner's private records were used and no API mocks
were installed in the capture browser.

| What was exercised | Capture evidence |
| --- | --- |
| Teaching conversation | Configured model response, worked example, diagram and saved conversation |
| Exploratory chart | Configured model's data/equation chart, real local slider updates and exports toolbar |
| Conversational input | Actual generated native grouped questionnaire |
| Private sources | Synthetic TXT source uploaded through Files and associated with Library |
| Practice and feedback | Three generated MCQs, a submitted synthetic attempt, grading and saved mistake history |
| Paper-answer preparation | A second attempt with an actual TXT upload/extraction, awaiting review/confirmation |
| Progress | The generated skills and real recorded evidence state; ungrouped skills are shown as ungrouped |
| Planning and reminders | Synthetic agenda entries and an actual reminder delivered to the showcase inbox |
| Preferences and responsive UI | Actual profile editor, mobile viewport and verified Dark theme |

The screenshots demonstrate product behavior, not a handwriting-quality,
retrieval-quality or learning-accuracy benchmark. The paper-answer image uses TXT
extraction, not a claim about photographed handwriting. Questionnaire answers were
not fabricated or submitted on behalf of a real learner.

## Files

Current images live beside their module's documentation in
`screenshots/showcase/`. Historical screenshots remain in each module's
`screenshots/history/`. [capture-manifest.json](capture-manifest.json) records
capture descriptions and viewports. The chart GIF contains eight actual browser
screenshots encoded as a looping animation; it is not an AI-generated animation.

## Refreshing the gallery

Start the configured local Mentra stack, install frontend dependencies and a
Playwright Chromium browser, then run from the repository root:

```sh
node frontend/scripts/capture-showcase.mjs
```

The [helper](../../../frontend/scripts/capture-showcase.mjs) creates a new synthetic
account and records on every run. It makes live calls to the configured model and
file providers and can consume their quotas. It is an explicit documentation
workflow, not a routine test or a fixture-only renderer.

| Optional variable | Purpose |
| --- | --- |
| `SHOWCASE_WEB_URL`, `SHOWCASE_API_URL` | Override local web origin and API base; defaults are localhost:5173 and localhost:8000/api/v1 |
| `SHOWCASE_HEADED=1` | Show Chromium while capturing |
| `SHOWCASE_PYTHON` | Python with Pillow for GIF encoding; defaults to the repository virtual environment |
| `SHOWCASE_KEEP_SESSION=1` | Explicitly retain a browser session and created IDs under ignored .cache for follow-up captures; treat that session file as a secret |

Inspect every output before replacing the gallery. Wait for loaded content and
verify the capture is useful; do not publish skeleton/loading screenshots as a
finished feature. Optional model/provider failures are recorded in the manifest,
and the resulting gallery must not claim capabilities that were not captured.

[Product documentation](../README.md) · [Documentation index](../../README.md)
