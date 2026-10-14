"""Canonical option mapping shared by validation, grading and handwritten review."""
import json
from app.interactions.schemas import canonical_option_id
from .schemas import MCQOption
from app.core.exceptions import AppError


def selected_options(question, answer):
    options = [MCQOption.model_validate(value) for value in question.get('options', [])]
    def canonical(value):
        try: return canonical_option_id(options, value)
        except AppError:
            token = value.strip().strip('().').upper()
            if len(token)==1 and 'A' <= token <= 'Z' and ord(token)-65 < len(options):
                return options[ord(token)-65].id
            raise
    if question.get('answer_mode') != 'multiple_choice':
        return [canonical(answer)]
    try:
        values = json.loads(answer)
    except (ValueError, TypeError):
        values = [value.strip() for value in answer.split(',')]
    if not isinstance(values, list) or not values or any(not isinstance(value, str) for value in values):
        raise AppError('ASSESSMENT_INVALID_ANSWER', 'Select one or more valid options.', 422)
    return sorted(set(canonical(value) for value in values))


def normalized_choice(question, answer):
    values = selected_options(question, answer)
    return json.dumps(values, separators=(',', ':')) if question.get('answer_mode') == 'multiple_choice' else values[0]
