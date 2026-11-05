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
    prepare = getattr(workflows.learner, 'get_assessment_context', None)
    if prepare and not reuse:
        stages.append(('learner', lambda: prepare(owner, request.context_id, request.topic, request.concept_ids)))
    if workflows.profile:
        profile_read = getattr(workflows.profile, 'prompt_snapshot', None) or workflows.profile.prompt_context
        stages.append(('profile', lambda: profile_read(owner)))
    # One sync task: no shared session or parallel checkout fanout at pool size 1.
    for stage, action in stages:
        value = optional_read(stage, action)
        if stage == 'learner': preparation = value
        else: profile = value
    return preparation, profile
