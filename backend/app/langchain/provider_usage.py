"""Normalize compatible-provider cache counters discarded by the base adapter."""

from typing import Any
from langchain_core.outputs import ChatResult, ChatGenerationChunk


def attach_cache_usage(message: Any, usage: dict | None) -> None:
    if not isinstance(usage, dict) or message is None or message.usage_metadata is None:
        return
    hit = usage.get('prompt_cache_hit_tokens')
    if type(hit) is int and hit >= 0:
        details = dict(message.usage_metadata.get('input_token_details') or {})
        details['cache_read'] = hit
        message.usage_metadata = dict(message.usage_metadata, input_token_details=details)


class CacheUsageMixin:
    def _create_chat_result(self, response: Any, generation_info: dict | None = None) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        usage = response.get('usage') if isinstance(response, dict) else getattr(response, 'usage', None)
        if usage is not None and not isinstance(usage, dict):
            usage = usage.model_dump()
        for generation in result.generations:
            attach_cache_usage(generation.message, usage)
        return result

    def _convert_chunk_to_generation_chunk(self, chunk: dict, default_chunk_class: type,
                                            base_generation_info: dict | None) -> ChatGenerationChunk | None:
        result = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if result is not None:
            attach_cache_usage(result.message, chunk.get('usage'))
        return result
