# Practise my mistakes

Graded results offer incorrect questions plus an **Include partially correct
questions** toggle and explicit selection (one to twenty parts). **Prepare mistake
practice** creates a saved follow-up assessment without a provider call. Starting
an attempt and submitting answers reuse the existing assessment workflows.

`POST /api/v1/assessments/attempts/{attempt_id}/practice` accepts
`client_request_id`, `expected_grade_revision` and `question_ids`. The server derives
eligibility from current owned grades, preserves source order, and rejects stale
results, correct/unknown/duplicate IDs and oversized selections. Owner transactions
serialize creation, corrections and deletion. Operation fingerprints bind the source
attempt, grade revision and selected IDs; a lost-response retry recovers the saved
follow-up even if the source later changes or is deleted. A changed payload conflicts.

The follow-up has new question IDs and its own answer sheet, attempts and grades.
Original questions/answers/results remain intact. Private keys and rubrics are
copied internally and never included in the public assessment. Shared passages,
numbering and nested part references survive. For paper sources a read-only public
snapshot of all original prompts/options and paper/section instructions is retained
as reference context, including for grading. Reference parts take no answers and
carry no follow-up marks. Repeating a derivative retains its original reference
snapshot; no recursive expansion of the reference packet occurs.

`assessment.practice_lineage` records source assessment/attempt/grade revision,
known answer exposure and the mapping from child question IDs to root item IDs.
`practice_source` is its safe public projection; the private item map is excluded.
Saved snapshots remain valid if a source is later corrected/deleted. Source deletion
does not cascade into independent follow-ups. The existing 200-assessment and
20-attempt guards apply; creation never deletes history to make room.

Answer feedback may already have exposed the solution. Evidence therefore preserves
the root item identity, forces independence to zero and records an effective repeat
attempt number (local attempt number plus one), regardless of a submitted independence
self-report. Corrections preserve these identities and supersede only their own
earlier evidence. Repeated practice adds no independent items, mastery increase or
fresh recall demonstration. It can still count as a practice observation and expose
a need for verification under the existing conservative policy.

The existing revision and chat-publication paths inherit exposure conservatively
when revising these worksheets. Exact retained prompt/context pairs keep their root
item IDs. Changed questions remain exposure-qualified practice. Generate a new
assessment without a revision source for a separate fresh verification activity.

Deploy through migration **`20261017_0027`** before starting the new application code.
It adds a nullable JSONB column and preserves existing records. Downgrade refuses
to remove the column while any lineage is stored, because erasing it could make
exposed questions appear independent. A rollback must preserve this evidence contract;
do not erase practice records simply to bypass the guard.


## Deployment fences and retries

Migration `0027` adds permanent owner-scoped operation receipts and backfills existing
follow-ups. Retrying the same operation returns the same owned assessment. If that
assessment was explicitly deleted, the API returns `ASSESSMENT_PRACTICE_DELETED`
(410); it never silently recreates it. The UI offers an explicit new follow-up
operation. Conflicting payloads cannot reuse an operation ID.

A database trigger forces attempts on known-exposure assessments to `assisted`,
including writes from older workers. New code also applies that qualification on
start, submission and correction. Downgrade refuses to erase retained receipts or
exposure state; deleting a result does not make the receipt disposable.

Deleting a chat removes its unpublished drafts and queued generation jobs in the
same owner transaction. Enqueue/retry rechecks chat ownership and existence.
Saved assessments remain independently retained. Reference snapshots consume the
existing assessment quota; full reference text renders only when expanded.

See [deployment verification and rollout](../deployment/Product_Deployment_Hardening_2026-10-18.md).
