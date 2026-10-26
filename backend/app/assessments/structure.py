"""Small practice has a deterministic outline; educational content stays generated."""
import re

SIMPLE_TYPES = {'mcq', 'true_false', 'short_answer', 'multiple_select', 'mixed'}


def small_practice(request) -> bool:
    return (request.count is not None and 1 <= request.count <= 3
            and request.question_format in SIMPLE_TYPES and request.purpose == 'practice'
            and not (request.paper_sections or request.question_formats or request.revision_instructions
                     or request.total_marks is not None or request.duration_minutes is not None)
            and len(request.instructions) <= 500
            and not re.search(r'\b(?:parts?|sections?|subquestions?|rubric|blueprint|outline|paper|marks?|points?|minutes?|duration|time limit)\b|حصے|حصوں|حصہ', request.instructions, re.I))


def small_blueprint(request):
    kinds = ['mcq', 'short_answer', 'true_false'] if request.question_format == 'mixed' else [request.question_format]
    return [dict(question_type=kinds[index % len(kinds)],
                 answer_mode='multiple_choice' if kinds[index % len(kinds)] == 'multiple_select'
                 else 'single_choice' if kinds[index % len(kinds)] in ('mcq', 'true_false') else 'text',
                 marks=1) for index in range(request.count)], None
