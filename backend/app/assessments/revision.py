"""Reuse immutable accepted items and structure for compatible content edits."""
from app.core.exceptions import AppError
from .blueprint import question_reference
from .schemas import GeneratedQuestion, PaperInfo
import re


def revision_sources(original, fresh):
    """Keep existing token identities; fresh retrieval must not relabel old items."""
    from copy import deepcopy
    sources=deepcopy(original)
    identity=lambda source: tuple(str(source.get(key,'')) for key in ('document_id','version_id','generation_id','chunk_id','excerpt'))
    known={identity(source) for source in sources}
    used={source['token'] for source in sources}
    for value in fresh:
        if identity(value) in known:
            continue
        source=deepcopy(value)
        index=1
        while f'S{index}' in used: index+=1
        source['token']=f'S{index}'
        sources.append(source);used.add(source['token']);known.add(identity(source))
    return sources


def reusable_revision(request, original):
    if not original or original.get('mistake_revision'):
        return None
    questions = original['questions']
    paper = original.get('paper')
    count = paper['question_count'] if paper else len(questions)
    kinds = {question.get('question_type') or ('mcq' if question.get('options') else 'written') for question in questions}
    same_format = request.question_format == ('mock_paper' if paper else next(iter(kinds)) if len(kinds) == 1 else 'mixed')
    structural = bool(re.search(r'\b(?:add|remove|delete|insert|split|merge)\b.*\b(?:questions?|parts?|sections?)\b|\b(?:change|switch|convert)\b.*\b(?:format|type|marks|duration)\b', request.revision_instructions, re.I))
    compatible = (not structural and request.count == count and same_format and not request.paper_sections and not request.question_formats
                  and (request.total_marks is None or paper and request.total_marks == paper['total_marks'])
                  and (request.duration_minutes is None or paper and request.duration_minutes == paper['duration_minutes'])
                  and request.level == original.get('preferences', {}).get('level'))
    if not compatible:
        if request.revision_question_numbers:
            raise AppError('ASSESSMENT_REVISION_SCOPE', 'Change question content separately from assessment structure or length.', 422)
        return None
    # Private keys stay inside the service. If a historical payload cannot be
    # reconstructed safely, use the full validated generation path instead.
    try:
        retained = [GeneratedQuestion.model_validate({key:value for key,value in question.items()
                    if key in GeneratedQuestion.model_fields}) for question in questions]
    except ValueError:
        if request.revision_question_numbers:
            raise AppError('ASSESSMENT_REVISION_SOURCE', 'The original grading data is unavailable for a partial revision.', 409) from None
        return None
    references = [question_reference(question,index) for index,question in enumerate(questions,1)]
    selected = set(request.revision_question_numbers or references)
    if selected - set(references):
        raise AppError('ASSESSMENT_QUESTION_NOT_FOUND', 'Choose question references from the original assessment.', 422)
    positions = [index for index,reference in enumerate(references) if reference in selected]
    plan = [{key:getattr(retained[index],key) for key in
             ('question_type','answer_mode','context','section','number','part','marks')} for index in positions]
    return dict(retained=retained, positions=positions, plan=plan,
                paper=PaperInfo.model_validate(paper) if paper else None,
                original=dict(original, questions=[questions[index] for index in positions]))
