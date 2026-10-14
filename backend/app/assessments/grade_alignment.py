"""Bind model evaluation to server-owned question maxima and canonical concepts."""
from .schemas import ConceptGrade
from app.langchain.generation_recovery import GenerationMismatch


def align_grades(result, questions):
    expected = {question['id']: question for question in questions}
    if len(result.questions) != len(expected) or {grade.question_id for grade in result.questions} != set(expected):
        raise GenerationMismatch('grade_question_ids_must_match_batch')
    for grade in result.questions:
        question = expected[grade.question_id]
        maximum = question['marks']
        if maximum < grade.score <= maximum+1e-6: grade.score=maximum
        if grade.score > maximum:
            scales = {value.max_score for value in grade.concept_grades.values()}
            if len(scales) != 1 or next(iter(scales)) < grade.score:
                raise GenerationMismatch('overall_score_exceeds_question_maximum')
            grade.score = maximum if grade.score==next(iter(scales)) else min(maximum, round(grade.score / next(iter(scales)) * maximum,8))
        aligned = {}
        for identifier in question['concept_ids']:
            detail = grade.concept_grades.get(identifier)
            if detail:
                aligned[identifier] = ConceptGrade(score=maximum if detail.score==detail.max_score else min(maximum,round(detail.score/detail.max_score*maximum,8)),
                    max_score=maximum, confidence=min(detail.confidence, grade.confidence))
            else:
                # A single concept is unambiguous. Missing multi-concept attribution
                # stays low confidence so it cannot manufacture reliable mastery.
                aligned[identifier] = ConceptGrade(score=grade.score,max_score=maximum,
                    confidence=grade.confidence if len(question['concept_ids'])==1 else min(.4,grade.confidence))
        grade.concept_grades = aligned
    return result
