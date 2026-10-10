"""Pydantic-validated pre-tool announcements with no private argument disclosure."""
from typing import Literal
from uuid import uuid4
from pydantic import Field, create_model
from langchain_core.tools import StructuredTool
from .activity import current_tool_call


LABELS = {
    'event_lookup': 'Checking your events',
    'event_manage': 'Preparing an event for your review',
    'history_lookup': 'Searching earlier conversations',
    'user_memory': 'Checking your saved memories',
    'get_active_learning_contexts': 'Checking your learning contexts',
    'get_relevant_learner_context': 'Checking your learning progress',
    'get_study_recommendations': 'Finding what to study next',
    'get_student_weaknesses': 'Finding useful practice targets',
    'get_verification_candidates': 'Finding concepts to review',
    'resolve_student_concept': 'Identifying the learning concept',
    'search_study_material': 'Reading documents',
    'get_study_source_chunk': 'Reading the source passage',
    'assessment_generate': 'Creating your practice assessment',
    'assessment_revise': 'Revising your practice assessment',
    'assessment_question': 'Reading your assessment question',
    'assessment_status': 'Checking your assessment progress',
    'assessment_answer': 'Preparing your answers for evaluation',
    'assessment_lookup': 'Finding your assessment',
    'enable_workflow_tools': 'Preparing the tools for your request',
}


def announced_tool(tool, publisher):
    """Native tool schemas require the model to announce the selected capability.

    Public text is deliberately a closed action vocabulary: a model cannot copy
    credentials, private evidence or its reasoning into persisted activity.
    """
    label = LABELS[tool.name]
    schema = create_model(f'{tool.args_schema.__name__}Announcement', __base__=tool.args_schema,
        tool_name=(Literal[tool.name], Field(description='Exact name of the tool being used.')),
        user_message=(Literal[label], Field(description='Public action shown before execution.')))

    async def execute(**arguments):
        decision = schema.model_validate(arguments)
        step = uuid4().hex
        call_id = current_tool_call.get()
        await publisher.emit(step, 'planned', decision.user_message, tool_name=decision.tool_name, tool_call_id=call_id)
        async with publisher.step(decision.user_message, tool_name=decision.tool_name, tool_call_id=call_id, step_id=step):
            return await tool.ainvoke(decision.model_dump(exclude={'tool_name', 'user_message'}))

    return StructuredTool.from_function(name=tool.name, description=tool.description,
        args_schema=schema, coroutine=execute)
