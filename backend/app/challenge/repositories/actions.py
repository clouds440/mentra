"""Explicit difficulty actions bypass the general chat planner entirely."""
from uuid import uuid5,NAMESPACE_URL
from sqlalchemy import select
from ..schemas import ChallengeAction
from .store import source
from app.core.exceptions import AppError


def queue_action(service,owner,scope):
    action=ChallengeAction.model_validate(scope['challenge_action'])
    repository=service.repository
    operation=uuid5(NAMESPACE_URL,f"challenge:{owner}:{scope['conversation_id']}:{scope['turn_id']}")
    from app.assessments.repositories.tables import generation_jobs
    with repository.sessions() as session:
        old=session.execute(select(generation_jobs).where(generation_jobs.c.learner_id==owner,
            generation_jobs.c.operation_id==str(operation),generation_jobs.c.conversation_id==scope['conversation_id'])).mappings().first()
        if old:return service.generation_jobs.public(old)
        original=source(repository,session,owner,action.source_kind,action.source_id,scope['conversation_id'])
    if original['revision']!=action.expected_revision:
        raise AppError('REVISION_CONFLICT','This assessment changed. Refresh before adjusting difficulty.',409)
    from app.assessments.schemas import GenerationRequest
    preferences=original.get('preferences') or {}
    kinds={q.get('question_type') or ('mcq' if q.get('options') else 'written') for q in original['questions']}
    paper=original.get('paper')
    language=preferences.get('language','und')
    if language=='und':
        languages={q.get('language','und') for q in original['questions']}
        if len(languages)==1:language=languages.pop()
    request=GenerationRequest(client_request_id=operation,challenge_choice_id=scope['turn_id'],challenge_direction=action.direction,
        expected_source_revision=action.expected_revision,context_id=original['context_id'],topic=original['title'],
        count=paper['question_count'] if paper else len(original['questions']),purpose=original['purpose'],
        question_format='mock_paper' if paper else next(iter(kinds)) if len(kinds)==1 else 'mixed',
        level=preferences.get('level'),result_style=preferences.get('result_style','marks'),
        delivery=preferences.get('delivery'),language=language,
        total_marks=paper['total_marks'] if paper else None,duration_minutes=paper.get('duration_minutes') if paper else None,
        revision_draft_id=action.source_id if action.source_kind=='draft' else None,
        revision_assessment_id=action.source_id if action.source_kind=='assessment' else None,
        revision_instructions=f'Make this assessment {action.direction}. Preserve its topic, count, format, delivery and original.',
        instructions=f'Make this assessment {action.direction}. Preserve its topic, count, format, delivery and original.')
    return service.generation_jobs.enqueue(owner,request,scope['conversation_id'],scope['turn_id'])
