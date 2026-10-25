"""Versioned score policy; question accuracy and rubric feedback remain unchanged."""
from decimal import Decimal, ROUND_HALF_UP


def summarize_score(grades, questions, reported_assistance):
    raw = sum((Decimal(str(grade.score)) for grade in grades.questions), Decimal(0))
    maximum = sum((Decimal(str(question['marks'])) for question in questions), Decimal(0))
    multiplier = Decimal('0.9') if reported_assistance == 'assisted' else Decimal('1')
    def number(value):
        return float(value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP))
    return dict(raw_score=number(raw), adjusted_score=number(raw * multiplier), max_score=number(maximum),
                multiplier=float(multiplier), reported_assistance=reported_assistance, policy='self-reported-assistance-v1')
