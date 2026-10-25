"""Deterministic, answer-free PDF rendering of an authorized public assessment."""
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from .blueprint import question_reference

_fonts = Lock()


def render_question_paper(assessment):
    # The renderer receives only the public DTO, never private grading keys.
    with _fonts:
        if 'MentraPaper' not in pdfmetrics.getRegisteredFontNames():
            fonts = Path(reportlab.__file__).parent / 'fonts'
            pdfmetrics.registerFont(TTFont('MentraPaper', str(fonts / 'Vera.ttf')))
    body = ParagraphStyle('body', fontName='MentraPaper', fontSize=10, leading=16,
                          textColor=colors.HexColor('#253047'), spaceAfter=8, splitLongWords=True)
    title = ParagraphStyle('title', parent=body, fontSize=19, leading=25, spaceAfter=14)
    heading = ParagraphStyle('heading', parent=body, fontSize=11, leading=17, spaceBefore=12, spaceAfter=8, keepWithNext=True)
    footer = ParagraphStyle('footer', parent=body, fontSize=8, alignment=TA_RIGHT)
    stream = BytesIO()
    document = SimpleDocTemplate(stream, pagesize=(210*mm, 297*mm), leftMargin=18*mm,
                                 rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm,
                                 title=assessment.title, author='Mentra')

    def paragraph(value, style=body):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)

    total = sum(question.marks for question in assessment.questions)
    story = [paragraph('MENTRA · QUESTION PAPER', heading), paragraph(assessment.title, title),
             paragraph(f'{len(assessment.questions)} questions / parts · {total:g} marks')]
    if assessment.paper and assessment.paper.duration_minutes:
        story.append(paragraph(f'Time allowed: {assessment.paper.duration_minutes} minutes'))
    instructions = ('Answer every numbered question or part. Show your working for written answers. '
                    'For multiple choice, write the option letter; for select-all questions, list all chosen letters. '
                    'Keep the question numbers and part labels below on your answer sheet. '
                    'Declare any AI or hint use when submitting; self-reported assistance applies a 0.9x final-score adjustment. '
                    'Upload a PDF, TXT, or PNG/JPEG answer sheet, review the extracted text, then submit for evaluation.')
    story += [paragraph('Instructions', heading), paragraph(instructions)]
    if assessment.paper and assessment.paper.instructions:
        story.append(paragraph(assessment.paper.instructions))
    last_section = None
    for index, question in enumerate(assessment.questions, 1):
        if question.section and question.section != last_section:
            story.append(paragraph(question.section, heading)); last_section = question.section
        label = question_reference(question.model_dump(mode='json'), index)
        story.extend([Spacer(1, 5*mm), paragraph(f'Question {label}   [{question.marks:g} marks]', heading)])
        if question.context:
            story.append(paragraph(question.context))
        story.append(paragraph(question.prompt))
        for position, option in enumerate(question.options or []):
            story.append(paragraph(f'{chr(65+position)}. {option.label}'))

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#cbd5e1'))
        canvas.line(18*mm, 16*mm, 192*mm, 16*mm)
        line = paragraph(f'Mentra · Page {doc.page}', footer)
        line.wrapOn(canvas, 174*mm, 10*mm); line.drawOn(canvas, 18*mm, 10*mm)
        canvas.restoreState()

    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return stream.getvalue()
