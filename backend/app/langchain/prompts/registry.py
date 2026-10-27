"""Resolve system prompts from explicit server-selected workflow sources."""

from enum import StrEnum
from functools import lru_cache


class PromptSource(StrEnum):
    MEMORY_SUMMARY = 'memory_summary'
    CHAT_SUMMARY = 'chat_summary'
    CHAT = "chat"
    CHAT_ASSESSMENT = "chat_assessment"
    RESPONSE_EDIT = 'response_edit'
    CHAT_TITLE = 'chat_title'
    LEARNER_CONTEXT = "learner_context"
    STUDENT_PROFILE_EVALUATION = "student_profile_evaluation"
    RAG_CONTEXT = "rag_context"
    HISTORY_MANAGEMENT = "history_management"
    MEMORY_VALIDATION = "memory_validation"
    CHAT_ATTACHMENTS = "chat_attachments"
    ASSESSMENT_GENERATION = 'assessment_generation'
    ASSESSMENT_DESIGN = 'assessment_design'
    ASSESSMENT_SELECTION = 'assessment_selection'
    ASSESSMENT_TARGETS = 'assessment_targets'
    CONCEPT_IDENTITY = 'concept_identity'
    ASSESSMENT_GRADING = 'assessment_grading'
    ASSESSMENT_TRANSCRIPTION = 'assessment_transcription'
    CHAT_EVIDENCE = 'chat_evidence'
    EVENT_ADMISSION = 'event_admission'
    TOOL_RECOVERY = 'tool_recovery'
    WEB_SEARCH = 'web_search'


@lru_cache(maxsize=len(PromptSource))
def get_system_prompt(source: PromptSource) -> str:
    """Load a source-owned prompt. Untrusted requests never choose this value."""
    source = PromptSource(source)
    if source is PromptSource.MEMORY_SUMMARY:
        from .memory_summary import SYSTEM_PROMPT
        return SYSTEM_PROMPT
    if source is PromptSource.CHAT_SUMMARY:
        from .chat_summary import SYSTEM_PROMPT
        return SYSTEM_PROMPT
    if source is PromptSource.CHAT:
        from .chat import SYSTEM_PROMPT
        from .chat_ui import SYSTEM_PROMPT as UI_PROMPT
        return SYSTEM_PROMPT + '\n\n' + UI_PROMPT
    elif source is PromptSource.CHAT_ASSESSMENT:
        from .chat_assessment import SYSTEM_PROMPT
    elif source is PromptSource.RESPONSE_EDIT:
        from .response_edit import SYSTEM_PROMPT
    elif source is PromptSource.CHAT_TITLE:
        from .chat_title import SYSTEM_PROMPT
    elif source is PromptSource.LEARNER_CONTEXT:
        from .learner_context import SYSTEM_PROMPT
    elif source is PromptSource.STUDENT_PROFILE_EVALUATION:
        from .student_profile import SYSTEM_PROMPT
    elif source is PromptSource.RAG_CONTEXT:
        from .rag_context import SYSTEM_PROMPT
    elif source is PromptSource.HISTORY_MANAGEMENT:
        from .history_management import SYSTEM_PROMPT
    elif source is PromptSource.MEMORY_VALIDATION:
        from .memory_validation import SYSTEM_PROMPT
    elif source is PromptSource.CHAT_ATTACHMENTS:
        from .chat_attachments import SYSTEM_PROMPT
    elif source is PromptSource.ASSESSMENT_GENERATION:
        from .assessment_generation import SYSTEM_PROMPT
    elif source is PromptSource.ASSESSMENT_DESIGN:
        from .assessment_design import SYSTEM_PROMPT
    elif source is PromptSource.ASSESSMENT_SELECTION:
        from .assessment_selection import SYSTEM_PROMPT
    elif source is PromptSource.ASSESSMENT_TARGETS:
        from .assessment_targets import SYSTEM_PROMPT
    elif source is PromptSource.CONCEPT_IDENTITY:
        from .concept_identity import SYSTEM_PROMPT
    elif source is PromptSource.ASSESSMENT_GRADING:
        from .assessment_grading import SYSTEM_PROMPT
    elif source is PromptSource.ASSESSMENT_TRANSCRIPTION:
        from .assessment_transcription import SYSTEM_PROMPT
    elif source is PromptSource.CHAT_EVIDENCE:
        from .evidence import SYSTEM_PROMPT
    elif source is PromptSource.EVENT_ADMISSION:
        from .event_admission import SYSTEM_PROMPT
    elif source is PromptSource.TOOL_RECOVERY:
        from .tool_recovery import SYSTEM_PROMPT
    elif source is PromptSource.WEB_SEARCH:
        from .web_search import SYSTEM_PROMPT
    else:  # Defensive if the enum grows without a registered prompt module.
        raise ValueError(f"No system prompt is registered for {source!r}")
    return SYSTEM_PROMPT


@lru_cache(maxsize=len(PromptSource))
def get_prompt_version(source: PromptSource) -> str:
    """Return the version alongside the source-owned system instructions."""
    source = PromptSource(source)
    if source is PromptSource.MEMORY_SUMMARY:
        from .memory_summary import VERSION
        return VERSION
    if source is PromptSource.CHAT_SUMMARY:
        return 'chat-summary-v2'
    if source is PromptSource.CHAT:
        from .chat import VERSION
        from .chat_ui import VERSION as UI_VERSION
        return VERSION + '+' + UI_VERSION
    elif source is PromptSource.CHAT_ASSESSMENT:
        from .chat_assessment import VERSION
    elif source is PromptSource.RESPONSE_EDIT:
        from .response_edit import VERSION
    elif source is PromptSource.CHAT_TITLE:
        from .chat_title import VERSION
    elif source is PromptSource.LEARNER_CONTEXT:
        from .learner_context import VERSION
    elif source is PromptSource.STUDENT_PROFILE_EVALUATION:
        from .student_profile import VERSION
    elif source is PromptSource.RAG_CONTEXT:
        from .rag_context import VERSION
    elif source is PromptSource.HISTORY_MANAGEMENT:
        from .history_management import VERSION
    elif source is PromptSource.MEMORY_VALIDATION:
        from .memory_validation import VERSION
    elif source is PromptSource.CHAT_ATTACHMENTS:
        from .chat_attachments import VERSION
    elif source is PromptSource.ASSESSMENT_GENERATION:
        from .assessment_generation import VERSION
    elif source is PromptSource.ASSESSMENT_DESIGN:
        from .assessment_design import VERSION
    elif source is PromptSource.ASSESSMENT_SELECTION:
        from .assessment_selection import VERSION
    elif source is PromptSource.ASSESSMENT_TARGETS:
        from .assessment_targets import VERSION
    elif source is PromptSource.CONCEPT_IDENTITY:
        from .concept_identity import VERSION
    elif source is PromptSource.ASSESSMENT_GRADING:
        from .assessment_grading import VERSION
    elif source is PromptSource.ASSESSMENT_TRANSCRIPTION:
        from .assessment_transcription import VERSION
    elif source is PromptSource.CHAT_EVIDENCE:
        from .evidence import VERSION
    elif source is PromptSource.EVENT_ADMISSION:
        from .event_admission import VERSION
    elif source is PromptSource.TOOL_RECOVERY:
        from .tool_recovery import VERSION
    elif source is PromptSource.WEB_SEARCH:
        from .web_search import VERSION
    else:
        raise ValueError(f"No prompt version is registered for {source!r}")
    return VERSION
