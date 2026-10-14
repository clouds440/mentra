"""Deterministic question/part and marks plans; AI supplies educational content."""
from app.core.exceptions import AppError
from .schemas import PaperInfo

def balance_outline_marks(sections, total):
    """Balance AI outline weights before writing content, preserving every part.

    Explicit caller-owned plans bypass this function and retain their marks.
    """
    if total is None: return
    from decimal import Decimal, ROUND_FLOOR
    parts = [part for section in sections for question in section.questions for part in question.parts]
    if not parts: return
    wanted = Decimal(str(total))
    weights = [Decimal(str(part.marks)) for part in parts]
    if sum(weights) == wanted: return
    quantum = Decimal(1) if wanted == wanted.to_integral_value() and wanted >= len(parts) else Decimal(1).scaleb(min(-2, wanted.as_tuple().exponent))
    while wanted/quantum < len(parts): quantum /= 10
    available = int(wanted/quantum)-len(parts)
    quotas = [Decimal(available)*weight/sum(weights) for weight in weights]
    allocation = [int(quota.to_integral_value(rounding=ROUND_FLOOR)) for quota in quotas]
    remainder = available-sum(allocation)
    for index in sorted(range(len(parts)), key=lambda i: quotas[i]-allocation[i], reverse=True)[:remainder]:
        allocation[index] += 1
    for part, value in zip(parts, allocation): part.marks = float((value+1)*quantum)


def part_letter(index):
    result = ''
    value = index+1
    while value:
        value, remainder = divmod(value-1,26)
        result = chr(97+remainder) + result
    return result

def flatten_sections(request, sections, duration=None, instructions=None):
    """One immutable grading item per leaf; paper references remain independent IDs."""
    # Expanding shorthand must not alter the caller's request/replay fingerprint.
    sections = [section.model_copy(deep=True) for section in sections]
    from app.langchain.generation_recovery import GenerationMismatch
    plan, numbers, references = [], set(), set()
    for section in sections:
        if not section.questions:
            from .schemas import PlannedQuestion, PlannedPart
            for _ in range(section.question_count):
                number = max(numbers, default=0) + len(section.questions) + 1
                section.questions.append(PlannedQuestion(number=number, parts=[PlannedPart(
                    path=[part_letter(i)] if len(section.part_marks)>1 else [], question_type=section.question_type,
                    answer_mode='single_choice' if section.question_type in ('mcq','true_false') else 'text', marks=mark)
                    for i, mark in enumerate(section.part_marks)]))
        section.question_count = len(section.questions)
        for question in section.questions:
            if question.number in numbers:
                raise GenerationMismatch('paper_question_numbers_must_be_unique')
            numbers.add(question.number)
            for part in question.parts:
                import re
                if any(not re.fullmatch(r'[A-Za-z0-9]+', label) for label in part.path):
                    raise GenerationMismatch('part_paths_require_letters_or_numbers')
                path = '.'.join(label.lower() for label in part.path) or None
                reference = question_reference(dict(number=question.number, part=path), question.number)
                if reference in references:
                    raise GenerationMismatch('paper_part_references_must_be_unique')
                references.add(reference)
                plan.append(dict(question_type=part.question_type, answer_mode=part.answer_mode,
                    section=section.title, number=question.number, part=path, marks=part.marks,
                    context='\n\n'.join(value for value in (question.context, part.context) if value), brief=part.brief))
    if request.question_format != 'mock_paper':
        # Ordinary mixed practice still uses all design decisions; exam chrome is optional.
        return plan, None
    paper = PaperInfo(duration_minutes=request.duration_minutes or duration,
        total_marks=sum(item['marks'] for item in plan), question_count=len(numbers),
        instructions=instructions or 'Answer all questions. Show your working where appropriate.', sections=sections)
    return plan, paper

def question_reference(question, index):
    value = question if isinstance(question, dict) else question.model_dump() if hasattr(question, 'model_dump') else vars(question)
    part = value.get('part') or ''
    return f"{value.get('number') or index}{'.' if part[:1].isdigit() else ''}{part}"


def normalize_reference(value):
    import re
    match = re.fullmatch(r'\s*(?:Q(?:uestion)?\s*)?(\d+)(.*)', str(value), re.I)
    if not match: return ''
    labels = re.findall(r'[a-z0-9]+', match.group(2).lower())
    part = '.'.join(labels)
    return match.group(1) + ('.' if part[:1].isdigit() else '') + part


def parse_numbered_answers(text):
    import re
    matches = list(re.finditer(r'(?m)^[ \t]*(?:Q(?:uestion)?[ \t]*)?(\d+(?:(?:[ \t]*\([A-Za-z0-9]+\))|(?:[A-Za-z]+)|(?:\.[A-Za-z0-9]+))*)[.):]?(?:[ \t]+|\n)', text, re.I))
    return [(normalize_reference(match.group(1)),
             text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip())
            for i, match in enumerate(matches)]


def blueprint(request):
    """Expand an explicit request. Unspecified/mixed papers use the LLM designer."""
    if request.paper_sections:
        plan, paper = flatten_sections(request, request.paper_sections)
        if request.total_marks is not None and abs(sum(item['marks'] for item in plan) - request.total_marks) > .001:
            raise AppError('ASSESSMENT_PAPER_MARKS', 'Section and part marks must add up to the requested total.', 422)
        return plan, paper
    if request.count is None or request.question_format in ('mixed','mock_paper'):
        raise AppError('ASSESSMENT_DESIGN_REQUIRED', 'Let the assessment designer choose this structure.', 422)
    mode = 'multiple_choice' if request.question_format == 'multiple_select' else 'single_choice' if request.question_format in ('mcq','true_false') else 'text'
    return [dict(question_type=request.question_format, answer_mode=mode,
        **({'marks': request.total_marks/request.count} if request.total_marks is not None else {})) for _ in range(request.count)], None
