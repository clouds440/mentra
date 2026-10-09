from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

class Demonstration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    concept_id: str
    quote: str = Field(min_length=1,max_length=1000)
    score: float = Field(ge=0)
    max_score: float = Field(gt=0,le=10)
    difficulty: float = Field(ge=0,le=1)
    independence: float = Field(ge=0,le=1)
    confidence: float = Field(ge=0,le=1)
    hint_count: int = Field(default=0,ge=0,le=10)
    @model_validator(mode='after')
    def bounds(self):
        if self.score>self.max_score: raise ValueError('Score exceeds maximum')
        return self

class DemonstrationExtraction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    assessable: bool
    observations: list[Demonstration] = Field(default_factory=list,max_length=5)
