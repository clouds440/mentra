# Follow-up edit optimization

The complete persistent chat suffix is loaded by `chat/service.py`, then budgeted by the coordinator. Previously, a follow-up could be routed by words such as “event,” and trimming could discard the response being edited. Assessment revisions skipped topic selection but still redesigned/regenerated the assessment.

Implemented changes:

- Recognize edits to a visible text/code artifact and select no domain tools. Protect the original response and its adjacent request during budgeting; ask for a smaller excerpt if it cannot fit instead of reconstructing missing code from a summary. One answer call can return the revised artifact.
- Load edit instructions only for this path, with no universal prompt-token increase. Preserve identity, constraints and unchanged content; provide the complete revision unless the learner requests a patch or excerpt.
- Reuse validated public web-source URLs as ordinary Markdown links when editing a research response. This neither searches again nor claims fresh verification. Canonical original messages remain unchanged. Missing source provenance, private Library/history references, new evidence and explicit verification keep their normal domain paths.
- Use visible assessment IDs without a lookup tool or speculative recent-assessment read. Revision tools still read authoritative owned records and enforce conversation/context scope.
- Reuse accepted assessment structure for compatible content revisions. Explicit question references generate only those items; unselected questions retain their exact content, concept IDs and private grading data. Skip mastery reranking and fresh learner-context reads. Changed questions still undergo generation/key/rubric/concept validation; new concepts use the learner facade normally.
- Preserve original citation-token identities when merging fresh assessment grounding. Retain independent checkpoints for partial edits. Structural changes use the full validated path; incompatible partial/structural combinations fail explicitly.
- Persist an immutable revised assessment version, preserving original attempts, grades and learner evidence. Creating/revising a question does not establish mastery.

## Offline measurement

Changing question 2 in a 20-question assessment, compared with the full-regeneration path using the same synthetic services:

| Metric | Full regeneration | Scoped revision |
|---|---:|---:|
| Content-workflow model calls | 2 | 1 |
| Estimated input tokens | 5,564 | 2,218 |
| Estimated output tokens | 2,219 | 120 |
| Questions generated | 20 | 1 |
| Final questions | 20 | 20 |

Approximately 60% fewer input tokens and 95% fewer output tokens. This comparison excludes chat routing, network and persistence latency. Tests additionally verify one chat routing call for compatible card edits, with no separate final narration call; ordinary visible artifact edits use one answer call. These are controlled checks, not production wall-clock or live-provider quality claims. No additional paid provider calls were used.

Run `backend/testing/followup_evaluation.py` with project Python and `PYTHONPATH=backend` to regenerate the [evidence](Followup_Edit_Optimization_Evidence_2026-10-27.json). The general 42-request/five-workflow offline cost gate also still passes. Regression coverage includes preserved originals, complete context, private-data ownership fences, unchanged grading keys/concepts, no reranking, citation stability and research-link preservation.

Final expanded suite: 210 run, 161 passed and 49 skipped. Three targeted revision integration checks additionally passed against a temporary isolated PostgreSQL 17 database: revision persistence/original preservation, foreign-chat/invented-instruction rejection, and large revision batching. The remaining skipped database checks were not represented as passes. Backend/frontend Docker images were rebuilt; all application services were recreated together. This does not establish production latency or live-provider edit quality. No extra paid model calls were made.
