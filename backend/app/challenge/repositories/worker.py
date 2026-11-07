"""Independent durable challenge learning; cannot roll back formal evidence."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select,update,or_,and_
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.logging import workflow_logger
from .tables import jobs


def enqueue(repository,session,owner,kind,subject,payload):
    values=dict(learner_id=owner,id=str(uuid4()),kind=kind,subject=subject,payload=payload,state='queued',attempts=0,created_at=repository.clock())
    session.execute(insert(jobs).values(**values).on_conflict_do_nothing(index_elements=['learner_id','kind','subject']))


class ChallengeWorker:
    def __init__(self,repository):self.repository=repository

    def claim(self):
        repo=self.repository;now=repo.clock()
        with repo.sessions() as session:
            expired=session.execute(select(jobs.c.learner_id,jobs.c.id,jobs.c.claim_id).where(jobs.c.state=='running',
                jobs.c.attempts>=3,jobs.c.claim_until<=now).limit(32)).all()
            candidates=session.execute(select(jobs).where(jobs.c.attempts<3,or_(jobs.c.state=='queued',
                and_(jobs.c.state=='running',jobs.c.claim_until<=now),and_(jobs.c.state=='failed',jobs.c.retry_at<=now)))
                .order_by(jobs.c.created_at,jobs.c.id).limit(32)).mappings().all()
        for owner,identifier,claim in expired:
            with repo.transactions.try_write(owner) as tx:
                if tx is not None:
                    tx._session.execute(update(jobs).where(jobs.c.learner_id==owner,jobs.c.id==identifier,jobs.c.claim_id==claim,
                        jobs.c.claim_until<=now).values(state='failed',claim_id=None,claim_until=None,retry_at=None))
        for row in candidates:
            with repo.transactions.try_write(row['learner_id']) as tx:
                if tx is None:continue
                claim=str(uuid4())
                value=tx._session.execute(update(jobs).where(jobs.c.learner_id==row['learner_id'],jobs.c.id==row['id'],
                    jobs.c.attempts==row['attempts'],jobs.c.state==row['state']).values(state='running',claim_id=claim,
                        claim_until=now+timedelta(seconds=60),attempts=row['attempts']+1).returning(jobs)).mappings().first()
                if value:return dict(value)
        return None

    def complete(self,job):
        repo=self.repository;owner=job['learner_id']
        with repo.transactions.write(owner) as tx:
            session=tx._session
            live=session.execute(select(jobs).where(jobs.c.learner_id==owner,jobs.c.id==job['id'])).mappings().first()
            if not live or live['state']=='applied':return
            if live['claim_id']!=job['claim_id'] or live['claim_until']<=repo.clock():return
            from .store import observe,refresh_many
            if job['kind']=='outcome':
                from app.assessments.repositories.tables import attempts
                attempt=session.execute(select(attempts).where(attempts.c.learner_id==owner,
                    attempts.c.id==job['payload']['attempt_id'])).mappings().first()
                if attempt and attempt['grade_revision']==job['payload']['grade_revision'] and attempt['state']=='graded':
                    paper=repo._assessment(session,owner,attempt['assessment_id'])
                    observe(repo,session,dict(owner=owner,id=attempt['id'],grade_revision=attempt['grade_revision'],
                        assessment=paper,attempt=attempt),attempt['evidence_receipt'])
            elif job['kind']=='refresh':
                refresh_many(session,owner,{item['key']:item['dimensions'] for item in job['payload']['scopes']},repo.clock())
            else:raise ValueError('Unknown challenge job kind')
            session.execute(update(jobs).where(jobs.c.learner_id==owner,jobs.c.id==job['id'],jobs.c.claim_id==job['claim_id'])
                .values(state='applied',claim_id=None,claim_until=None,retry_at=None))

    def fail(self,job):
        repo=self.repository
        with repo.transactions.write(job['learner_id']) as tx:
            tx._session.execute(update(jobs).where(jobs.c.learner_id==job['learner_id'],jobs.c.id==job['id'],
                jobs.c.claim_id==job['claim_id']).values(state='failed',claim_id=None,claim_until=None,
                    retry_at=repo.clock()+timedelta(seconds=5*2**job['attempts']) if job['attempts']<3 else None))

    async def run_once(self):
        if not settings.learner_challenge_capture_enabled:return False
        job=await run_in_threadpool(self.claim)
        if not job:return False
        try:await run_in_threadpool(self.complete,job)
        except Exception as error:
            await run_in_threadpool(self.fail,job)
            workflow_logger.event('challenge.update_failed',error_type=type(error).__name__)
        return True
