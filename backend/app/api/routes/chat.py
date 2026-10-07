from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.langchain.chat_service import ChatService

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1)


class ChatResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


@router.post("/chat", response_model=ChatResponse, summary="Send a chat message")
async def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    chat_service: ChatService = http_request.app.state.chat_service
    reply = await chat_service.reply(
        [(message.role, message.content) for message in request.messages]
    )
    return ChatResponse(content=reply)
