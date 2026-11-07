"""Owned, revision-checked opt-in and reset; source observations are retained."""
from datetime import datetime,timezone
from sqlalchemy import select,update
from sqlalchemy.dialects.postgresql import insert
from app.core.exceptions import AppError
from app.history_management.repositories.events.postgres import request_hash
from app.core.config import settings
from .tables import states,controls,control_operations
from ..policy import POLICY


def page(repository,owner,after='',limit=20):
    if not 1<=limit<=50:raise AppError('CHALLENGE_PAGE','Choose a page size from 1 to 50.',422)
    from app.learner.repositories.tables import concept
    query=select(states,concept.c.canonical_name.label('name'),controls.c.enabled,
        controls.c.revision.label('control_revision')).join(concept,concept.c.id==states.c.concept_id).outerjoin(controls,
            (controls.c.learner_id==states.c.learner_id)&(controls.c.context_id==states.c.context_id)&(controls.c.concept_id==states.c.concept_id)).where(
        states.c.learner_id==owner,states.c.scope_key>after).order_by(states.c.scope_key).limit(limit+1)
    with repository.sessions() as session:rows=session.execute(query).mappings().all()
    items=[]
    for row in rows[:limit]:
        fresh=row['expires_at']>repository.clock() and row['policy']==POLICY
        global_enabled=settings.learner_challenge_adaptation_enabled and settings.learner_personalization_enabled
        items.append(dict(scope_key=row['scope_key'],context_id=row['context_id'],concept_id=row['concept_id'],name=row['name'],
            language=row['language'],answer_mode=row['answer_mode'],enabled=bool(row['enabled']),control_revision=row['control_revision'] or 0,
            global_enabled=global_enabled,
            mode='paused' if not global_enabled else 'expired' if not fresh else 'active' if row['enabled'] and row['payload']['offset'] else 'shadow',
            **dict(row['payload'],offset=row['payload']['offset'] if fresh else 0)))
    return dict(items=items,next_cursor=rows[limit-1]['scope_key'] if len(rows)>limit else None)


def change(repository,owner,body):
    owner_key=dict(learner_id=owner,context_id=body.context_id,concept_id=str(body.concept_id))
    fingerprint=request_hash(body.model_dump(mode='json'))
    with repository.transactions.write(owner) as tx:
        session=tx._session
        previous=session.execute(select(control_operations).where(control_operations.c.learner_id==owner,
            control_operations.c.id==str(body.client_request_id))).mappings().first()
        if previous:
            if previous['fingerprint']!=fingerprint:raise AppError('OPERATION_CONFLICT','This preference request changed.',409)
            return previous['result']
        from app.learner.repositories.tables import context_concept
        linked=session.scalar(select(context_concept.c.concept_id).where(context_concept.c.learner_id==owner,
            context_concept.c.context_id==body.context_id,context_concept.c.concept_id==str(body.concept_id)))
        if not linked:raise AppError('CHALLENGE_SKILL_NOT_FOUND','This skill is not available in your learning context.',404)
        old=session.execute(select(controls).filter_by(**owner_key)).mappings().first()
        revision=old['revision'] if old else 0
        if body.expected_revision!=revision:raise AppError('REVISION_CONFLICT','Your challenge preferences changed. Refresh and retry.',409)
        reset_at=repository.clock() if body.reset else old['reset_at'] if old else datetime(1970,1,1,tzinfo=timezone.utc)
        values=dict(**owner_key,enabled=body.enabled,reset_at=reset_at,revision=revision+1)
        session.execute(insert(controls).values(**values).on_conflict_do_update(index_elements=['learner_id','context_id','concept_id'],set_=values))
        if body.reset:
            from ..policy import evaluate
            session.execute(update(states).where(states.c.learner_id==owner,states.c.context_id==body.context_id,
                states.c.concept_id==str(body.concept_id)).values(payload=evaluate([]),updated_at=repository.clock(),expires_at=repository.clock()))
        result=dict(context_id=body.context_id,concept_id=str(body.concept_id),enabled=body.enabled,revision=revision+1,reset=body.reset)
        session.execute(control_operations.insert().values(learner_id=owner,id=str(body.client_request_id),fingerprint=fingerprint,result=result))
        return result
