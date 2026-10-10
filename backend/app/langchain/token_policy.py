"""Provider-independent guards; payloads are never truncated silently."""
import json
import math
import os
import hashlib
import tempfile
from pathlib import Path
from functools import lru_cache
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.utils.function_calling import convert_to_openai_tool
from app.core.config import settings
from app.core.exceptions import AppError


@lru_cache(maxsize=1)
def _encoding():
    try:
        import tiktoken
        # get_encoding downloads its vocabulary when the cache is missing.
        # Guard that path: request-time budgeting must never wait on a download.
        location = os.environ.get('TIKTOKEN_CACHE_DIR', os.environ.get('DATA_GYM_CACHE_DIR',
            os.path.join(tempfile.gettempdir(), 'data-gym-cache')))
        if not location:
            return None
        vocabulary = Path(location) / hashlib.sha1(
            b'https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken').hexdigest()
        if hashlib.sha256(vocabulary.read_bytes()).hexdigest() != '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7':
            return None
        return tiktoken.get_encoding('cl100k_base')
    except Exception:
        # A missing tokenizer cache must not trigger unguarded provider calls.
        # UTF-8 bytes conservatively bound BPE tokens without a network dependency.
        return None


def count_messages(messages):
    """Use a Unicode-aware tokenizer, conservatively retaining protocol estimates.

    Compatible providers may tokenize differently; usage metadata is authoritative.
    """
    messages = list(messages)
    estimate = count_tokens_approximately(messages, tokens_per_image=2048)
    for message in messages:
        texts = ([message.content] if isinstance(message.content,str) else
                 [block.get('text','') for block in message.content if isinstance(block,dict) and block.get('type')=='text'])
        for text in texts:
            encoding = _encoding()
            tokens = len(encoding.encode(text, disallowed_special=())) if encoding else len(text.encode('utf-8'))
            estimate += max(0, tokens - math.ceil(len(text)/4))
    return estimate


def output_budget(source, config=settings):
    if source.value == 'assessment_generation':
        return min(config.assessment_generation_output_tokens, config.chat_context_window_tokens // 2)
    if source.value in ('assessment_grading', 'assessment_transcription'):
        return min(config.assessment_grading_output_tokens, config.chat_context_window_tokens // 2)
    return config.chat_output_token_reserve


def schema_tokens(tools):
    if not tools:
        return 0
    content = json.dumps([convert_to_openai_tool(tool) for tool in tools], ensure_ascii=False, separators=(',', ':'))
    return count_messages([HumanMessage(content=content)])


def check_input(messages, source, *, tools=None, config=settings):
    # High-detail images cost more than the library's low-resolution default.
    # Bound dimensions in the extractor and reserve a conservative per-page cost.
    tokens = count_messages(messages) + schema_tokens(tools)
    if tokens + output_budget(source, config) + 256 > config.chat_context_window_tokens:
        raise AppError('AI_CONTEXT_LIMIT', 'This workflow exceeds the model context budget. Reduce its input or split the work.', 422)
    return tokens


def reserve_workflow(source, tokens, config=settings):
    from .workflow_budget import current_budget
    budget = current_budget.get()
    if budget is not None:
        budget.reserve(tokens, output_budget(source, config))


def log_usage(result, source, estimated_input):
    from app.core.logging import workflow_logger
    usage = getattr(result, 'usage_metadata', None) or {}
    counts = {key: value for key in ('input_tokens', 'output_tokens', 'total_tokens')
              if isinstance((value := usage.get(key)), int)}
    details = usage.get('input_token_details') or {}
    if isinstance(details.get('cache_read'), int):
        counts['cached_tokens'] = details['cache_read']
    workflow_logger.event('model.usage', prompt_source=source.value, estimated_input_tokens=estimated_input,
                          usage_available=bool(counts), **counts)
