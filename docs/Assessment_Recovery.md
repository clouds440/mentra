# Assessment failure recovery

The reported React assessment failure was traced in API container logs under trace `e94fb88279934cd6832b46774583e377`. At 16:51:05 UTC on October 14 the generation tool successfully queued work. At 16:51:06 chat response assembly raised `KeyError` in `ChatResponse.latest_assessment_cards`, which assumed every card already contained `assessment.id`. Queued cards instead carry `generation_job_id`. Deduplication now handles both shapes in separate namespaces, with a regression test through actual response validation.

Evaluation logs for trace `47a192f21c764fccb4d91084076ad0a1` showed successful provider responses followed by repeated `grade_marks_and_concept_ids_must_match_question` repairs and a failed attempt after three runs. The evaluation path now binds concept attribution and maxima to the saved question. Unknown question IDs and ambiguous invalid scores still fail safely. Missing multi-concept attribution stays low confidence, preventing unjustified learner evidence. No private student answers were replayed to the provider for this diagnosis.

The previous UI used a new-attempt action for failed evaluations. Evaluation retry now uses the existing retry endpoint and preserves the attempt ID and submitted answers. New attempts remain a separate explicit action after results. Results and review use shared answer panels; default results navigation shows one colored question at a time with an optional list view.

The previous React jobs produced 25/26 answerable items. With the old three-item sequential batches, 26 items required nine content requests in addition to planning. New generation is capped at 20, prefers a representative 6–10 item mix when length is unspecified, and requests the whole quiz in one call when it fits. Larger work uses two concurrent bounded batches with ordered checkpoints and duplicate validation.

Validation includes server-side response packaging, concept/scale alignment, preservation of submitted answers, generation call counts and concurrency, grading/evidence/ownership regressions, and browser coverage of evaluation retry and both result views. Synthetic tests use an isolated PostgreSQL database. Production asset serving and container startup are checked after rebuild.

A synthetic live-provider call generated ten mixed React-state questions in one content request in 13.99 seconds. This measures content generation only, excludes planning, and did not contain real learner answers. The local verification runs passed 59 core recovery/assessment checks, the remaining evidence/topic/ownership checks after updating two obsolete fixed-batch assertions, eight assessment browser checks and nine existing quiz checks after updating the renamed new-attempt action.

[Mobile results example](assessment-engine/assessment-results-mobile.png)
