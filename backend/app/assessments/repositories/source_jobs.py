"""Durable, owned source requests. Worker leases fence job status and attempts."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, func, or_, and_
from app.core.exceptions import AppError
from .tables import source_jobs as j

LEASE_SECONDS = 900


class SourceJobs:
    def __init__(self, repository):
        self.repo = repository

    def public(self, row):
        return dict(id=row['id'], state=row['state'], error=row['error'],
            attempt_id=row['attempt_id'], retry_pending=bool(row['retry_at']),
            attempt=self.repo.attempt(row['learner_id'],row['attempt_id']).model_dump(mode='json') if row['state']=='completed' else None)

    def enqueue(self, owner, attempt_id, file_id, revision, *, from_chat=False):
        self.repo.files.metadata(owner, file_id, 'chat' if from_chat else 'assessment')
        with self.repo.transactions.write(owner) as tx:
            # Serialize publication with file cleanup; never queue a deleted asset.
            from app.files.tables import assets
            file = tx._session.execute(select(assets).where(assets.c.id==file_id,
                assets.c.learner_id==owner).with_for_update()).mappings().first()
            if not file or file['state'] not in ('STAGED','ACTIVE'):
                raise AppError('FILES_NOT_FOUND','This file is no longer available.',404)
            row = tx._session.execute(select(j).where(j.c.learner_id==owner,j.c.attempt_id==attempt_id,
                j.c.file_id==file_id,j.c.expected_revision==revision)).mappings().first()
            if row and row['state'] != 'failed':
                identifier = row['id']
            else:
                attempt = self.repo._attempt(tx._session,owner,attempt_id)
                if attempt['revision'] != revision or attempt['state'] not in ('draft','pending_transcription'):
                    raise AppError('REVISION_CONFLICT','This attempt changed. Reload before uploading.',409)
                if tx._session.scalar(select(func.count()).select_from(j).where(j.c.learner_id==owner,
                    j.c.state.in_(['queued','running']))) >= 2:
                    raise AppError('ASSESSMENT_SOURCE_BUSY','Let your current answer sheets finish first.',429)
                if row:
                    if row['manual_retries'] >= 3:
                        raise AppError('ASSESSMENT_RETRY_LIMIT','This upload reached its retry limit.',409)
                    identifier = row['id']
                    tx._session.execute(update(j).where(j.c.id==identifier).values(state='queued',attempts=0,
                        manual_retries=row['manual_retries']+1,claim_id=None,claim_until=None,retry_at=None,error=None))
                else:
                    identifier = str(uuid4())
                    tx._session.execute(j.insert().values(id=identifier,learner_id=owner,attempt_id=attempt_id,
                        file_id=file_id,expected_revision=revision,from_chat=from_chat,state='queued',created_at=self.repo.clock()))
        return self.get(owner,identifier)

    def get(self, owner, identifier):
        with self.repo.sessions() as session:
            row = session.execute(select(j).where(j.c.learner_id==owner,j.c.id==identifier)).mappings().first()
        if not row:
            raise AppError('ASSESSMENT_SOURCE_NOT_FOUND','This answer-sheet request is unavailable.',404)
        return self.public(row)

    def claim(self):
        now = self.repo.clock()
        with self.repo.sessions.begin() as session:
            session.execute(update(j).where(j.c.state=='running',j.c.claim_until<=now,j.c.attempts>=3)
                .values(state='failed',claim_id=None,claim_until=None,retry_at=None,error='Extraction was interrupted. Retry this upload.'))
            row = session.execute(select(j).where(j.c.attempts<3,or_(j.c.state=='queued',
                and_(j.c.state=='running',j.c.claim_until<=now),and_(j.c.state=='failed',j.c.retry_at<=now)))
                .order_by(j.c.created_at,j.c.id).with_for_update(skip_locked=True).limit(1)).mappings().first()
            if not row: return None
            values = dict(state='running',attempts=row['attempts']+1,claim_id=str(uuid4()),
                claim_until=now+timedelta(seconds=LEASE_SECONDS),retry_at=None)
            session.execute(update(j).where(j.c.id==row['id']).values(**values))
            return dict(row,**values)

    def finish(self, job, error=None, retry=False, deferred=False):
        with self.repo.sessions.begin() as session:
            session.execute(update(j).where(j.c.id==job['id'],j.c.claim_id==job['claim_id'],
                j.c.state=='running',j.c.claim_until>self.repo.clock()).values(
                    state='failed' if error else 'completed',error=error,claim_id=None,claim_until=None,
                    attempts=max(0,job['attempts']-1) if deferred else job['attempts'],
                    retry_at=self.repo.clock()+timedelta(seconds=5 if deferred else 5*2**job['attempts']) if deferred or retry and job['attempts']<3 else None))

    def active(self, job):
        with self.repo.sessions() as session:
            return bool(session.scalar(select(j.c.id).where(j.c.id==job['id'],j.c.claim_id==job['claim_id'],
                j.c.state=='running',j.c.claim_until>self.repo.clock())))
