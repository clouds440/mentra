import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage

from app.core.exceptions import AppError
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelConfigurationError, ModelFactory
from app.langchain.prompts import PromptSource
from app.learner.schemas import LearnerContextPacket

logger = logging.getLogger("mentra")

class ChatService:
    def __init__(self, llm: MentraLLM | ModelFactory) -> None:
        self._llm = llm if isinstance(llm, MentraLLM) else MentraLLM(llm)

    async def reply(
        self,
        messages: list[tuple[Literal["user", "assistant"], str]],
        *,
        learner_context: LearnerContextPacket | None = None,
    ) -> str:
        conversation = [
            HumanMessage(content=content)
            if role == "user"
            else AIMessage(content=content)
            for role, content in messages
        ]
        try:
            response = await self._llm.ainvoke_messages(
                PromptSource.CHAT, conversation,
                additional_sources=((PromptSource.LEARNER_CONTEXT,) if learner_context is not None else ()),
                system_context=learner_context.model_dump_json(exclude_none=True) if learner_context is not None else None)
        except ModelConfigurationError as exc:
            raise AppError(
                "AI_CONFIGURATION_ERROR",
                str(exc),
                status_code=503,
            ) from exc
        except Exception as exc:
            logger.exception("Chat provider request failed.")
            raise AppError(
                "AI_PROVIDER_ERROR",
                "The AI provider could not complete the request. Check its "
                "configuration and try again.",
                status_code=502,
            ) from exc

        if not isinstance(response.content, str):
            raise AppError(
                "AI_PROVIDER_ERROR",
                "The AI provider returned an unsupported response format.",
                status_code=502,
            )
        return response.content
