# Mentra: remaining product recommendations

**Research:** 17 October 2026 · **Updated:** 18 October 2026

This is the remaining-work plan. Finished implementation items have been removed. The original research and initial recommendations remain in Git history at `8ce7091`.

## Priorities

| Priority | Remaining recommendation | Expected value | Estimated focused effort | Key dependency |
| --- | --- | --- | --- | --- |
| Parallel · Q1 | Tutoring-quality benchmark and learner pilot | High: validate educational quality and adoption | 2–3 days initial, then bounded pilot | Reviewed synthetic/permissioned cases and a baseline |

Effort ranges are planning judgments for one engineer familiar with Mentra, including focused checks. They are not delivery promises or measured ROI. Recheck current code before starting; preserve existing screen positions and domain ownership.

### Q1 — Quality and complete-journey measurements

Mentra already has regression tests, timing traces and dated verification reports. Extend that infrastructure with a small repeatable product-quality corpus rather than building a separate observability system. [C6]

Start with approximately 30–50 synthetic or permissioned cases: objective correctness, written grading agreement, ambiguous source support, unanswerable questions, cited passage accuracy, conflicting concept labels, assisted vs independent attempts, long documents, and multilingual/mixed-language usage. Include English, Urdu and a third script as regression examples while retaining support for other languages.

Have a qualified reviewer validate the subject-matter cases before treating them as a gold set. Record model/prompt/configuration, rubric version and latency. Keep deterministic contract checks separate from model-quality checks; a schema-valid answer can still be wrong.

**Release rule:** no unresolved high-impact wrong-answer, cross-owner, answer-key exposure or evidence-attribution failures in the candidate set. Compare the remaining quality results with a recorded baseline; agree thresholds after that baseline exists. Measure end-to-end visible response time and completed job time, not just provider latency. Do not reduce evidence or change the canonical publication model merely to improve a timing number.

## Delivery and acceptance

| Step | Concrete outcome | Required evidence |
| --- | --- | --- |
| Q1 baseline | Reviewed corpus and complete study-journey measurements | Keep deterministic persistence checks, live provider quality and user observations separate |

Use disposable test databases. Do not use student accounts as fixtures. No UI or orchestration component may write learner tables directly. Assessments owns questions/attempts/private keys; Learner owns evidence/mastery; Chat owns canonical transcripts; RAG owns source authorization and immutable source identity.

## Product validation still needed

The learning mechanism is supported by research; Mentra-specific adoption and learning gains remain unmeasured. Practice testing/distributed practice have broad evidence [S1]; classroom retrieval research also has population limitations [S2]. Measure distinct, unassisted follow-up performance rather than interpreting answer-assisted success as mastery [S3].

Observe approximately 5–8 representative learners, including mobile, multilingual and larger-Library use. A small pilot can reveal friction; it cannot establish a learning-effect size.

| Question | Measure | Guardrail |
| --- | --- | --- |
| Do learners move from materials into useful practice? | Ready material → started/completed grounded attempt; time to first meaningful action | Source support, abandonment and model cost per completion |
| Do learners revisit feedback productively? | Results → follow-up started/completed; later distinct-item correctness | Record answer exposure/repeats; preserve independent-evidence policy |
| Do short reviews reduce decision effort? | View → start → completion; return for another review | No automatic evidence or unsupported overdue claims |
| Can learners verify and retrieve information? | Time/success finding support or an old exchange | No wrong-version source or private snippet leakage |
| Does quality hold? | Reviewer agreement, independent follow-up results and p50/p95 visible wait | Consider quality, cost and completion together |

Collect only needed metadata such as origin, pseudonymous session/owner ID, job/attempt ID, counts, duration and outcome. Avoid analytics containing answers, prompts, document text or search strings. Define access and retention before adding telemetry; reuse existing timing traces where possible.

Record baseline rates before setting product success thresholds. At low traffic, report counts and observed failures instead of unstable percentages. For learning gains, use distinct matched follow-up items after a delay and a suitable comparison; raw score changes across easier/harder generated quizzes are insufficient.

## Maintenance and product decisions remaining

| Item | Bounded next step |
| --- | --- |
| Written-work save clarity | Explain saved/unsaved status and consider a leave warning. Interactive quiz choices intentionally remain local until final submission; persistent MCQ drafts or per-question writes require a separate product decision |
| Readable job states | Replace exposed raw assessment/event state names with shared learner-facing labels; keep exact codes in diagnostics |
| Long-term capacity | Assessment creation has a 200-record guard and attempts a 20-attempt guard. Define a capacity policy that preserves important attempts/evidence before promoting habitual review to heavy users |
| Calendar compatibility | Manually import synthetic timed/all-day exports into two real calendar clients; automated serialization and browser-download checks do not establish every client's behavior |
| Live provider quality | Run bounded subject-reviewed grounded/exact-target examples against the configured provider; fixture-based generation does not establish real model quality |

## Later ideas, gated by evidence or scope decisions

| Idea | Why it remains later | Revisit when |
| --- | --- | --- |
| Hint-first guided practice | Roughly 4–7 days plus evaluation; hints/reveals need server-recorded assistance and a distinct independent follow-up | Quality cases cover answer leakage and learners repeatedly seek guided help |
| Exam preparation planning | Link an owned exam to context/materials, then validate workload and available study days; scheduling/adaptation is a separate project | Learners use events and reviews together and want an explicit plan |
| Full flashcards/FSRS/imports | Adds authoring/editing, scheduling, exposure/self-rating and another evidence path | A repeated memorization need is underserved by existing assessments |
| AI audio/video | Generation, playback, accessibility and verification add cost; bundled multimodal studies do not isolate the best format | Repeated demand and a representative learning-quality benchmark justify it |
| Autonomous study agent | More writes/model calls and harder recovery/evaluation | Manually initiated workflows are proven and automation boundaries are clear |
| Social sharing/leaderboards | Adds permissions, moderation and collaboration scope | Explicit demand and a privacy model exist |
| Streaks/badges | Visits do not establish learning; avoid coercive recovery or fabricated mastery | Reward completed learning effort in an established review habit |
| Calendar OAuth/two-way sync | Adds token lifecycle, conflicts, quotas and external writes | Sustained demand demonstrates snapshot export is insufficient |
| Push/offline application | Adds service workers, delivery/subscriptions, offline conflicts and model/attachment behavior | Closed-app delivery/offline needs are demonstrated |
| Replace OCR/embeddings | Accuracy depends on workload; changing models is not itself an improvement | A reproducible quality benchmark identifies a better tested option |

## Sources for remaining work

| Reference | Primary source / code |
| --- | --- |
| C6 | [Assessment engine](Assessment_Engine.md), [latency evidence](Response_Latency_Fixes.md), [backend atlas](Mentra_Backend_Map.md) |
| S1 | [Dunlosky et al., 2013][S1] |
| S2 | [Agarwal et al., 2021][S2] |
| S3 | [Bastani et al., PNAS, 2025][S3] |

[S1]: https://www.psychologicalscience.org/journals/pspi/1529100612453266/
[S2]: https://remix.berklee.edu/faculty-works/12/
[S3]: https://doi.org/10.1073/pnas.2422633122
