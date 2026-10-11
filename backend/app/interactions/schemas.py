"""General selection contracts shared by chat, assessments and future producers."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.exceptions import AppError

class ChoiceOption(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')
    label: str = Field(min_length=1, max_length=300)

class ChoiceContent(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['single_choice', 'multiple_choice']
    question: str = Field(min_length=1, max_length=1000)
    options: list[ChoiceOption] = Field(min_length=2, max_length=10)
    @model_validator(mode='after')
    def unique(self):
        if len({x.id for x in self.options}) != len(self.options):
            raise ValueError('Option identifiers must be unique.')
        maximum = sum(len(x.id) + len(x.label) + 4 for x in self.options) if self.kind == 'multiple_choice' else max(len(x.id) + len(x.label) + 4 for x in self.options)
        if len(self.question) + maximum + 12 > 4000:
            raise ValueError('Shorten this interaction to fit a conversation response.')
        return self

def selected_options(options, kind, selected):
    """Validate identifiers and cardinality; return server options in display order."""
    if not selected or len(set(selected)) != len(selected) or set(selected)-{x.id for x in options} or (kind == 'single_choice' and len(selected) != 1):
        raise AppError('INTERACTION_INVALID_ANSWER', 'Choose valid options for this question.', 422)
    return [x for x in options if x.id in selected]

def canonical_option_id(options, answer):
    """Resolve a verbatim typed/OCR option ID or exact label without guessing."""
    text = answer.strip()
    exact = [x.id for x in options if x.id == text]
    if len(exact) == 1: return exact[0]
    token = text.rstrip('.)').strip().casefold()
    matches = {x.id for x in options if x.id.casefold() == token or x.label.casefold() == text.casefold()}
    if len(matches) != 1:
        raise AppError('ASSESSMENT_INVALID_ANSWER', 'Choose an unambiguous option ID or exact option label.', 422)
    return next(iter(matches))
