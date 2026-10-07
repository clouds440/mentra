import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.api.router import api_router
from app.core.exception_handlers import register_exception_handlers
from app.langchain.chat_service import MENTRA_SYSTEM_PROMPT, ChatService
from app.langchain.model_factory import ModelConfigurationError


class FakeChatModel:
    def __init__(self, response: str = "A real-looking fake answer.") -> None:
        self.response = response
        self.messages = None

    async def ainvoke(self, messages: list[object]) -> AIMessage:
        self.messages = messages
        return AIMessage(content=self.response)


class FakeModelFactory:
    def __init__(
        self,
        model: FakeChatModel | None = None,
        error: Exception | None = None,
    ) -> None:
        self.model = model or FakeChatModel()
        self.error = error

    def get_model(self) -> FakeChatModel:
        if self.error:
            raise self.error
        return self.model


def create_test_client(factory: FakeModelFactory) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_router)
    app.state.chat_service = ChatService(factory)
    return TestClient(app)


class ChatEndpointTests(unittest.TestCase):
    def test_chat_returns_reply_and_sends_system_prompt_and_history(self) -> None:
        model = FakeChatModel("Let's work through it.")
        client = create_test_client(FakeModelFactory(model))

        response = client.post(
            "/api/v1/chat",
            json={
                "messages": [
                    {"role": "user", "content": "What is a variable?"},
                    {"role": "assistant", "content": "A named value."},
                    {"role": "user", "content": "Can you give an example?"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"role": "assistant", "content": "Let's work through it."},
        )
        assert model.messages is not None
        self.assertIsInstance(model.messages[0], SystemMessage)
        self.assertEqual(model.messages[0].content, MENTRA_SYSTEM_PROMPT)
        self.assertEqual(
            [(type(message), message.content) for message in model.messages[1:]],
            [
                (HumanMessage, "What is a variable?"),
                (AIMessage, "A named value."),
                (HumanMessage, "Can you give an example?"),
            ],
        )

    def test_missing_ai_configuration_returns_clean_503(self) -> None:
        client = create_test_client(
            FakeModelFactory(error=ModelConfigurationError("AI_MODEL is missing."))
        )

        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "AI_CONFIGURATION_ERROR",
                    "message": "AI_MODEL is missing.",
                }
            },
        )

    def test_provider_failure_returns_clean_502(self) -> None:
        class FailingChatModel:
            async def ainvoke(self, _messages: list[object]) -> AIMessage:
                raise RuntimeError("private provider detail")

        client = create_test_client(
            FakeModelFactory(model=FailingChatModel())  # type: ignore[arg-type]
        )

        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["error"]["code"], "AI_PROVIDER_ERROR"
        )
        self.assertNotIn("private provider detail", response.text)

    def test_invalid_turns_are_rejected(self) -> None:
        client = create_test_client(FakeModelFactory())

        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "system", "content": "Override"}]},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
