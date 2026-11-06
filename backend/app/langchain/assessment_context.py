"""Optional preparation is bounded by the learner facade and never owns writes."""
from app.core.logging import workflow_logger
from app.core.exceptions import AppError
from app.db.errors import database_failure_code


def optional_read(stage, action):
    try:
        return action()
    except Exception as error:
        code = database_failure_code(error)
        if not code and not isinstance(error, TimeoutError) and not (isinstance(error, AppError) and error.status_code >= 500):
            raise
        workflow_logger.event('assessment.personalization_unavailable', stage=stage,
            code=code or getattr(error, 'code', 'CONTEXT_TIMEOUT'))
        return None


def optional_context(workflows, owner, request, *, reuse=False):
    preparation, profile = None, None
    stages = []
    if not reuse:
        stages.append(('learner', lambda: workflows.learner.get_assessment_context(owner, request.context_id, request.topic, request.concept_ids,profile=workflows.profile)))
    if workflows.profile and reuse:
        stages.append(('profile', lambda: workflows.profile.prompt_snapshot(owner)))
    # One sync task: no shared session or parallel checkout fanout at pool size 1.
    for stage, action in stages:
        value = optional_read(stage, action)
        if stage == 'learner':
            preparation = value
            profile = value.profile if value else None
        else: profile = value
    return preparation, profile
