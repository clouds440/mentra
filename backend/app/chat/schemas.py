from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.rag.schemas import ChatSelection


class SendTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID
    client_turn_id: UUID
    expected_revision: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=4000)
    retrieval: ChatSelection = Field(default_factory=ChatSelection)
    retry: bool = False


class EditConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)


class TurnStatus(BaseModel):
    state: Literal['RUNNING', 'SUCCEEDED', 'FAILED']
