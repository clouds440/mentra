"""Request-scoped OCR recovery without replaying orchestration or tool writes."""
from contextvars import ContextVar
from openai import APIConnectionError, APIStatusError

chat_image_fallback = ContextVar('chat_image_fallback', default=None)


def recoverable_image_failure(error):
    return isinstance(error, APIConnectionError) or (
        isinstance(error, APIStatusError) and (error.status_code in (400, 415, 422, 429) or error.status_code >= 500))


def has_images(messages):
    return any(isinstance(message.content, list) and any(
        isinstance(block, dict) and block.get('type') == 'image_url' for block in message.content) for message in messages)
