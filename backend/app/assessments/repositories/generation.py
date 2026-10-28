"""Owner-scoped, lease-fenced generation with private per-batch checkpoints."""
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select, update, delete, or_, func
from app.core.exceptions import AppError
from app.history_management.repositories.events.postgres import request_hash
from .tables import generation_jobs as jobs


class GenerationJobs:
    def __init__(self, repository): self.repository = repository

    def public(self, row):
        progress = row['progress'] or {}
        expires = row.get('resume_until')
        return dict(id=row['id'], state=row['state'], title=(progress.get('resolved_request') or row['request']).get('topic') or 'Your assessment',
            conversation_id=row.get('conversation_id'), source_turn_id=row.get('source_turn_id'),
            completed_parts=len(progress.get('questions', [])), total_parts=len(progress.get('plan', [])) or None,
            result=row['result'], error=row['error'], can_retry=row['state'] in ('failed', 'stopped'),
            revision=row.get('revision', 1), resume_until=expires,
            can_resume=row['state'] == 'stopped' and bool(expires and expires > self.repository.clock()))

    def enqueue(self, owner, request, conversation=None, source_turn_id=None):
        fingerprint = request_hash(dict(request=request.fingerprint_payload(), conversation=conversation))
        with self.repository.transactions.write(owner) as tx:
            session = tx._session
            if conversation:
                from .chat import ChatAssessmentRepository
                ChatAssessmentRepository(self.repository)._conversation(session, owner, conversation)
            if source_turn_id:
                from app.chat.repositories.tables import turns
                source = session.scalar(select(turns.c.id).where(turns.c.id == source_turn_id,
                    turns.c.learner_id == owner, turns.c.conversation_id == conversation, turns.c.state == 'RUNNING'))
                if not source:
                    raise AppError('CHAT_GENERATION_STOPPED', 'This response was stopped.', 409)
            row = session.execute(select(jobs).where(jobs.c.learner_id==owner, jobs.c.operation_id==str(request.client_request_id))).mappings().first()
            if row:
                if row['fingerprint'] != fingerprint:
                    raise AppError('OPERATION_CONFLICT', 'This request ID belongs to a different assessment.', 409)
                return self.public(row)
            if session.scalar(select(func.count()).select_from(jobs).where(jobs.c.learner_id==owner, jobs.c.state.in_(['queued','running']))) >= 2:
                raise AppError('ASSESSMENT_GENERATION_BUSY', 'Let your current assessments finish before starting another.', 409)
            row = dict(id=str(uuid4()), learner_id=owner, operation_id=str(request.client_request_id), fingerprint=fingerprint,
                conversation_id=conversation, request=request.model_dump(mode='json'), state='queued', progress={}, result=None,
                source_turn_id=source_turn_id, revision=1, resume_until=None,
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
        self.expire_stopped(owner)
        with self.repository.sessions() as session:
            row = session.execute(select(jobs).where(jobs.c.id==identifier, jobs.c.learner_id==owner)).mappings().first()
            if not row: raise AppError('ASSESSMENT_JOB_NOT_FOUND', 'Assessment generation unavailable.', 404)
            if row['conversation_id']:
                from app.chat.repositories.tables import conversations
                if not session.scalar(select(conversations.c.id).where(conversations.c.id==row['conversation_id'], conversations.c.learner_id==owner, conversations.c.deleted_at.is_(None))):
                    raise AppError('ASSESSMENT_JOB_NOT_FOUND', 'Assessment generation unavailable.', 404)
            return self.public(row)

    def retry(self, owner, identifier):
        self.expire_stopped(owner)
        with self.repository.transactions.write(owner) as tx:
            row = tx._session.execute(select(jobs).where(jobs.c.id==identifier, jobs.c.learner_id==owner).with_for_update()).mappings().first()
            if not row: raise AppError('ASSESSMENT_JOB_NOT_FOUND', 'Assessment generation unavailable.', 404)
            if row['conversation_id']:
                from .chat import ChatAssessmentRepository
                ChatAssessmentRepository(self.repository)._conversation(tx._session, owner, row['conversation_id'])
            if row['state'] in ('failed', 'stopped'):
                if tx._session.scalar(select(func.count()).select_from(jobs).where(jobs.c.learner_id==owner, jobs.c.state.in_(['queued','running']))) >= 2:
                    raise AppError('ASSESSMENT_GENERATION_BUSY', 'Let your current assessments finish before resuming another.', 409)
                tx._session.execute(update(jobs).where(jobs.c.id==identifier).values(state='queued', error=None,
                    attempts=0, revision=row['revision'] + 1, resume_until=None, claim_id=None, claim_until=None))
        return self.get(owner, identifier)

    def claim(self):
        now = self.repository.clock()
        self.expire_stopped()
        from app.chat.repositories.postgres import ChatRepository
        ChatRepository(self.repository.sessions).expire_paused()
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

    def active(self, job):
        with self.repository.sessions() as session:
            return bool(session.scalar(select(jobs.c.id).where(jobs.c.id == job['id'],
                jobs.c.learner_id == job['learner_id'], jobs.c.state == 'running',
                jobs.c.claim_id == job['claim_id'], jobs.c.claim_until > self.repository.clock())))

    def expire_stopped(self, owner=None):
        now = self.repository.clock()
        with self.repository.sessions.begin() as session:
            filters = [jobs.c.state == 'stopped', jobs.c.resume_until <= now]
            if owner:
                filters.append(jobs.c.learner_id == owner)
            rows = session.execute(select(jobs.c.id, jobs.c.progress).where(*filters,
                (jobs.c.progress - 'mistake_revision') != {}).limit(100).with_for_update(skip_locked=True)).mappings().all()
            for row in rows:
                # Preserve source-practice provenance; only unfinished generated
                # questions/answers/plans expire, never the original source exam.
                kept = {key: value for key, value in (row['progress'] or {}).items() if key == 'mistake_revision'}
                if kept != row['progress']:
                    session.execute(update(jobs).where(jobs.c.id == row['id'], jobs.c.state == 'stopped').values(progress=kept))

    def stop(self, owner, identifier, expected_revision):
        with self.repository.transactions.write(owner) as tx:
            return self.stop_in_transaction(tx, identifier, expected_revision)

    def stop_in_transaction(self, tx, identifier, expected_revision=None):
        from .tables import assessments, chat_drafts, generation_claims
        owner, session = tx.owner, tx._session
        row = session.execute(select(jobs).where(jobs.c.id == identifier,
            jobs.c.learner_id == owner).with_for_update()).mappings().first()
        if not row:
            raise AppError('ASSESSMENT_JOB_NOT_FOUND', 'Assessment generation unavailable.', 404)
        if row['conversation_id']:
            from .chat import ChatAssessmentRepository
            ChatAssessmentRepository(self.repository)._conversation(session, owner, row['conversation_id'])
        if expected_revision is not None and row['revision'] != expected_revision:
            raise AppError('REVISION_CONFLICT', 'This generation has resumed. Refresh before stopping it.', 409)
        if row['state'] in ('completed', 'stopped'):
            return self.public(row)
        # The owner's publication lock decides the race. A saved result is never
        # relabeled stopped or deleted by a late Stop request.
        draft = session.execute(select(chat_drafts).where(chat_drafts.c.learner_id == owner,
            chat_drafts.c.operation_id == row['operation_id'])).mappings().first()
        saved = session.execute(select(assessments).where(assessments.c.learner_id == owner,
            assessments.c.operation_id == row['operation_id'])).mappings().first()
        if draft or saved:
            if draft:
                from .chat import ChatAssessmentRepository
                result = ChatAssessmentRepository(self.repository).public(draft)
            else:
                result = self.repository.public(saved).model_dump(mode='json')
            values = dict(state='completed', result=result, error=None, claim_id=None, claim_until=None)
        else:
            values = dict(state='stopped', error=None, resume_until=self.repository.clock() + timedelta(minutes=30),
                claim_id=None, claim_until=None)
            session.execute(delete(generation_claims).where(generation_claims.c.learner_id == owner,
                generation_claims.c.operation_id == row['operation_id']))
        session.execute(update(jobs).where(jobs.c.id == identifier).values(**values))
        return self.public(dict(row, **values))
