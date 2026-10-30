# Grouped conversational questions — October 28, 2026

Related in-chat questions now use a single questionnaire, with one submission for
the complete answer set. It reuses assessment question navigation, progress,
choices and fields while keeping chat input separate from assessment persistence
and grading. Existing multi-card responses receive the same grouped controls.

| Original gap | Correction |
| --- | --- |
| Only two choices were displayed | Native presentation consumed the two-write allowance. Presentation now has its own bounded allowance; domain writes keep their original limits. |
| Additional questions could still disappear | The old three-card ceiling and lookup slots shared with profile preparation also constrained question display. Valid UI supports 20 cards, and related questions use one `present_questionnaire` call containing 1–20 questions. |
| Several separate Send buttons | One shared question navigator and one Submit all answers action collect the whole set. Single/multiple choices, custom option text and short/long text can be mixed. |
| Only one answer reached the model | One owned chat transaction validates all question IDs, selected options and fields, builds canonical content from server labels, and marks the complete set submitted together. |
| Older cards still needed separate submissions | `additional_responses` submits pending sibling cards from the same assistant message in one transaction. Previously submitted cards stay read-only. |
| Recovery could duplicate or change answers | Existing operation IDs, exact pending payloads, owner/conversation locking and legacy fingerprint order are preserved. Old checkpoints regain currently available common controls; presentation counts survive new checkpoints. |

No database migration or assessment/attempt is needed. These answers become one
canonical user message, visible to the next response. Choosing preferences or
submitting an informal questionnaire does not itself establish mastery.

The schema retains existing per-question option/field validation rather than
silently trimming content. Questionnaires permit up to 20 questions, each choice
question up to 10 options, and a complete canonical answer summary up to 16,000
characters. Model/time budgets remain bounded. Presentation receipts can compact
without discarding validated question metadata. Missing/invalid/foreign/duplicate
answers reject the complete submission with no partial update.

| Verification | Result |
| --- | --- |
| Backend interaction/routing/recovery suite | 99 passed in 21.756 seconds on the host and 23.372 seconds under the rebuilt image's Python 3.12 runtime. Counts overlap; they are not 198 unique tests. |
| Persistence checks | Five mixed questions, custom text, multiple selections, canonical labels, zero assessment/evidence rows, rollback on invalid answers, concurrent submission fencing and duplicate replay. Twenty-question metadata preserves every option. |
| Browser acceptance | Nine passed in 1.7 minutes: desktop/mobile five-question submission, selection retention through navigation, one request for all answers, reload of accepted selections, legacy five-card batch, existing inputs and actual assessment grading. |
| Configured model | [Synthetic English/Urdu evidence](../verification/chat-questionnaire-provider-verification.json): both cases returned all five questions and all four options in one questionnaire, without assessment services. |
| Frontend/static | TypeScript/Vite production image build, theme/UI checks, targeted Ruff and whitespace checks passed. The existing large-bundle advisory remains. |

Backend images reuse the previously verified dependency/model layers and copy the
current application/scripts; no dependency change is part of this release. The
frontend is rebuilt from source. Update backend, workers and frontend together.
Keep learner data, application logs and prior release images; remove this task's
disposable PostgreSQL container, browser artifacts and scratch build/test files.
See [native interaction contracts](../chat-interactions.md) for payloads and limits.
