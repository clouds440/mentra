# Arabic quiz failure and multilingual assessment support

## Confirmed trace

The latest quiz request created a six-question mixed Arabic-alphabet assessment. On October 29 at 01:00:53 and 01:01:08 Asia/Karachi, generation validation rejected the returned batch as `wrong_question_format`. The first question's logged shape was valid; retained logs did not include every rejected item's content, so the exact failing item cannot be identified retrospectively. This was not an Arabic concept-name rejection.

The job retry endpoint succeeded at 01:01:25. Its next generation call was cancelled when Stop was requested around 01:02:17–20. Resume was accepted at 01:02:26. The later persisted job failure used a generic message; previous worker logging did not retain its precise pre-generation cause. New diagnostics record failure stage and code without private content. Daily file logging had reached its cap; retained Docker logs supplied the trace.

## Changes

| Area | Fix |
| --- | --- |
| Mixed-question repair | Feedback now identifies the failing batch position, expected type/input mode and actual option count. It contains no rejected wording or answers. Model repairs remain bounded. |
| True/false localization | Require exactly the stable `true` / `false` option IDs, while allowing natural labels in any language. Removed the English-only label validation and prompt requirement. |
| Outline consistency | Choice questions require one selectable answer; true/false outlines and questions must contain one binary proposition rather than several judgments plus a written task. |
| Native language content | Generation instructions explicitly preserve native spelling, script and diacritics, distinguish subject language from explanation language, and keep protocol enums unchanged. |
| Worker recovery diagnostics | Retain the latest successful checkpoint locally before recording a failure; persist safe failure stage/code and emit a content-free failure event. Completed sections remain available for retry. |

## Learner behavior

Concept names, broader topic labels, subskills, aliases, assessment text and answers accept Unicode. Lookup normalizes with NFKC and case folding; it does not require Latin letters or strip meaningful diacritics. Exact native labels reuse identity; the topic organizer can reuse supplied equivalent translations while keeping distinct skills separate. Naming a skill alone does not create mastery evidence. No language allowlist was added.

## Verification

- 29 completed regression tests passed: multilingual true/false, precise format repair, Arabic/Japanese concept reuse, grading, generation recovery, stop/resume and assessment intent.
- A fully synthetic live configured-model check created native Arabic concepts and resumed a failed six-question mixed Arabic quiz from its checkpoint: completed, all six questions attributed, three initial native concepts, 13.535 seconds for the retry.
- Static checks and patch formatting passed.

The live check used only handwritten synthetic content and disposable records. Automatic approval review rejected replaying the saved student outline to the external provider, so that replay was not performed. The student's original request and checkpoint were left unchanged. The synthetic success does not prove that the exact retained outline succeeds, and no production latency guarantee is claimed.
