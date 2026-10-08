from typing import Literal

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
import re
import json
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.rag.schemas import ChatSelection, SearchRequest, SourceReference

from app.langchain.chat_service import ChatService
from app.chat.context import HistoryContextPolicy
from app.langchain.prompts import PromptSource, get_system_prompt
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
    return await generate_reply([(message.role, message.content) for message in request.messages], request.retrieval, http_request, identity)
