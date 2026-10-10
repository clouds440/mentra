from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, func, and_, or_
from app.core.exceptions import AppError
from app.db.owner_transactions import OwnerTransactions
from app.history_management.repositories.events.postgres import request_hash
from app.assessments.schemas import Assessment, Attempt, PublicQuestion
from .tables import assessments as a, attempts as t, generation_claims as g

# Upload bytes are only needed when explicitly reading the original artifact.
# Polling, claiming and corrections must not download them from PostgreSQL.
ATTEMPT_COLUMNS = [column for column in t.c if column.name != 'source']


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={'claim': {'quiet':True},
    'correct': {'request_outcome': True, 'result': lambda value: dict(domain_status=value.state),
                'outcome': lambda value: 'deferred' if value.state in ('submitted','grading') else 'success'},
})
class AssessmentRepository:
    def __init__(self, sessions, clock=None):
        self.sessions, self.transactions = sessions, OwnerTransactions(sessions)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _assessment(self, session, owner, identifier):
        row = session.execute(select(a).where(a.c.learner_id == owner, a.c.id == identifier)).mappings().first()
        if not row: raise AppError('ASSESSMENT_NOT_FOUND', 'Assessment unavailable.', 404)
        return dict(row)

    def profile_version(self, session, owner):
        from app.student_profile.repositories.tables import student_profile
        return session.scalar(select(student_profile.c.context_version).where(student_profile.c.learner_id == owner))

    def _attempt(self, session, owner, identifier):
        row = session.execute(select(*ATTEMPT_COLUMNS).where(t.c.learner_id == owner, t.c.id == identifier)).mappings().first()
        if not row: raise AppError('ATTEMPT_NOT_FOUND', 'Assessment attempt unavailable.', 404)
        return dict(row)

    def public(self, row):
        return Assessment(**{key:row[key] for key in ('id','context_id','title','purpose','revision','created_at','sources')},
            questions=[PublicQuestion.model_validate({key:value for key,value in question.items() if key not in ('model_answer','rubric')}) for question in row['questions']])

    def attempt_public(self, row):
        return Attempt(**{key:row[key] for key in ('id','assessment_id','revision','state','attempt_number','answers','grades','extraction','error','evidence_status','created_at')}, grade_revision=row.get('grade_revision',1),grade_history=row.get('grade_history',[]), assistance=row.get('assistance','unknown'), retry_pending=bool(row.get('retry_at') and row.get('worker_attempts',0)<3))

    def claim_generation(self, owner, request):
        with self.transactions.write(owner) as tx:
            operation = str(request.client_request_id)
            fingerprint = request_hash(request.fingerprint_payload())
            row = tx._session.execute(select(g).where(g.c.learner_id == owner, g.c.operation_id == operation)).mappings().first()
            if row:
                if row['fingerprint'] != fingerprint:
                    raise AppError('OPERATION_CONFLICT', 'Request changed.', 409)
                if row['claim_until'] > self.clock():
                    raise AppError('ASSESSMENT_GENERATING', 'This assessment is already being generated. Retry the same request shortly.', 409)
            token = str(uuid4())
            values = dict(learner_id=owner, operation_id=operation, fingerprint=fingerprint,
                          claim_id=token, claim_until=self.clock()+timedelta(seconds=180))
            from sqlalchemy.dialects.postgresql import insert
            tx._session.execute(insert(g).values(**values).on_conflict_do_update(index_elements=['learner_id','operation_id'], set_=values))
            return token

    def release_generation(self, owner, operation, token):
        with self.transactions.write(owner) as tx:
            tx._session.execute(delete(g).where(g.c.learner_id == owner, g.c.operation_id == str(operation), g.c.claim_id == token))

    def replay(self, owner, request):
        with self.sessions() as session:
            row = session.execute(select(a).where(a.c.learner_id == owner, a.c.operation_id == str(request.client_request_id))).mappings().first()
            if row and row['fingerprint'] != request_hash(request.fingerprint_payload()):
                raise AppError('OPERATION_CONFLICT', 'This request ID already belongs to another assessment.', 409)
            return self.public(row) if row else None

    def save(self, owner, request, generated, sources, claim_id=None):
        with self.transactions.write(owner) as tx:
            session = tx._session
            previous = session.execute(select(a).where(a.c.learner_id == owner, a.c.operation_id == str(request.client_request_id))).mappings().first()
            fingerprint = request_hash(request.fingerprint_payload())
            if previous:
                if previous['fingerprint'] != fingerprint: raise AppError('OPERATION_CONFLICT', 'Request changed.', 409)
                return self.public(previous)
            if claim_id is not None:
                claim = session.execute(select(g).where(g.c.learner_id == owner, g.c.operation_id == str(request.client_request_id))).mappings().first()
                if not claim or claim['claim_id'] != claim_id or claim['claim_until'] <= self.clock():
                    raise AppError('ASSESSMENT_GENERATION_EXPIRED', 'Generation ownership expired. Retry the same request.', 409)
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

    def start(self, owner, identifier, body, *, fingerprint=None):
        with self.transactions.write(owner) as tx:
            session = tx._session
            self._assessment(session, owner, identifier)
            existing = session.execute(select(*ATTEMPT_COLUMNS).where(t.c.learner_id == owner, t.c.operation_id == str(body.client_request_id))).mappings().first()
            if existing:
                if existing['assessment_id'] != identifier: raise AppError('OPERATION_CONFLICT', 'Request ID belongs to another assessment.', 409)
                if fingerprint != existing.get('start_fingerprint'):
                    raise AppError('OPERATION_CONFLICT', 'The answers for this request changed.', 409)
                return self.attempt_public(existing)
            count = session.scalar(select(func.count()).select_from(t).where(t.c.learner_id == owner, t.c.assessment_id == identifier))
            if count >= 20: raise AppError('ATTEMPT_CAPACITY', 'This assessment has reached its attempt limit.', 409)
            row = dict(id=str(uuid4()), learner_id=owner, assessment_id=identifier, operation_id=str(body.client_request_id),
                attempt_number=count+1, revision=1, state='draft', created_at=self.clock(), answers={}, grades=None,
                extraction=None, error=None, worker_attempts=0, evidence_status='none', start_fingerprint=fingerprint)
            session.execute(t.insert().values(**row))
            return self.attempt_public(row)

    def store_chat_answers(self, owner, identifier, expected_revision, answers, message_id, fingerprint):
        """Merge verbatim chat work without discarding upload provenance or prior answers."""
        with self.transactions.write(owner) as tx:
            row = self._attempt(tx._session, owner, identifier)
            inputs = dict(row.get('chat_inputs') or {})
            if message_id in inputs:
                if inputs[message_id] != fingerprint:
                    raise AppError('OPERATION_CONFLICT', 'The answers for this message changed.', 409)
                return self.attempt_public(row)
            if row['revision'] != expected_revision or row['state'] not in ('draft', 'pending_transcription'):
                raise AppError('REVISION_CONFLICT', 'This attempt changed. Reload before adding answers.', 409)
            if len(inputs) >= 30:
                raise AppError('CHAT_ANSWER_LIMIT', 'Review and submit this attempt before adding more messages.', 409)
            extraction = dict(row['extraction'] or dict(warnings=[], requires_confirmation=True,
                handwriting_support='typed_chat', reader_revision='chat-verbatim-v1',
                extraction_confidence=1, mapping_confidence=1, text='', truncated=False))
            extraction['answers'] = dict(extraction.get('answers') or {}, **answers)
            inputs[message_id] = fingerprint
            values = dict(extraction=extraction, chat_inputs=inputs, state='pending_transcription', revision=row['revision']+1)
            tx._session.execute(update(t).where(t.c.id == identifier).values(**values))
            return self.attempt_public(dict(row, **values))

    def chat_answer_replay(self, owner, assessment_id, message_id, fingerprint):
        with self.sessions() as session:
            row = session.execute(select(*ATTEMPT_COLUMNS).where(t.c.learner_id == owner,
                t.c.assessment_id == assessment_id, t.c.chat_inputs.has_key(message_id))).mappings().first()
            if row and row['chat_inputs'][message_id] != fingerprint:
                raise AppError('OPERATION_CONFLICT', 'The answers for this message changed.', 409)
            return self.attempt_public(row) if row else None

    def attempt(self, owner, identifier):
        with self.sessions() as session: return self.attempt_public(self._attempt(session, owner, identifier))

    def attempts(self, owner, assessment_id):
        with self.sessions() as session:
            self._assessment(session, owner, assessment_id)
            return [self.attempt_public(row) for row in session.execute(select(*ATTEMPT_COLUMNS).where(t.c.learner_id == owner,
                t.c.assessment_id == assessment_id).order_by(t.c.attempt_number.desc()).limit(20)).mappings()]

    def submit(self, owner, identifier, body):
        with self.transactions.write(owner) as tx:
            session = tx._session
            row = self._attempt(session, owner, identifier)
            digest = request_hash(body.answers if body.assistance == 'unknown' else dict(answers=body.answers, assistance=body.assistance))
            if row['submission_id']:
                if row['submission_id'] == str(body.client_request_id) and row['submission_hash'] == digest:
                    return self.attempt_public(row)
                raise AppError('ATTEMPT_ALREADY_SUBMITTED', 'This attempt already has a submitted answer set.', 409)
            if row['revision'] != body.expected_revision or row['state'] not in ('draft','pending_transcription'):
                raise AppError('REVISION_CONFLICT', 'This attempt changed. Reload before submitting.', 409)
            if row['extraction'] and not body.transcription_confirmed:
                raise AppError('TRANSCRIPTION_CONFIRMATION_REQUIRED', 'Confirm the reviewed answer transcription.', 422)
            questions = self._assessment(session, owner, row['assessment_id'])['questions']
            if set(body.answers) != {q['id'] for q in questions} or any(not answer.strip() or len(answer)>8000 for answer in body.answers.values()):
                raise AppError('ASSESSMENT_INCOMPLETE', 'Answer every question with at most 8000 characters each.', 422)
            values = dict(answers=body.answers, state='submitted', revision=row['revision']+1, submitted_at=self.clock(),
                profile_context_version=self.profile_version(session, owner),
                submission_id=str(body.client_request_id), submission_hash=digest, evidence_status='pending', assistance=body.assistance, error=None, log_context=workflow_logger.envelope())
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
            digest=request_hash(body.answers if body.assistance == 'unknown' else dict(answers=body.answers, assistance=body.assistance))
            if row['submission_id']==str(body.client_request_id) and row['submission_hash']==digest:
                return self.attempt_public(row)
            if row['state']!='graded' or row['revision']!=body.expected_revision:
                raise AppError('REVISION_CONFLICT','Only the current graded attempt can be corrected.',409)
            questions=self._assessment(session,owner,row['assessment_id'])['questions']
            if set(body.answers)!={question['id'] for question in questions} or any(not answer.strip() or len(answer)>8000 for answer in body.answers.values()):
                raise AppError('ASSESSMENT_INCOMPLETE','Review every answer before submitting a correction.',422)
            if row['extraction'] and not body.transcription_confirmed:
                raise AppError('TRANSCRIPTION_CONFIRMATION_REQUIRED','Confirm the corrected transcription.',422)
            history=[*row['grade_history'],dict(grade_revision=row['grade_revision'],grades=row['grades'],answers=row['answers'],assistance=row.get('assistance','unknown'),corrected_at=self.clock().isoformat())]
            if len(history)>10:raise AppError('CORRECTION_LIMIT','This attempt has reached its correction limit.',409)
            values=dict(grade_history=history,grade_revision=row['grade_revision']+1,answers=body.answers,grades=None,
                profile_context_version=self.profile_version(session, owner),
                revision=row['revision']+1,state='submitted',submitted_at=self.clock(),worker_attempts=0,retry_at=None,
                submission_id=str(body.client_request_id),submission_hash=digest,evidence_status='pending',assistance=body.assistance,error=None,log_context=workflow_logger.envelope())
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
                assessment=self._assessment(tx._session, owner, row['assessment_id']), profile_context_version=row['profile_context_version'])

    def complete(self, job, grades, apply_evidence):
        with self.transactions.write(job['owner']) as tx:
            row = self._attempt(tx._session, job['owner'], job['id'])
            if row['claim_id'] != job['claim_id'] or row['state'] != 'grading' or row['claim_until'] <= self.clock():
                raise AppError('ATTEMPT_CLAIM_EXPIRED', 'Grading lease expired.', 409)
            # The evidence producer admits each observation independently and
            # withdraws obsolete evidence even when a corrected grade is uncertain.
            receipt = apply_evidence(tx)
            expected = sum(len(question.concept_grades) for question in grades.questions)
            accepted = sum(bool(item.get('accepted')) for item in receipt or [])
            evidence_status = 'applied' if accepted == expected else 'partial' if accepted else 'unavailable'
            tx._session.execute(update(t).where(t.c.id == job['id']).values(state='graded', grades=grades.model_dump(mode='json')['questions'],
                evidence_status=evidence_status, evidence_receipt=receipt,
                revision=row['revision']+1, claim_id=None, claim_until=None, retry_at=None, error=None))

    def fail(self, job, *, retry=True):
        with self.transactions.write(job['owner']) as tx:
            row = self._attempt(tx._session, job['owner'], job['id'])
            if row['claim_id'] != job['claim_id']: return
            tx._session.execute(update(t).where(t.c.id == job['id']).values(state='failed', error='Grading is temporarily unavailable.',
                retry_at=self.clock()+timedelta(seconds=5*2**row['worker_attempts']) if retry else None, claim_id=None, claim_until=None, revision=row['revision']+1))
        workflow_logger.event('job.retry_scheduled' if retry and row['worker_attempts'] < 3 else 'job.failed', job_id=job['id'], attempt=row['worker_attempts'])

    def remove(self, owner, identifier):
        with self.transactions.write(owner) as tx:
            self._assessment(tx._session, owner, identifier)
            from app.langchain.repositories.checkpoint_tables import delete_thread
            for attempt_id in tx._session.execute(select(t.c.id).where(t.c.learner_id == owner, t.c.assessment_id == identifier)).scalars():
                delete_thread(tx._session, f'assessment-transcription-v1:{owner}:{attempt_id}')
            tx._session.execute(delete(a).where(a.c.learner_id == owner, a.c.id == identifier))
