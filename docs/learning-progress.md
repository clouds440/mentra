# Learning Progress

The Learning tab separates topic suggestions, evidence-based understanding,
practice suggestions and useful follow-up reviews. No section treats accepting a
topic as demonstrating knowledge.

- **Topic suggestions to review:** unresolved concepts found during learning activity.
  Confirm promotes/reuses a canonical identity and links it to its owned learning
  context, when one was recorded. A suggestion without a context saves only the
  concept name. Dismiss discards the suggestion. Neither operation adds evidence or
  changes a mastery estimate. Assessment generation resolves its own practice targets
  automatically; these are not a prerequisite for generating a quiz.
- **Your understanding:** all concepts linked to the selected owned contexts, including
  new topics whose estimates remain unknown. Default scope is active/related areas;
  an explicit owned context can recover dormant/archived knowledge. Status explanations
  distinguish getting started, developing, demonstrated, needs practice and review.
- **What to study next:** bounded practice recommendations. New topics may appear to
  help students get started; all reasons are translated into plain language.
- **Check your understanding:** follow-ups backed by actual evidence and a meaningful
  reason to revisit it. New/insufficient-evidence and untested-difficulty entries are
  hidden. Mixed evidence can still warrant review. Filtering happens before top-K
  selection so unsupported topics cannot crowd out useful suggestions.

`GET /api/v1/learning/understanding` accepts `query` (up to 200 characters), optional
owned `context_id`, `limit` (1–50, default 10), and `offset` (0–100000). It returns
`items`, matching `total`, unfiltered `total_concepts`, effective `offset`, `limit`,
and `generated_at`. Search uses normalized name/alias substrings. Queries remain
owner-scoped, duplicates across context links count once, and stale offsets clamp
to the final page. Responses are private/no-store; the ordinary bounded frontend
page cache remains owner/query-scoped and invalidates after review mutations.

The page debounces search, resets paging on a new query/context, aborts stale
consumers and uses accessible numbered Previous/Next controls. Confirm all reviews
the shown snapshot through the existing idempotent owner-bound actions. Requests
are sequential; successes remain saved if another fails, and only unresolved
suggestions remain for retry. More pending suggestions can appear after a batch.
Single-action loading distinguishes Confirm from Dismiss. Review results and
understanding counts refresh after successful changes.

The compact LLM context and assessment bootstrap ranking are unchanged. Page-only
visibility rules do not remove new concepts from adaptive AI practice workflows.
