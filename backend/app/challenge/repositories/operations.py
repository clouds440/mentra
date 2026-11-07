"""Private owner-scoped diagnostics and recovery. Never exports answers or keys."""
from sqlalchemy import select,update,Text
from app.core.exceptions import AppError
from .tables import choices,outcomes,states,jobs
from .store import refresh_many


def export_page(repository,owner,kind,after='',limit=50):
    if kind not in ('choices','outcomes') or not 1<=limit<=100:
        raise AppError('CHALLENGE_EXPORT','Choose choices/outcomes and a limit from 1 to 100.',422)
    table=choices if kind=='choices' else outcomes
    if kind=='choices':
        columns=[table.c.id,table.c.source_kind,table.c.source_id,table.c.source_revision,table.c.direction,
            table.c.job_id,table.c.assessment_id,table.c.family,table.c.created_at,table.c.served_at]
        cursor=table.c.id.cast(Text)
    else:
        columns=[table.c.attempt_id,table.c.grade_revision,table.c.scope_key,table.c.assessment_id,
            table.c.choice_id,table.c.family,table.c.occurred_at,table.c.payload]
        cursor=table.c.attempt_id.cast(Text)+':'+table.c.grade_revision.cast(Text)+':'+table.c.scope_key
    with repository.sessions() as session:
        rows=session.execute(select(*columns,cursor.label('cursor')).where(table.c.learner_id==owner,cursor>after)
            .order_by(cursor).limit(limit+1)).mappings().all()
    return dict(items=[dict(row) for row in rows[:limit]],next_cursor=rows[limit-1]['cursor'] if len(rows)>limit else None)


def retry(repository,owner,identifier):
    with repository.transactions.write(owner) as tx:
        row=tx._session.execute(update(jobs).where(jobs.c.learner_id==owner,jobs.c.id==identifier,jobs.c.state=='failed')
            .values(state='queued',attempts=0,claim_id=None,claim_until=None,retry_at=None).returning(jobs.c.id)).first()
        if not row:raise AppError('CHALLENGE_RETRY_UNAVAILABLE','No failed challenge update exists for this owner.',409)
    return dict(id=identifier,state='queued')


def rebuild(repository,owner,after='',limit=32):
    if not 1<=limit<=32:raise AppError('CHALLENGE_REBUILD','Rebuild at most 32 scopes per transaction.',422)
    with repository.transactions.write(owner) as tx:
        rows=tx._session.execute(select(states).where(states.c.learner_id==owner,states.c.scope_key>after)
            .order_by(states.c.scope_key).limit(limit+1)).mappings().all()
        scopes={row['scope_key']:{key:row[key] for key in ('context_id','concept_id','language','answer_mode')} for row in rows[:limit]}
        refresh_many(tx._session,owner,scopes,repository.clock())
    return dict(rebuilt=len(scopes),next_cursor=rows[limit-1]['scope_key'] if len(rows)>limit else None)
