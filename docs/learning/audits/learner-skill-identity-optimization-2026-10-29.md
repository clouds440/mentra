# Learner skill identity and assessment optimization

## What the latest Arabic quiz showed

The inspected quiz had one broader Arabic topic and 14 stored skill memberships, including staged skills. Some questions repeated that same topic heading up to four times. The labels also contained probable overlaps: a long description of reading short-vowel marks alongside a second “Harakat…” skill, for example. Different wording alone is not sufficient grounds to merge graded identities.

The shared assessment component now renders each topic once per question with its subskills underneath. Repeated skill IDs within the question are displayed once. Existing assessment wording, IDs, attempts, evidence and scores are preserved.

## What the names mean internally

| Record | Purpose |
| --- | --- |
| Learning context | The student's subject/study area and ownership boundary. |
| Learning topic | The recognizable broader heading shown to the student. |
| Canonical concept | The stable identity of an assessable leaf skill; “subskill” in the grouped UI. |
| Topic membership | Connects that stable skill to its broader topic and human-readable label/ability. |
| Accepted resolution binding | An indexed mapping from owner + context + normalized subject + normalized incoming label to the already accepted skill/topic IDs. It creates no mastery evidence. |
| Evidence and learner state | Observations and derived estimates attached to the stable skill ID. Topic membership itself is not mastery. |

## How generation and acceptance work now

| Stage | Behavior and authority |
| --- | --- |
| Choose practice targets | Use bounded relevant learner data or supplied exact targets. The generator receives selected targets, not the student's entire registry. |
| Produce questions | Prefer supplied skill IDs. For a genuinely missing skill, return a concise reusable name. One diagnostic skill is usual; multiple skills require independently supported rubric components. There is no fixed topic catalog or required child count. |
| Accept existing IDs | A valid supplied target ID is authoritative attribution. Extra prose labels no longer create parallel identities alongside it. Unknown opaque IDs cannot invent a match. |
| Resolve new labels | Preserve an explicit input-label-to-ID map for the whole batch. Renaming, translation, reordering and synonymous labels no longer cause a batch lookup followed by separate lookup/repair requests for each label. |
| Reuse an exact accepted label | First consult the subject-scoped binding under the current owned context and active membership. Exact repeats need no organizer model call or registry-wide version scan. Unrelated subjects/owners do not share these bindings. |
| Resolve a new paraphrase/translation | Send a bounded candidate shortlist to the organizer. It chooses `reuse`, `add_subskill`, a genuinely new topic, or deferral. Only supplied owned IDs are accepted; existing membership cannot be silently reparented. A learned synonym is retained for future exact reuse. |
| Recover a missing candidate | One bounded wider lookup can use up to six model-proposed synonym/translation search phrases. Wider lookup actually expands children, not only parent count. Truncation is explicit; absence from a truncated packet is not proof of novelty. |
| Persist | Server transactions, owner/context foreign keys and conflict checks validate the decision. A learned alias cannot silently switch skill identity. New skills remain staged until publication; naming a skill creates no learning observation. |
| Evaluate | Choices use stable option IDs and deterministic scoring. Written responses use the complete question, rubric, key, answer and relevant skill IDs. Grading does not require the whole topic hierarchy or repeated display labels. |
| Update learning | The evidence worker records observations against those same canonical IDs. A real later attempt can strengthen or weaken the estimate according to its result, confidence and assistance. Replaying the same evidence is idempotent; merely recognizing a synonym never raises mastery. |

## Gaps found and fixed

| Before | After |
| --- | --- |
| A question could return valid known IDs plus paraphrased names, creating extra skills after generation. | Reuse the verified IDs and discard redundant name attribution. |
| A renamed/combined batch result lost the connection to each original input label. The caller then issued individual resolver requests. | Explicit batch bindings retain every original label's resulting ID, including many labels resolving to one skill. |
| The exact-label shortcut required request-title words to occur in the topic name/scope. Changed titles triggered repeated semantic work. | Accepted subject/label bindings are retained directly. |
| Word overlap could incorrectly establish identity: “integration” also matched a scope saying “excludes integration.” | Word overlap no longer proves identity. A different subject needs an accepted binding or semantic advice. |
| Only five children were visible per parent; the wider pass still exposed just five. | Normal lookup returns up to five relevant children per parent, wider lookup up to twelve, with a global 96-child packet ceiling and real provider-budget admission. Storage and pagination have no such child-count cap. |
| Long scope/ability descriptions inflated model context, and the model repeated them when reusing a skill. | Compact candidate descriptions; ID-only reuse output. The server retains and supplies the full stored descriptions. Oversized packets shrink before model invocation and mark omissions. |
| Repeated coverage labels cluttered each question. | One heading per topic, all relevant children listed below it. Native-script labels use automatic direction. |

## Cost and latency boundaries

- A five-label batch previously could cause one batch request plus up to five individual resolver requests; whether each reached the model depended on the old alias shortcut. The default production organizer path now returns the complete mapping in the batch.
- An exact accepted repeat uses zero organizer model calls. A valid known-ID question uses zero additional name-resolution calls. A new semantic meaning can still require an organizer call, a bounded wider lookup, or bounded invalid-output repair.
- Normal candidate discovery selects at most 12 topics; the wider pass at most 24. The packet also obeys actual input/output/schema budgets. A 1,000-skill registry is not a 1,000-skill prompt.
- Existing chat assessment references are already lightweight, and grading already omits display-only hierarchy metadata. Historical label snapshots remain for reliable review; this does not mean they are resent to the model on every turn.
- This is not a promise that semantic duplicates are mathematically impossible. Uncertain identity should be reviewed rather than merged based on spelling or broad similarity. An existing topic/skill is reused only when evidence supports the same assessable meaning.

## Existing records and remaining work

No historical concepts, skills, assessments or evidence were deleted or merged. The 14 existing Arabic memberships include overlaps worth reviewing, but a broad skill and a narrower independently assessed skill are not automatically duplicates. A future reviewed consolidation must use canonical redirects, preserve attempts/provenance and reconcile evidence idempotently; deleting rows or adding historical mastery together is unsafe.

Failed-generation staging is another maintenance concern: unpublished targets can remain even if no question eventually uses them. They stay outside published progress. A later cleanup must check retained generation checkpoints, live jobs, drafts, assessments and evidence before retiring true orphans. It must not delete canonical identities or affect paused work merely because a row is old.

## Verification

The final focused regression group passed **74 tests**. Desktop/mobile coverage checks passed **2 browser tests**. The candidate migration also passed on a populated local restore, preserving the checked canonical concept, membership, evidence, learner-state, assessment and attempt row counts. The additive table does not rewrite those records.

Completed focused checks cover topic grouping, label reordering/renaming, owner/context isolation, immutable aliases, compact reuse, actual input budgets, synonym-assisted wider lookup, multilingual assessment generation and grading. The synthetic 1,000-skill check returned only five normal or twelve wider children for its relevant topic, retained the wanted match, and repeated an accepted skill without a model call or registry scan.

Configured-provider checks used handwritten synthetic labels and disposable records only: the initial label took one model call, its Arabic translation took one, and repeating that accepted translation took zero. All mapped to one canonical skill; no mastery evidence was created. A separate live reuse check returned only `label`, `action`, `skill_id` and `topic_id`, repeating zero characters of the topic name/scope.

Desktop/mobile browser checks passed with one topic heading, both child skills visible, and unchanged typed/multiple-choice answer submission. The frontend production build and fatal static checks passed. Test groups overlap; do not sum their counts as unique coverage or treat synthetic timings as a production p95 claim.
