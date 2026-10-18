"""Owner-scoped, lease-fenced generation with private per-batch checkpoints."""
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select, update, or_, func
from app.core.exceptions import AppError
from app.history_management.repositories.events.postgres import request_hash
from .tables import generation_jobs as jobs


class GenerationJobs:
    def __init__(self, repository): self.repository = repository

    def public(self, row):
        progress = row['progress'] or {}
        return dict(id=row['id'], state=row['state'], title=(progress.get('resolved_request') or row['request']).get('topic') or 'Your assessment',
            completed_parts=len(progress.get('questions', [])), total_parts=len(progress.get('plan', [])) or None,
            result=row['result'], error=row['error'], can_retry=row['state']=='failed')

    def enqueue(self, owner, request, conversation=None):
        fingerprint = request_hash(dict(request=request.fingerprint_payload(), conversation=conversation))
        with self.repository.transactions.write(owner) as tx:
            session = tx._session
            if conversation:
                from .chat import ChatAssessmentRepository
                ChatAssessmentRepository(self.repository)._conversation(session, owner, conversation)
            row = session.execute(select(jobs).where(jobs.c.learner_id==owner, jobs.c.operation_id==str(request.client_request_id))).mappings().first()
            if row:
                if row['fingerprint'] != fingerprint:
                    raise AppError('OPERATION_CONFLICT', 'This request ID belongs to a different assessment.', 409)
                return self.public(row)
            if session.scalar(select(func.count()).select_from(jobs).where(jobs.c.learner_id==owner, jobs.c.state.in_(['queued','running']))) >= 2:
                raise AppError('ASSESSMENT_GENERATION_BUSY', 'Let your current assessments finish before starting another.', 409)
            row = dict(id=str(uuid4()), learner_id=owner, operation_id=str(request.client_request_id), fingerprint=fingerprint,
                conversation_id=conversation, request=request.model_dump(mode='json'), state='queued', progress={}, result=None,
                error=None, attempts=0, claim_id=None, claim_until=None, created_at=self.repository.clock())
            session.execute(jobs.insert().values(**row))
            return self.public(row)

    def replay(self, owner, request, conversation=None):
        fingerprint = request_hash(dict(request=request.fingerprint_payload(), conversation=conversation))
        with self.repository.sessions() as session:
            row = session.execute(select(jobs).where(jobs.c.learner_id==owner,
                jobs.c.operation_id==str(request.client_request_id))).mappings().first()
            if not row: return None
            if row['fingerprint'] != fingerprint:
                raise AppError('OPERATION_CONFLICT', 'This request ID belongs to a different assessment.', 409)
        return self.get(owner, row['id'])

    def get(self, owner, identifier):
        with self.repository.sessions() as session:
            row = session.execute(select(jobs).where(jobs.c.id==identifier, jobs.c.learner_id==owner)).mappings().first()
            if not row: raise AppError('ASSESSMENT_JOB_NOT_FOUND', 'Assessment generation unavailable.', 404)
            if row['conversation_id']:
                from app.chat.repositories.tables import conversations
                if not session.scalar(select(conversations.c.id).where(conversations.c.id==row['conversation_id'], conversations.c.learner_id==owner, conversations.c.deleted_at.is_(None))):
                    raise AppError('ASSESSMENT_JOB_NOT_FOUND', 'Assessment generation unavailable.', 404)
            return self.public(row)

    def retry(self, owner, identifier):
        with self.repository.transactions.write(owner) as tx:
            row = tx._session.execute(select(jobs).where(jobs.c.id==identifier, jobs.c.learner_id==owner).with_for_update()).mappings().first()
            if not row: raise AppError('ASSESSMENT_JOB_NOT_FOUND', 'Assessment generation unavailable.', 404)
            if row['conversation_id']:
                from .chat import ChatAssessmentRepository
                ChatAssessmentRepository(self.repository)._conversation(tx._session, owner, row['conversation_id'])
            if row['state']=='failed':
                if tx._session.scalar(select(func.count()).select_from(jobs).where(jobs.c.learner_id==owner, jobs.c.state.in_(['queued','running']))) >= 2:
                    raise AppError('ASSESSMENT_GENERATION_BUSY', 'Let your current assessments finish before resuming another.', 409)
                tx._session.execute(update(jobs).where(jobs.c.id==identifier).values(state='queued', error=None, attempts=0))
        return self.get(owner, identifier)

    def claim(self):
        now = self.repository.clock()
        with self.repository.sessions.begin() as session:
            row = session.execute(select(jobs).where(or_(jobs.c.state=='queued',
                (jobs.c.state=='running') & (jobs.c.claim_until < now))).order_by(jobs.c.created_at).with_for_update(skip_locked=True).limit(1)).mappings().first()
            if not row: return None
            if row['attempts'] >= 3:
                session.execute(update(jobs).where(jobs.c.id==row['id']).values(state='failed', error='Generation was interrupted repeatedly. Your completed sections are preserved.'))
                return None
            values = dict(state='running', attempts=row['attempts']+1, claim_id=str(uuid4()), claim_until=now+timedelta(seconds=180))
            session.execute(update(jobs).where(jobs.c.id==row['id']).values(**values))
            return dict(row, **values)

    def update(self, job, **values):
        now = self.repository.clock()
        with self.repository.sessions.begin() as session:
            result = session.execute(update(jobs).where(jobs.c.id==job['id'], jobs.c.claim_id==job['claim_id'],
                jobs.c.state=='running', jobs.c.claim_until > now).values(claim_until=now+timedelta(seconds=180), **values))
            if result.rowcount != 1: raise AppError('ASSESSMENT_JOB_EXPIRED', 'Generation ownership changed.', 409)
