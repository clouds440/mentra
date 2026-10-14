"""Request-led outlines, separate from content generation and grading keys."""
from app.assessments.schemas import AssessmentDesign, limit_sections
from app.assessments.blueprint import flatten_sections, balance_outline_marks
from .prompts import PromptSource
from .generation_recovery import invoke_generated, GenerationMismatch


async def design_assessment(llm, request, sources, profile, original=None, learner_context=None):
    def validate(result):
        result.sections = limit_sections(result.sections)
        if request.result_style != 'marks' and request.total_marks is None:
            for section in result.sections:
                if not section.questions: section.part_marks = [1 for _ in section.part_marks]
                for question in section.questions:
                    for part in question.parts: part.marks = 1
        balance_outline_marks(result.sections, request.total_marks)
        plan, paper = flatten_sections(request, result.sections, result.duration_minutes, result.instructions)
        if request.question_format not in ('mixed','mock_paper','written') and any(item['question_type'] != request.question_format for item in plan):
            raise GenerationMismatch('honor_the_explicitly_requested_question_format')
        if request.question_format == 'written' and any(item['answer_mode'] != 'text' for item in plan):
            raise GenerationMismatch('written_questions_require_text_responses')
        main_count = sum(section.question_count for section in result.sections)
        if request.count is not None and main_count != request.count:
            raise GenerationMismatch('main_question_count_must_match_request')
        if request.total_marks is not None and abs(sum(item['marks'] for item in plan) - request.total_marks) > .001:
            raise GenerationMismatch('paper_marks_must_match_requested_total')
    result = await invoke_generated(llm, PromptSource.ASSESSMENT_DESIGN,
        dict(topic=request.topic, instructions=request.instructions or request.revision_instructions,
             count=request.count, question_format=request.question_format, total_marks=request.total_marks,
             duration_minutes=request.duration_minutes, sources=sources, profile=profile,
             learner_context=learner_context, level=request.level, result_style=request.result_style,
             original_paper=original.get('paper') if original else None),
        output_schema=AssessmentDesign, validate=validate)
    return flatten_sections(request, result.sections, result.duration_minutes, result.instructions)
