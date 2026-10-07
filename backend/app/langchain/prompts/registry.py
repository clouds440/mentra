"""Resolve system prompts from explicit server-selected workflow sources."""

from enum import StrEnum
from functools import lru_cache


class PromptSource(StrEnum):
    CHAT = "chat"
    LEARNER_CONTEXT = "learner_context"
    STUDENT_PROFILE_EVALUATION = "student_profile_evaluation"


@lru_cache(maxsize=len(PromptSource))
def get_system_prompt(source: PromptSource) -> str:
    """Load a source-owned prompt. Untrusted requests never choose this value."""
    source = PromptSource(source)
    if source is PromptSource.CHAT:
        from .chat import SYSTEM_PROMPT
    elif source is PromptSource.LEARNER_CONTEXT:
        from .learner_context import SYSTEM_PROMPT
    elif source is PromptSource.STUDENT_PROFILE_EVALUATION:
        from .student_profile import SYSTEM_PROMPT
    else:  # Defensive if the enum grows without a registered prompt module.
        raise ValueError(f"No system prompt is registered for {source!r}")
    return SYSTEM_PROMPT


@lru_cache(maxsize=len(PromptSource))
def get_prompt_version(source: PromptSource) -> str:
    """Return the version alongside the source-owned system instructions."""
    source = PromptSource(source)
    if source is PromptSource.CHAT:
        from .chat import VERSION
    elif source is PromptSource.LEARNER_CONTEXT:
        from .learner_context import VERSION
    elif source is PromptSource.STUDENT_PROFILE_EVALUATION:
        from .student_profile import VERSION
    else:
        raise ValueError(f"No prompt version is registered for {source!r}")
    return VERSION
