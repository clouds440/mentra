import logging
import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage

from app.core.exceptions import AppError
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelConfigurationError, ModelFactory
from app.langchain.prompts import PromptSource
from app.learner.schemas import LearnerContextPacket

logger = logging.getLogger("mentra")

from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class ChatService:
    def __init__(self, llm: MentraLLM | ModelFactory) -> None:
        self._llm = llm if isinstance(llm, MentraLLM) else MentraLLM(llm)

    async def reply(
        self,
        messages: list[tuple[Literal["user", "assistant"], str]],
        *,
        learner_context: LearnerContextPacket | None = None,
        source_packet: dict | None = None,
        history_runtime: tuple | None = None,
        document_context: list[dict] | None = None,
        image_context: list[dict] | None = None,
        profile_context: dict | None = None,
        recovery_context: list[dict] | None = None,
    ) -> str:
        conversation = [
            HumanMessage(content=content)
            if role == "user"
            else AIMessage(content=content)
            for role, content in messages
        ]
        if history_runtime:
            scope = history_runtime[2]
            rows = list(reversed(scope['context_rows']))
            offset = 0
            for message in reversed(conversation):
                for index in range(offset, len(rows)):
                    row = rows[index]
                    if row['content'] == message.content and row['role'] == ('user' if message.type == 'human' else 'assistant'):
                        message.id = str(row['id'])
                        offset = index + 1
                        break
        from app.web_search.citations import historical_web_markers
        if image_context:
            current = next(message for message in reversed(conversation) if message.type == 'human')
            current.content = [dict(type='text', text=current.content), *[image['block'] for image in image_context]]
        for message in conversation:
            if message.type == 'ai':
                message.content = historical_web_markers(message.content)
        try:
            sources = []
            context = {}
            if recovery_context:
                sources.append(PromptSource.TOOL_RECOVERY)
                context['missing_context'] = recovery_context
            if profile_context is not None:
                from .response_style import response_style
                context['student_profile'] = profile_context
                context['response_style'] = response_style(profile_context)
            if document_context or image_context:
                sources.append(PromptSource.CHAT_ATTACHMENTS)
                context['chat_attachments'] = document_context or []
                if image_context:
                    context['chat_images'] = [dict(id=image['id'], filename=image['filename']) for image in image_context]
            if learner_context is not None:
                sources.append(PromptSource.LEARNER_CONTEXT)
                context['learner'] = learner_context.model_dump(mode='json', exclude_none=True)
            if source_packet is not None:
                sources.append(PromptSource.RAG_CONTEXT)
                context['study_sources'] = dict(source_packet, sources=[
                    {key:source[key] for key in ('token','title','excerpt','warnings') if key in source}
                    for source in source_packet.get('sources', [])])
            if history_runtime:
                from .history_orchestration import tool_reply
                from app.chat.titles import NewChatReply
                service, owner, scope = history_runtime
                first_turn = scope.get('user_sequence') == 1
                if first_turn:
                    sources.append(PromptSource.CHAT_TITLE)
                response = await tool_reply(self._llm, conversation, service, owner, scope, tuple(sources), context,
                                            output_schema=NewChatReply if first_turn else None)
                if isinstance(response, NewChatReply):
                    scope['conversation_title'] = response.conversation_title
            else:
                response = await self._llm.ainvoke_messages(
                    PromptSource.CHAT, conversation,
                    additional_sources=tuple(sources),
                    system_context=json.dumps(context, ensure_ascii=False, separators=(',', ':')) if context else None)
        except ModelConfigurationError as exc:
            raise AppError(
                "AI_CONFIGURATION_ERROR",
                "Mentra isn’t available right now. Please try again later.",
                status_code=503,
            ) from exc
        except AppError:
            raise
        except Exception as exc:
            logger.warning("Chat provider request failed (%s).", type(exc).__name__)
            raise AppError(
                "AI_PROVIDER_ERROR",
                "Mentra couldn’t finish this response. Please try again.",
                status_code=502,
            ) from exc

        if not isinstance(response.content, str) or not response.content.strip():
            raise AppError(
                "AI_PROVIDER_ERROR",
                "Mentra couldn’t finish this response. Please try again.",
                status_code=502,
            )
        return response.content
