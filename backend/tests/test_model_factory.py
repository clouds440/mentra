import sys
import types
import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.langchain.model_factory import ModelConfigurationError, ModelFactory


def configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "openai_compatible",
        "ai_model": "chat-model",
        "ai_base_url": "https://compatible.example/v1",
        "ai_api_key": "test-secret",
    }
    values.update(overrides)
    return Settings(**values)


class ModelFactoryTests(unittest.TestCase):
    def test_model_uses_configured_compatible_endpoint(self) -> None:
        captured: dict[str, object] = {}

        class FakeChatOpenAI:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        fake_module = types.ModuleType("langchain_openai")
        fake_module.ChatOpenAI = FakeChatOpenAI

        with patch.dict(sys.modules, {"langchain_openai": fake_module}):
            model = ModelFactory(
                configured_settings(
                    ai_base_url="https://api.deepseek.example/v1",
                    ai_model="deepseek-chat",
                    ai_api_key="provider-secret",
                    ai_temperature=0.7,
                    ai_timeout=12,
                    ai_max_retries=4,
                )
            ).get_model()

        self.assertIsInstance(model, FakeChatOpenAI)
        self.assertEqual(
            captured,
            {
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.example/v1",
                "api_key": "provider-secret",
                "temperature": 0.7,
                "timeout": 12,
                "max_retries": 4,
            },
        )

    def test_missing_required_configuration_is_reported(self) -> None:
        factory = ModelFactory(
            configured_settings(ai_model="", ai_base_url="", ai_api_key="")
        )

        with self.assertRaisesRegex(
            ModelConfigurationError, "AI_MODEL, AI_BASE_URL, AI_API_KEY"
        ):
            factory.validate_configuration()

    def test_unknown_provider_is_rejected(self) -> None:
        factory = ModelFactory(configured_settings(ai_provider="other"))

        with self.assertRaisesRegex(ModelConfigurationError, "Unsupported AI_PROVIDER"):
            factory.validate_configuration()

    def test_invalid_base_url_is_rejected_at_configuration_validation(self) -> None:
        factory = ModelFactory(configured_settings(ai_base_url="not-a-url"))

        with self.assertRaisesRegex(ModelConfigurationError, "AI_BASE_URL"):
            factory.validate_configuration()
