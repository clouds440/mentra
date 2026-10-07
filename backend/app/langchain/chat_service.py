import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.exceptions import AppError
from app.langchain.model_factory import ModelConfigurationError, ModelFactory

logger = logging.getLogger("mentra")

MENTRA_SYSTEM_PROMPT = (
    "You are Mentra, a supportive learning assistant. Explain ideas clearly, "
    "encourage understanding, and guide learners one step at a time."
)


class ChatService:
    def __init__(self, model_factory: ModelFactory) -> None:
        self._model_factory = model_factory

    async def reply(
        self,
        messages: list[tuple[Literal["user", "assistant"], str]],
    ) -> str:
        try:
            model = self._model_factory.get_model()
        except ModelConfigurationError as exc:
            raise AppError(
                "AI_CONFIGURATION_ERROR",
                str(exc),
                status_code=503,
            ) from exc

        conversation = [SystemMessage(content=MENTRA_SYSTEM_PROMPT)]
        conversation.extend(
            HumanMessage(content=content)
            if role == "user"
            else AIMessage(content=content)
            for role, content in messages
        )
        try:
            response = await model.ainvoke(conversation)
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
