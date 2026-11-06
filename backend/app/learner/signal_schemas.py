"""Observed learning signals are source claims, never model-assigned mastery."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator


class LearningSignal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['encounter','struggle','self_report','guided_work','demonstration']
    label: str=Field(min_length=1,max_length=200)
    topic: str=Field(default='',max_length=200)
    concept_id: str|None=None
    context_id: str|None=None
    source_id: str=Field(default='user',min_length=1,max_length=100)
    quote: str=Field(min_length=1,max_length=1000)
    start: int|None=Field(default=None,ge=0)
    end: int|None=Field(default=None,ge=1)
    confidence: float=Field(ge=0,le=1)
    authorship: Literal['student','quoted','uncertain']='uncertain'
    assistance: Literal['observed_guidance','unknown']='unknown'
    task_quote: str=Field(default='',max_length=500)
    note: str=Field(default='',max_length=500)

    @field_validator('label')
    @classmethod
    def meaningful_label(cls,value):
        value=' '.join(value.split())
        if not value: raise ValueError('A reusable skill label is required')
        return value

    @model_validator(mode='after')
    def span(self):
        if not self.quote.strip(): raise ValueError('A meaningful source quote is required')
        if self.start is not None and self.end is not None and self.end<=self.start:
            raise ValueError('A source span must have positive length')
        return self


class LearningSignalExtraction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    signals: list[LearningSignal]=Field(default_factory=list,max_length=8)
    disposition: Literal['learning_signals','non_learning','insufficient_context','quoted_material']='non_learning'
