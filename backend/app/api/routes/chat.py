from typing import Literal

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.rag.schemas import ChatSelection

from app.student_profile.dependencies import require_onboarded_identity

from app.chat.response import ChatResponse
from app.chat.generation import generate_reply

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    messages: list[ChatTurn] = Field(min_length=1, max_length=100)
    retrieval: ChatSelection | None = None

    @model_validator(mode='after')
    def question_budget(self):
        if any(turn.role == 'user' and len(turn.content) > 4000 for turn in self.messages):
            raise ValueError('Shorten your question to at most 4000 characters.')
        return self


@router.post("/chat", response_model=ChatResponse, response_model_exclude_unset=True, summary="Legacy stateless chat", deprecated=True)
async def chat(request: ChatRequest, http_request: Request, identity=Depends(require_onboarded_identity)) -> ChatResponse:
    from app.db.admission import request_capacity
    async with request_capacity(http_request, getattr(identity, 'learner_id', None), 'model', capacity=16, owner_capacity=2):
        return await generate_reply([(message.role, message.content) for message in request.messages], request.retrieval, http_request, identity)
