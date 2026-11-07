from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field

class ChallengeAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_kind: Literal['draft','assessment']
    source_id: UUID
    expected_revision: int=Field(ge=1)
    direction: Literal['easier','harder']

class ChallengeControl(BaseModel):
    model_config=ConfigDict(extra='forbid')
    context_id: str=Field(min_length=1,max_length=100)
    concept_id: UUID
    enabled: bool
    reset: bool=False
    expected_revision: int=Field(ge=0)
    client_request_id: UUID
