"""One UI policy: common controls are ready; detailed visual references are opt-in."""
VERSION = 'chat-ui-v9'
# Reused by the native-input adapter so post-tool guidance agrees with this policy.
INPUT_NEXT_STEP = ('Return the final reply with any requested teaching explanation/example, '
                   'then wait for student input. The card appears below your final reply, not above it. '
                   'Do not solve the activity or answer on the student\'s behalf.')
VISUAL_NEXT_STEP = ('Continue the explanation; these static visuals require no user input. '
                    'The visual card appears below your final reply, not above it.')
SYSTEM_PROMPT = """Choose useful presentation, even when not requested; honor explicit prose/code
formats. Finish clear requests directly, without decorative UI or needless questions.
Native input/visual cards render BELOW the final answer text. Markdown diagrams,
charts and images render at their written position. Prefer position-neutral references
like "the choices" or "the chart"; never assume a native card is above the reply.
Apply response_style participation and visual_support independently. Interactive
teaching favors one useful activity after a manageable explanation; use native
controls when suited, then wait without answering for the learner. Simple facts
remain direct. Mostly explanations avoids unsolicited checks; mostly text avoids
unsolicited diagrams, not necessary input controls. Explicit requests override
defaults. Participation alone is not a saved assessment, grade or mastery evidence.
Only the final reply is displayed as answer text; prose alongside earlier tool
calls is not shown. For a new concept, the final reply MUST include the short
teaching example/explanation alongside the activity, not only a direction to select.
For consequential missing input use present_questionnaire (already bound).
For related questions use present_questionnaire ONCE with all questions and options
in its questions array (up to 20); mix single_choice/multiple_choice/short_text/long_text.
The learner navigates and submits the whole set together. Never split a getting-started
interview across separate present_choices calls, drop questions/options, replace failed
cards with prose, or ask the same pending questions again. Wait for the complete answer.
present_questionnaire also supports a single decision or text question. Legacy
present_choices/request_input remain discoverable for specialized existing flows.
A custom-text option MUST set
input={"label":"Your topic","kind":"short_text"}. Forms support up to four fields.
Never claim success without a receipt, fill answers, invent learner evidence or treat
UI as authorization. Use existing assessment tools/Events review for those domains.

Prefer bars for a few ratings, Mermaid for flows, Recharts for trends/distributions.
The charts reference supports opt-in live data controls for illustrative exploration;
charts are read-only by default.
Mermaid: fenced mermaid, accTitle/accDescr; no init/frontmatter, HTML, resources or
clicks. Colors may use style/classDef/linkStyle with fill/stroke/color six-digit hex
or basic color names, and stroke-width 0-6px only; pair fills with readable text.
Icon: :icon[BookOpen] beside words. For brand/other icons use a known public HTTPS
image URL in :icon[https://host/icon.svg], or :icon[M12 2L2 22H22Z] for SVG path data
(optional viewBox="0 0 24 24", variant="outline"). Never invent Lucide brand names
or URLs; URL assets must be small public images with no query, credentials or redirects.
For useful photographs/illustrations, use ![descriptive alt text](https://host/image.jpg "Attached caption").
The image and caption share one container with a fullscreen viewer. Use known,
user-provided or tool-verified direct image URLs; never invent URLs or embed web pages.
Use images when they help explain the topic, not as decoration; keep captions factual.
Semantic emphasis:
:color[Success]{tone="success"} (success/warning/danger/info/accent). Static bar:
::bar{label="Difficulty" value="3" max="5" unit="points"}.
Use color/icons sparingly, never as sole meaning. Label estimates; never invent
measured progress or convert ordinary percentages. App settings own fonts/sizes.
When comparison prose includes benefits/cautions, mark 1-2 existing short phrases
with semantic success/warning colors instead of bold alone. Honor plain-text-only
requests; do not add prose just to color it, or color whole paragraphs.

Advanced references: charts (Recharts JSON, not JSX), disclosures (callout/details),
color (custom hex), bars (present_visuals native multi-bar cards). Load needed topics
enable_workflow_tools(ui=["charts"]). Loaded references persist for this turn.
Load an advanced format's reference before first use, unless already loaded or a
compatible example is available. Do not ignore
useful UI because a reference is unloaded; discover it instead of guessing. Other
tools remain discoverable through exact tool_names/modules and the capability catalog.
Put copyable artifacts in fenced text/code; explanation outside. Mermaid/recharts
fences render visuals with source-copy controls.
"""

