from ..schemas import CalibrationAttempt, EvidenceInput, EvidenceItem, CalibrationView, PublicQuestion


def public_attempt(attempt: CalibrationAttempt) -> CalibrationView:
    return CalibrationView(id=attempt.id, blueprint_version=attempt.blueprint_version,
        questions=[PublicQuestion.model_validate(item.model_dump(include={'id', 'prompt', 'kind', 'options'})) for item in attempt.questions],
        answers=attempt.answers, status=attempt.status, version=attempt.version)


def score(attempt: CalibrationAttempt, now) -> EvidenceInput:
    if set(attempt.answers) != {item.id for item in attempt.questions}:
        raise ValueError('All calibration questions must be answered')
    items = []
    for question in attempt.questions:
        choice = next((option for option in question.options if option.id == attempt.answers[question.id]), None)
        if choice is None:
            raise ValueError('Invalid answer choice')
        items.append(EvidenceItem(id=question.id, dimension=question.dimension, prompt=question.prompt,
            difficulty=question.difficulty, correct=choice.id == question.correct_option_id, selected_option=choice.text))
    return EvidenceInput(source_type='onboarding_calibration', source_id=attempt.id,
                         occurred_at=now, items=items)
