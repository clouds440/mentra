"""Plan at most two complete grading packets without trimming student work."""
from app.assessments.schemas import GradedAssessment
from app.core.config import settings
from app.core.exceptions import AppError
from .llm import MentraLLM
from .prompts import PromptSource
from .token_policy import check_input, output_budget
from math import ceil


def grading_output_tokens(config, questions):
    expected = 120 + sum(230 + 50 * len(q['concept_ids']) for q in questions)
    maximum = output_budget(PromptSource.ASSESSMENT_GRADING, config)
    return min(maximum, max(512, ceil(expected / .85)))


def grading_payload(assessment, attempt, questions):
    # Source receipts and generation metadata are irrelevant to scoring. Keep the
    # complete prompt, context, key, rubric and answer; never shorten their text.
    fields = ('id', 'prompt', 'context', 'model_answer', 'rubric', 'marks',
              'concept_ids', 'question_type', 'number', 'part', 'section')
    payload = dict(questions=[{key: q[key] for key in fields if key in q} for q in questions],
        answers={q['id']: attempt['answers'][q['id']] for q in questions},
        result_style=assessment.get('preferences', {}).get('result_style', 'marks'),
        transcription_confirmed=attempt.get('extraction') is not None)
    lineage = assessment.get('practice_lineage') or {}
    if lineage.get('reference_questions'):
        contexts, references = {}, []
        for q in lineage['reference_questions']:
            reference = {key:q[key] for key in ('prompt','number','part','section','options') if key in q}
            if q.get('context'):
                context_id = contexts.setdefault(q['context'], f'C{len(contexts)+1}')
                reference['context_ref'] = context_id
            references.append(reference)
        payload['original_paper_reference'] = dict(instructions=lineage.get('instructions', ''),
            contexts={value:key for key,value in contexts.items()}, questions=references,
            usage='Reference only; context_ref points to shared contexts. Grade only the questions with submitted answers.')
    return payload


def plan_grading_batches(llm, assessment, attempt, questions):
    if not questions:
        return []
    config = getattr(getattr(llm, 'model_factory', None), '_settings', settings)
    reserve = output_budget(PromptSource.ASSESSMENT_GRADING, config)

    def fits(batch):
        # Includes JSON/IDs, concise feedback and exact multi-concept attribution.
        expected_output = 120 + sum(230 + 50 * len(q['concept_ids']) for q in batch)
        if expected_output > reserve * .9:
            return False
        packet_config = config.model_copy(update={'assessment_grading_output_tokens': grading_output_tokens(config, batch)})
        try:
            check_input(MentraLLM.messages(llm, PromptSource.ASSESSMENT_GRADING,
                grading_payload(assessment, attempt, batch)), PromptSource.ASSESSMENT_GRADING,
                tools=[GradedAssessment], config=packet_config)
        except AppError as error:
            if error.code != 'AI_CONTEXT_LIMIT':
                raise
            return False
        return True

    if fits(questions):
        return [questions]
    # Try balanced partitions first; full payload checks account for long answers
    # and shared contexts, rather than assuming question count equals token cost.
    weights = [len(str(grading_payload(assessment, attempt, [q]))) for q in questions]
    total, prefix, candidates = sum(weights), 0, []
    for cut in range(1, len(questions)):
        prefix += weights[cut - 1]
        candidates.append((abs(total - 2 * prefix), cut))
    for _, cut in sorted(candidates):
        if fits(questions[:cut]) and fits(questions[cut:]):
            return [questions[:cut], questions[cut:]]
    raise AppError('AI_CONTEXT_LIMIT',
        'This submission is too large to evaluate in two requests. Shorten the answers or use a larger model context.', 422)
