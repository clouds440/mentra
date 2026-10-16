from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.core.config import Settings, settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class ModelConfigurationError(RuntimeError):
    """Raised when the configured chat model cannot be constructed."""


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class ModelFactory:
    def __init__(self, app_settings: Settings) -> None:
        self._settings = app_settings
        self._models = {}

    def validate_configuration(self) -> None:
        if self._settings.ai_provider != "openai_compatible":
            raise ModelConfigurationError(
                "Unsupported AI_PROVIDER "
                f"{self._settings.ai_provider!r}; supported value: "
                "'openai_compatible'."
            )

        missing = [
            name
            for name, value in (
                ("AI_MODEL", self._settings.ai_model),
                ("AI_BASE_URL", self._settings.ai_base_url),
                ("AI_API_KEY", self._settings.ai_api_key),
            )
            if not value.strip()
        ]
        if missing:
            names = ", ".join(missing)
            raise ModelConfigurationError(
                f"Missing required chat model configuration: {names}. "
                "Set these environment variables before starting Mentra."
            )
        base_url = urlsplit(self._settings.ai_base_url)
        if base_url.scheme not in {"http", "https"} or not base_url.netloc:
            raise ModelConfigurationError(
                "AI_BASE_URL must be an absolute HTTP or HTTPS URL for an "
                "OpenAI-compatible chat endpoint."
            )

    def get_model(self, *, output_tokens=None, model_name=None, maximum_retries=None) -> BaseChatModel:
        self.validate_configuration()
        output_tokens = output_tokens or self._settings.chat_output_token_reserve
        retries = self._settings.ai_max_retries if maximum_retries is None else maximum_retries
        key = (output_tokens, model_name or self._settings.ai_model, retries)
        if key in self._models:
            return self._models[key]
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ModelConfigurationError(
                "The langchain-openai package is required to create chat models."
            ) from exc

        provider_options = {}
        if urlsplit(self._settings.ai_base_url).hostname == 'api.deepseek.com':
            # DeepSeek defaults to thinking mode, which rejects required/named
            # tool choices used for both structured answers and domain tools.
            provider_options['extra_body'] = {'thinking': {'type': 'disabled'}}
            provider_options['stream_usage'] = True
            from .provider_usage import CacheUsageMixin
            class CacheAwareChatOpenAI(CacheUsageMixin, ChatOpenAI):
                pass
            ChatOpenAI = CacheAwareChatOpenAI
        model = ChatOpenAI(
            model=model_name or self._settings.ai_model,
            base_url=self._settings.ai_base_url,
            api_key=self._settings.ai_api_key,
            temperature=self._settings.ai_temperature,
            timeout=self._settings.ai_timeout,
            max_retries=retries,
            max_tokens=output_tokens,
            **provider_options,
        )
        # Reuse the client's configured transport/timeout/proxy behavior. The
        # pinned adapter exposes its httpx client; only attach a content-free hook.
        from .provider_activity import observe_request, observe_response
        client = getattr(getattr(model, 'root_async_client', None), '_client', None)
        hooks = getattr(client, 'event_hooks', None)
        if isinstance(hooks, dict) and observe_request not in hooks.get('request', []):
            hooks.setdefault('request', []).append(observe_request)
            hooks.setdefault('response', []).append(observe_response)
        self._models[key] = model
        return model


model_factory = ModelFactory(settings)
