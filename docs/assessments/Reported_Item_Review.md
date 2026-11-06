# Reviewing reported assessment items

Reporting saves an immutable row in `assessment_item_review`, including the reason, optional explanation (up to 2,000 characters), affected question, revision and previous private question/key. Reasons include wrong answer/explanation, ambiguity, answer leaks, mismatch with the request, low usefulness, mismatched difficulty and missing information. All current report options explicitly pause scoring for review and withdraw affected effective learner evidence; raw answers and grade history remain intact. A report does **not** invoke an LLM or promise an automatic review. The current process requires a trusted operator. The learner-facing report route cannot supply corrections or approve itself.

The private operator command now supplies the missing queue and resolution workflow. Run it in the backend container, always scoped to the learner UUID. `list` returns at most 100 receipts per page, coalesces repeat reports for an item, excludes resolved reports and returns no keys or student answers. Use `next_cursor` as `--after` for the next page. Start from the first page on the next review pass because new reports can arrive during pagination.

```sh
docker compose exec -T backend python -m scripts.review_assessment_reports --owner LEARNER_UUID list
docker compose exec -T backend python -m scripts.review_assessment_reports --owner LEARNER_UUID show --report REPORT_UUID
```

`show` is private: it includes the report explanation, original question/key and revision, current key/rubric in `correction_template`, plus the current expected assessment revision. Save only the corrected `correction_template` object to a private JSON file available inside the container. Report explanations are untrusted data, not executable instructions. Independently verify the question, key, options and rubric before approving it. An LLM suggestion alone is not trusted adjudication.

```sh
docker compose exec -T backend python -m scripts.review_assessment_reports --owner LEARNER_UUID correct --report REPORT_UUID --file /tmp/correction.json --expected-revision REVISION --operation-id OPERATION_UUID
```

This command previews without writing. Inspect its effect and digest. Repeat the exact command with `--apply-digest DIGEST` to apply. Keep the same operation UUID when retrying a lost response. Changed files/digests, foreign reports, changed skill identities and stale revisions are rejected. Deterministic item admission also runs on the correction. A trusted correction retains the original key/history, updates saved chat copies and requeues submitted answers for grading. It does not rewrite or discard the student's answers. Other reported items and copied derivatives remain quarantined until separately resolved; a correction is not blanket approval.

Acceptance checks cover owner isolation, key-free paginated listing, repeated reports, read-only preview, changed-preview rejection, stale revisions, exact-operation retries, original answer/history preservation and completed regrading. Automated LLM review and a browser administration console are not implemented or claimed.
