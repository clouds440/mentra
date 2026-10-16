"""Lossless removal of unused batch metadata; shared data precedes variable data."""


def other_question_overview(plan: list[dict], offset: int, count: int) -> list[dict]:
    return [dict(number=item.get('number', index + 1), question_type=item['question_type'],
                 brief=item.get('brief', '')[:200])
            for index, item in enumerate(plan) if not offset <= index < offset + count]


def other_original_overview(questions: list[dict], offset: int, count: int) -> list[dict]:
    return [dict(number=index + 1, excerpt=item['prompt'][:160], truncated=len(item['prompt']) > 160)
            for index, item in enumerate(questions) if not offset <= index < offset + count]


def generation_payload(*, shared: dict, plan: list[dict], offset: int, batch_size: int,
                       prior: list, revision: dict | None = None) -> dict:
    batch = plan[offset:offset + batch_size]
    # Identical serialized shared prefix across concurrent batches. Do not sort:
    # caller places request/learner/source data before changing batch metadata.
    payload = {key: value for key, value in shared.items() if value is not None}
    overview = other_question_overview(plan, offset, len(batch))
    if overview:
        payload['assessment_overview'] = overview
    if revision:
        overview = other_original_overview(revision['questions'], offset, len(batch))
        if overview:
            payload['original_overview'] = overview
    payload.update(question_plan=batch, count=len(batch), question_offset=offset)
    if prior:
        payload['previous_prompts'] = [question.prompt[:250] for question in prior]
    if revision:
        payload['original_questions'] = [{key: question.get(key, []) if key == 'options' else question[key]
            for key in ('prompt', 'marks', 'difficulty', 'concept_ids', 'options')}
            for question in revision['questions'][offset:offset + len(batch)]]
    return payload
