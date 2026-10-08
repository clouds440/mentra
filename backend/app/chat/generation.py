import re
import json
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.rag.schemas import SearchRequest, ChatSelection
from app.langchain.chat_service import ChatService
from app.chat.context import HistoryContextPolicy
from app.langchain.prompts import PromptSource, get_system_prompt
from .response import ChatResponse


async def generate_reply(messages, retrieval, http_request, identity, history_policy=None, history_scope=None) -> ChatResponse:
    chat_service: ChatService = http_request.app.state.chat_service
    rag_service = getattr(http_request.app.state, 'rag_service', None)
    result, warning = None, None
    if rag_service is not None:
        query = next((content for role, content in reversed(messages) if role == 'user'), '')
        selection = retrieval.model_dump() if retrieval else {}
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
    policy = history_policy or HistoryContextPolicy()
    if history_scope is not None and getattr(http_request.app.state, 'history_management', None) is not None:
        history_scope['history_token_budget'] = policy.max_tokens
        kwargs['history_runtime'] = (http_request.app.state.history_management, identity.learner_id, history_scope)
    else:
        system_text = get_system_prompt(PromptSource.CHAT)
        if rag_service is not None:
            system_text += '\n\n' + get_system_prompt(PromptSource.RAG_CONTEXT) + '\n\n' + json.dumps({'study_sources': packet}, ensure_ascii=False)
        messages = policy.for_prompt(messages, system_text)
    reply = await chat_service.reply(
        messages, **kwargs
    )
    if rag_service is None:
        references = dict(history_references=history_scope['history_references'], memory_references=history_scope['memory_references']) if history_scope else {}
        return ChatResponse(role='assistant', content=reply, **references)
    sources = [chunk.source for chunk in result.chunks] if result else []
    valid = {s.token for s in sources}
    cited = list(dict.fromkeys(token for token in re.findall(r'\[\[(S\d+)\]\]', reply) if token in valid))
    # Unknown markers never become links. The UI only resolves the allowlisted tokens.
    return ChatResponse(role='assistant', content=reply, sources=sources, citations=cited,
                        history_references=history_scope['history_references'] if history_scope else [],
                        memory_references=history_scope['memory_references'] if history_scope else [],
                        retrieval_status=packet['status'], retrieval_warning=warning,
                        retrieval_scope=ChatSelection(mode=retrieval.mode if retrieval else 'STANDARD',
                            context_ids=result.context_ids if result else None,
                            document_ids=list(dict.fromkeys(s.document_id for s in sources)),
                            include_archived=retrieval.include_archived if retrieval else False))
