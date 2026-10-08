from typing import Literal

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
import re
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.rag.schemas import ChatSelection, SearchRequest, SourceReference

from app.langchain.chat_service import ChatService
from app.student_profile.dependencies import require_onboarded_identity

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


class ChatResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    sources: list[SourceReference] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    retrieval_status: str = 'no_eligible_sources'
    retrieval_warning: str | None = None
    retrieval_scope: ChatSelection | None = None


@router.post("/chat", response_model=ChatResponse, response_model_exclude_unset=True, summary="Send a chat message")
async def chat(request: ChatRequest, http_request: Request, identity=Depends(require_onboarded_identity)) -> ChatResponse:
    chat_service: ChatService = http_request.app.state.chat_service
    rag_service = getattr(http_request.app.state, 'rag_service', None)
    result, warning = None, None
    if rag_service is not None:
        query = next((turn.content for turn in reversed(request.messages) if turn.role == 'user'), '')
        selection = request.retrieval.model_dump() if request.retrieval else {}
        try:
            result = await run_in_threadpool(rag_service.search, identity.learner_id, SearchRequest(query=query, **selection))
        except AppError as exc:
            if exc.code != 'RAG_UNAVAILABLE':
                raise
            warning = exc.message
    packet = dict(status=result.status if result else 'unavailable' if warning else 'no_eligible_sources',
                  sources=[chunk.source.model_dump() for chunk in result.chunks] if result else [])
    if result and result.warnings:
        warning = ' '.join(result.warnings)
    kwargs = {'source_packet': packet} if rag_service is not None else {}
    reply = await chat_service.reply(
        [(message.role, message.content) for message in request.messages], **kwargs
    )
    if rag_service is None:
        return ChatResponse(role='assistant', content=reply)
    sources = [chunk.source for chunk in result.chunks] if result else []
    valid = {s.token for s in sources}
    cited = list(dict.fromkeys(token for token in re.findall(r'\[\[(S\d+)\]\]', reply) if token in valid))
    # Unknown markers never become links. The UI only resolves the allowlisted tokens.
    return ChatResponse(role='assistant', content=reply, sources=sources, citations=cited,
                        retrieval_status=packet['status'], retrieval_warning=warning,
                        retrieval_scope=ChatSelection(mode=request.retrieval.mode if request.retrieval else 'STANDARD',
                            context_ids=result.context_ids if result else None,
                            document_ids=list(dict.fromkeys(s.document_id for s in sources)),
                            include_archived=request.retrieval.include_archived if request.retrieval else False))