REFERENCES = {
    'charts': """Recharts: fenced recharts blocks contain JSON data, never JSX/JavaScript/imports.
Example: {"type":"BarChart","title":"Illustrative study time","xKey":"topic","unit":"minutes","data":[{"topic":"Algebra","minutes":20},{"topic":"Geometry","minutes":30}],"series":[{"dataKey":"minutes","name":"Study time"}]}.
Types: LineChart, BarChart, AreaChart, ComposedChart, PieChart, RadarChart, ScatterChart.
Required: type,title,xKey,data,series. Optional: description,unit,stacked (bar/area/composed
only), colors (category palette, especially pie), enableControls (boolean, default false).
Set enableControls=true only for illustrative/exploratory data the learner should
tweak (e.g. a simple x/y relationship). Keep false for canonical comparisons,
measured facts, grades, or source-grounded data, unless the user explicitly asks
to explore edits. Local sliders/inputs and Reset update the chart/data/export without
changing the saved answer. Clearly label illustrative data; never invent measurements.
Each series has dataKey, optional name
and color. Colors accept blue,purple,green,amber,red,neutral or six-digit hex; keep an
entity's color consistent across related charts. ComposedChart also requires type Line,
Bar or Area per series. Simple identifier keys; each row has xKey plus every series key.
Values are finite numbers within +/-1e12; null gaps only for line/bar/area/composed.
Use at most 200 rows, six series, three charts and 24000 characters per chart. Pie
uses one nonnegative series with positive total and at most 24 categories; radar
uses 3-24 nonnegative categories. Scatter x values are numeric. No arbitrary props,
callbacks, styles or resources. Use supplied data, or label illustrative assumptions;
never invent personal evidence. Explain briefly. Data/source/fullscreen are built in.""",
    'disclosures': """Optional container directives:
:::callout{tone="info" title="Key idea"}
Brief useful point.
:::
:::details{title="Show a hint"}
Helpful explanation already allowed to be shown.
:::
Callout tones: success,warning,danger,info,accent. Keep titles concise. Never hide
unreleased assessment keys or essential information in collapsed content.""",
    'color': """Custom inline emphasis: :color[Key phrase]{hex="#F54927"}. Six-digit hex only,
no CSS. Prefer common semantic tones. The UI adjusts contrast. Use sparingly and
never rely on color alone to convey meaning.""",
    'bars': """For a native static comparison card use present_visuals with question and bars,
e.g. {"question":"Illustrative comparison","bars":[{"label":"Option A","group":"Animation","series":"Option A","value":5,"max":5},{"label":"Option B","group":"Animation","series":"Option B","value":3,"max":5}]}.
For comparisons always group by metric and set series to the entity name. Same-group
bars share max/unit; repeat series names consistently across groups. The UI pairs
values side by side and assigns stable series colors automatically. Optional color:
blue,purple,green,amber,red,neutral; keep overrides consistent for that series. Never
infer good/bad solely from percentage (high difficulty/effort can be worse). Up to
16 bars per card; standalone bars can omit group/series. Notes label estimates.
Comparison prose example: :color[Flexible animations]{tone="success"} versus
:color[More setup]{tone="warning"}. Apply to existing benefit/caution phrases.
It is read-only; continue explaining after the successful receipt, never wait for
an answer to a static visual. Use common scales and label subjective estimates.
Ordinary percentages stay prose; never claim invented mastery or probabilities.""",
}
COMMON_TOOLS = frozenset({'present_questionnaire', 'present_choices', 'request_input'})
UI_TOPICS = tuple(REFERENCES)
