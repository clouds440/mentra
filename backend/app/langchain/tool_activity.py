"""Pydantic-validated pre-tool announcements with no private argument disclosure."""
from typing import Literal
from uuid import uuid4
from pydantic import create_model
from langchain_core.tools import StructuredTool
from .activity import current_tool_call


LABELS = {
    'web_research': 'Researching the web',
    'web_search': 'Searching the web',
    'present_choices': 'Preparing choices for you',
    'event_lookup': 'Checking your events',
    'event_manage': 'Preparing an event for your review',
    'history_lookup': 'Searching earlier conversations',
    'user_memory': 'Checking your saved memories',
    'get_active_learning_contexts': 'Checking what you’re studying',
    'get_relevant_learner_context': 'Checking your learning progress',
    'get_study_recommendations': 'Finding what to study next',
    'get_student_weaknesses': 'Finding useful practice targets',
    'get_verification_candidates': 'Finding concepts to review',
    'resolve_student_concept': 'Understanding the topic',
    'search_study_material': 'Reading documents',
    'get_study_source_chunk': 'Reading the source passage',
    'assessment_generate': 'Creating your practice assessment',
    'assessment_revise': 'Revising your practice assessment',
    'assessment_question': 'Reading your assessment question',
    'assessment_status': 'Checking your assessment progress',
    'assessment_answer': 'Preparing your answers for evaluation',
    'assessment_lookup': 'Finding your assessment',
    'enable_workflow_tools': 'Preparing to help',
    'profile_context': 'Checking your learning preferences',
    'document_extract': 'Reading your attached document',
}


def announced_tool(tool, publisher):
    """Publish server-owned announcements around a native tool schema.

    Public text is deliberately a closed action vocabulary: a model cannot copy
    credentials, private evidence or its reasoning into persisted activity.
    """
    label = LABELS[tool.name]
    # Fixed public labels are server data, not extra model arguments. Accept old
    # callers after validating their literals without advertising redundant fields.
    class AnnouncedTool(StructuredTool):
        async def ainvoke(self, input, config=None, **kwargs):
            if isinstance(input, dict) and ('tool_name' in input or 'user_message' in input):
                legacy = create_model('LegacyAnnouncement', tool_name=(Literal[tool.name], tool.name), user_message=(Literal[label], label))
                legacy.model_validate({key: input[key] for key in ('tool_name', 'user_message') if key in input})
                input = {key: value for key, value in input.items() if key not in ('tool_name', 'user_message')}
            return await super().ainvoke(input, config=config, **kwargs)

    async def execute(**arguments):
        decision = tool.args_schema.model_validate(arguments)
        step = uuid4().hex
        call_id = current_tool_call.get()
        await publisher.emit(step, 'planned', label, tool_name=tool.name, tool_call_id=call_id)
        await publisher.emit(step, 'running', label, tool_name=tool.name, tool_call_id=call_id)
        try:
            result = await tool.ainvoke(decision.model_dump())
        except BaseException:
            await publisher.emit(step, 'failed', 'This step could not be completed.', tool_name=tool.name, tool_call_id=call_id)
            raise
        from .tool_execution import outcome_status
        status, _ = outcome_status(result)
        await publisher.emit(step, status, label if status == 'completed' else 'This action needs review or could not be completed.', tool_name=tool.name, tool_call_id=call_id)
        return result

    return AnnouncedTool.from_function(name=tool.name, description=tool.description,
        args_schema=tool.args_schema, coroutine=execute)
