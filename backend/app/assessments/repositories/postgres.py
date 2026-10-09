from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, func, and_, or_
from app.core.exceptions import AppError
from app.db.owner_transactions import OwnerTransactions
from app.history_management.repositories.events.postgres import request_hash
from app.assessments.schemas import Assessment, Attempt, PublicQuestion
from .tables import assessments as a, attempts as t


class AssessmentRepository:
    def __init__(self, sessions, clock=None):
        self.sessions, self.transactions = sessions, OwnerTransactions(sessions)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _assessment(self, session, owner, identifier):
        row = session.execute(select(a).where(a.c.learner_id == owner, a.c.id == identifier)).mappings().first()
        if not row: raise AppError('ASSESSMENT_NOT_FOUND', 'Assessment unavailable.', 404)
        return dict(row)

    def _attempt(self, session, owner, identifier):
        row = session.execute(select(t).where(t.c.learner_id == owner, t.c.id == identifier)).mappings().first()
        if not row: raise AppError('ATTEMPT_NOT_FOUND', 'Assessment attempt unavailable.', 404)
        return dict(row)

    def public(self, row):
        return Assessment(**{key:row[key] for key in ('id','context_id','title','purpose','revision','created_at','sources')},
            questions=[PublicQuestion.model_validate({key:value for key,value in question.items() if key not in ('model_answer','rubric')}) for question in row['questions']])

    def attempt_public(self, row):
        return Attempt(**{key:row[key] for key in ('id','assessment_id','revision','state','attempt_number','answers','grades','extraction','error','evidence_status','created_at')}, grade_revision=row.get('grade_revision',1),grade_history=row.get('grade_history',[]))

    def replay(self, owner, request):
        with self.sessions() as session:
            row = session.execute(select(a).where(a.c.learner_id == owner, a.c.operation_id == str(request.client_request_id))).mappings().first()
            if row and row['fingerprint'] != request_hash(request.model_dump(mode='json')):
                raise AppError('OPERATION_CONFLICT', 'This request ID already belongs to another assessment.', 409)
            return self.public(row) if row else None

    def save(self, owner, request, generated, sources):
        with self.transactions.write(owner) as tx:
            session = tx._session
            previous = session.execute(select(a).where(a.c.learner_id == owner, a.c.operation_id == str(request.client_request_id))).mappings().first()
            fingerprint = request_hash(request.model_dump(mode='json'))
            if previous:
                if previous['fingerprint'] != fingerprint: raise AppError('OPERATION_CONFLICT', 'Request changed.', 409)
                return self.public(previous)
            if session.scalar(select(func.count()).select_from(a).where(a.c.learner_id == owner)) >= 200:
                raise AppError('ASSESSMENT_CAPACITY', 'Delete unused assessments before adding more.', 409)
            questions = [dict(question.model_dump(mode='json'), id=str(uuid4())) for question in generated.questions]
            row = dict(id=str(uuid4()), learner_id=owner, context_id=request.context_id, title=generated.title,
                purpose=request.purpose, revision=1, created_at=self.clock(), questions=questions, sources=sources,
                operation_id=str(request.client_request_id), fingerprint=fingerprint)
            session.execute(a.insert().values(**row))
            return self.public(row)

    def detail(self, owner, identifier):
        with self.sessions() as session: return self.public(self._assessment(session, owner, identifier))

    def list(self, owner, offset=0):
        with self.sessions() as session:
            rows = session.execute(select(a).where(a.c.learner_id == owner).order_by(a.c.created_at.desc(), a.c.id).offset(offset).limit(21)).mappings().all()
            return dict(items=[self.public(row) for row in rows[:20]], next_offset=offset+20 if len(rows)>20 else None)

    def start(self, owner, identifier, body):
        with self.transactions.write(owner) as tx:
            session = tx._session
            self._assessment(session, owner, identifier)
            existing = session.execute(select(t).where(t.c.learner_id == owner, t.c.operation_id == str(body.client_request_id))).mappings().first()
            if existing:
                if existing['assessment_id'] != identifier: raise AppError('OPERATION_CONFLICT', 'Request ID belongs to another assessment.', 409)
                return self.attempt_public(existing)
            count = session.scalar(select(func.count()).select_from(t).where(t.c.learner_id == owner, t.c.assessment_id == identifier))
            if count >= 20: raise AppError('ATTEMPT_CAPACITY', 'This assessment has reached its attempt limit.', 409)
            row = dict(id=str(uuid4()), learner_id=owner, assessment_id=identifier, operation_id=str(body.client_request_id),
                attempt_number=count+1, revision=1, state='draft', created_at=self.clock(), answers={}, grades=None,
                extraction=None, error=None, worker_attempts=0, evidence_status='none')
            session.execute(t.insert().values(**row))
            return self.attempt_public(row)

    def attempt(self, owner, identifier):
        with self.sessions() as session: return self.attempt_public(self._attempt(session, owner, identifier))

    def attempts(self, owner, assessment_id):
        with self.sessions() as session:
            self._assessment(session, owner, assessment_id)
            return [self.attempt_public(row) for row in session.execute(select(t).where(t.c.learner_id == owner,
                t.c.assessment_id == assessment_id).order_by(t.c.attempt_number.desc()).limit(20)).mappings()]

    def submit(self, owner, identifier, body):
        with self.transactions.write(owner) as tx:
            session = tx._session
            row = self._attempt(session, owner, identifier)
            digest = request_hash(body.answers)
            if row['submission_id']:
                if row['submission_id'] == str(body.client_request_id) and row['submission_hash'] == digest:
                    return self.attempt_public(row)
                raise AppError('ATTEMPT_ALREADY_SUBMITTED', 'This attempt already has a submitted answer set.', 409)
            if row['revision'] != body.expected_revision or row['state'] not in ('draft','pending_transcription'):
                raise AppError('REVISION_CONFLICT', 'This attempt changed. Reload before submitting.', 409)
            questions = self._assessment(session, owner, row['assessment_id'])['questions']
            if set(body.answers) != {q['id'] for q in questions} or any(not answer.strip() or len(answer)>8000 for answer in body.answers.values()):
                raise AppError('ASSESSMENT_INCOMPLETE', 'Answer every question with at most 8000 characters each.', 422)
            values = dict(answers=body.answers, state='submitted', revision=row['revision']+1, submitted_at=self.clock(),
                submission_id=str(body.client_request_id), submission_hash=digest, evidence_status='pending', error=None)
            session.execute(update(t).where(t.c.id == identifier).values(**values))
            from app.langchain.repositories.checkpoint_tables import delete_thread
            delete_thread(session, f'assessment-transcription-v1:{owner}:{identifier}')
            return self.attempt_public(dict(row, **values))

    def store_extraction(self, owner, identifier, expected_revision, extraction, data, filename):
        with self.transactions.write(owner) as tx:
            row = self._attempt(tx._session, owner, identifier)
            if row['revision'] != expected_revision or row['state'] not in ('draft','pending_transcription'):
                raise AppError('REVISION_CONFLICT', 'This attempt changed. Reload before uploading.', 409)
            values = dict(extraction=extraction, source=data, filename=filename, state='pending_transcription', revision=row['revision']+1)
            tx._session.execute(update(t).where(t.c.id == identifier).values(**values))
            return self.attempt_public(dict(row, **values))

    def correct(self, owner, identifier, body):
        with self.transactions.write(owner) as tx:
            session=tx._session
            row=self._attempt(session,owner,identifier)
            digest=request_hash(body.answers)
            if row['submission_id']==str(body.client_request_id) and row['submission_hash']==digest:
                return self.attempt_public(row)
            if row['state']!='graded' or row['revision']!=body.expected_revision:
                raise AppError('REVISION_CONFLICT','Only the current graded attempt can be corrected.',409)
            questions=self._assessment(session,owner,row['assessment_id'])['questions']
            if set(body.answers)!={question['id'] for question in questions} or any(not answer.strip() or len(answer)>8000 for answer in body.answers.values()):
                raise AppError('ASSESSMENT_INCOMPLETE','Review every answer before submitting a correction.',422)
            if row['extraction'] and not body.transcription_confirmed:
                raise AppError('TRANSCRIPTION_CONFIRMATION_REQUIRED','Confirm the corrected transcription.',422)
            history=[*row['grade_history'],dict(grade_revision=row['grade_revision'],grades=row['grades'],answers=row['answers'],corrected_at=self.clock().isoformat())]
            if len(history)>10:raise AppError('CORRECTION_LIMIT','This attempt has reached its correction limit.',409)
            values=dict(grade_history=history,grade_revision=row['grade_revision']+1,answers=body.answers,grades=None,
                revision=row['revision']+1,state='submitted',submitted_at=self.clock(),worker_attempts=0,retry_at=None,
                submission_id=str(body.client_request_id),submission_hash=digest,evidence_status='pending',error=None)
            session.execute(update(t).where(t.c.id==identifier).values(**values))
            return self.attempt_public(dict(row,**values))

    def claim(self):
        now = self.clock()
        with self.sessions.begin() as session:
            session.execute(update(t).where(t.c.state == 'grading', t.c.claim_until <= now, t.c.worker_attempts >= 3).values(
                state='failed', error='Grading could not complete. Please retry this assessment.', claim_id=None,
                claim_until=None, retry_at=None, revision=t.c.revision+1))
            candidate = session.execute(select(t.c.id, t.c.learner_id).where(t.c.worker_attempts < 3,
                or_(t.c.state == 'submitted', and_(t.c.state == 'grading', t.c.claim_until <= now),
                    and_(t.c.state == 'failed', t.c.retry_at <= now))).order_by(t.c.created_at).limit(1)).first()
        if not candidate: return None
        identifier, owner = candidate
        with self.transactions.write(owner) as tx:
            row = self._attempt(tx._session, owner, identifier)
            eligible = row['state'] == 'submitted' or (row['state'] == 'grading' and row['claim_until'] and row['claim_until'] <= now) or (row['state'] == 'failed' and row['retry_at'] and row['retry_at'] <= now)
            if not eligible or row['worker_attempts'] >= 3: return None
            token = str(uuid4())
            tx._session.execute(update(t).where(t.c.id == identifier).values(state='grading', claim_id=token,
                claim_until=now+timedelta(seconds=120), worker_attempts=row['worker_attempts']+1))
            return dict(owner=owner, id=identifier, claim_id=token, attempt=dict(row, worker_attempts=row['worker_attempts']+1),
                assessment=self._assessment(tx._session, owner, row['assessment_id']))

    def complete(self, job, grades, apply_evidence):
        with self.transactions.write(job['owner']) as tx:
            row = self._attempt(tx._session, job['owner'], job['id'])
            if row['claim_id'] != job['claim_id'] or row['state'] != 'grading' or row['claim_until'] <= self.clock():
                raise AppError('ATTEMPT_CLAIM_EXPIRED', 'Grading lease expired.', 409)
            receipt = apply_evidence(tx) if all(q.confidence >= .8 and all(g.confidence >= .8 for g in q.concept_grades.values()) for q in grades.questions) else None
            tx._session.execute(update(t).where(t.c.id == job['id']).values(state='graded', grades=grades.model_dump(mode='json')['questions'],
                evidence_status='applied' if receipt else 'unavailable', evidence_receipt=receipt,
                revision=row['revision']+1, claim_id=None, claim_until=None, retry_at=None, error=None))

    def fail(self, job):
        with self.transactions.write(job['owner']) as tx:
            row = self._attempt(tx._session, job['owner'], job['id'])
            if row['claim_id'] != job['claim_id']: return
            tx._session.execute(update(t).where(t.c.id == job['id']).values(state='failed', error='Grading is temporarily unavailable.',
                retry_at=self.clock()+timedelta(seconds=5*2**row['worker_attempts']), claim_id=None, claim_until=None, revision=row['revision']+1))

    def remove(self, owner, identifier):
        with self.transactions.write(owner) as tx:
            self._assessment(tx._session, owner, identifier)
            from app.langchain.repositories.checkpoint_tables import delete_thread
            for attempt_id in tx._session.execute(select(t.c.id).where(t.c.learner_id == owner, t.c.assessment_id == identifier)).scalars():
                delete_thread(tx._session, f'assessment-transcription-v1:{owner}:{attempt_id}')
            tx._session.execute(delete(a).where(a.c.learner_id == owner, a.c.id == identifier))
