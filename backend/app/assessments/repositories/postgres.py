from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, func, and_, or_
from app.core.exceptions import AppError
from app.db.owner_transactions import OwnerTransactions
from app.history_management.repositories.events.postgres import request_hash
from app.assessments.schemas import Assessment, Attempt, PublicQuestion, PracticeSource
from .tables import assessments as a, attempts as t, generation_claims as g

# Upload bytes are only needed when explicitly reading the original artifact.
# Polling, claiming and corrections must not download them from PostgreSQL.
ATTEMPT_COLUMNS = [column for column in t.c if column.name not in ('source','grading_progress')]


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
        lineage = row.get('practice_lineage')
        return Assessment(tags=['revision assessment'] if lineage and lineage.get('revision_assessment') else [],
            source_assessment_ids=lineage.get('source_assessment_ids', []) if lineage else [],
            practice_source={key:value for key,value in lineage.items() if key in PracticeSource.model_fields} if lineage else None,
            paper=row.get('paper'), preferences=row.get('preferences') or {}, **{key:row[key] for key in ('id','context_id','title','purpose','revision','created_at','sources')},
            questions=[PublicQuestion.model_validate({key:value for key,value in question.items() if key not in ('model_answer','rubric','correct_option_id','correct_option_ids','concept_names')}) for question in row['questions']])

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

    def renew_generation(self, owner, operation, token):
        with self.transactions.write(owner) as tx:
            result = tx._session.execute(update(g).where(g.c.learner_id==owner, g.c.operation_id==str(operation),
                g.c.claim_id==token, g.c.claim_until > self.clock()).values(claim_until=self.clock()+timedelta(seconds=180)))
            if result.rowcount != 1: raise AppError('ASSESSMENT_GENERATION_EXPIRED', 'Generation ownership changed.', 409)

    def replay(self, owner, request):
        with self.sessions() as session:
            row = session.execute(select(a).where(a.c.learner_id == owner, a.c.operation_id == str(request.client_request_id))).mappings().first()
            if row and row['fingerprint'] != request_hash(request.fingerprint_payload()):
                raise AppError('OPERATION_CONFLICT', 'This request ID already belongs to another assessment.', 409)
            return self.public(row) if row else None

    def save(self, owner, request, generated, sources, claim_id=None, revision_snapshot=None):
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
                paper=generated.paper.model_dump(mode='json') if generated.paper else None,
                preferences=dict(level=request.level, result_style=request.result_style),
                operation_id=str(request.client_request_id), fingerprint=fingerprint)
            from .mistake_practice import inherit_practice_lineage
            row['practice_lineage'] = inherit_practice_lineage(self, session, owner, request, questions, row['id'])
            if revision_snapshot:
                from .revision_practice import revision_lineage
                row['practice_lineage'] = revision_lineage(revision_snapshot, questions)
            session.execute(a.insert().values(**row))
            return self.public(row)

    def detail(self, owner, identifier):
        with self.sessions() as session: return self.public(self._assessment(session, owner, identifier))

    def practise_mistakes(self, owner, identifier, body):
        from .mistake_practice import create_practice
        return create_practice(self, owner, identifier, body)

    def list(self, owner, offset=0):
        with self.sessions() as session:
            rows = session.execute(select(a).where(a.c.learner_id == owner).order_by(a.c.created_at.desc(), a.c.id).offset(offset).limit(21)).mappings().all()
            return dict(items=[self.public(row) for row in rows[:20]], next_offset=offset+20 if len(rows)>20 else None)

    def start(self, owner, identifier, body, *, fingerprint=None):
        with self.transactions.write(owner) as tx:
            session = tx._session
            assessment = self._assessment(session, owner, identifier)
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
                extraction=None, error=None, worker_attempts=0, evidence_status='none', start_fingerprint=fingerprint,
                assistance='assisted' if assessment.get('practice_lineage') else 'unknown')
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

    def available_evidence_sources(self, owner, references):
        """Hydrate only current owned grades; deleted or regraded sources have no link."""
        references = list(references)[:5]
        if not references: return set()
        with self.sessions() as session:
            rows = session.execute(select(t.c.assessment_id, t.c.id, t.c.grade_revision).join(a,
                and_(a.c.id==t.c.assessment_id, a.c.learner_id==t.c.learner_id)).where(
                    t.c.learner_id==owner, t.c.state=='graded', t.c.id.in_([str(ref[1]) for ref in references]))).all()
            return {(str(row.assessment_id), str(row.id), row.grade_revision) for row in rows}

    def save_draft_answers(self, owner, identifier, body):
        with self.transactions.write(owner) as tx:
            row = self._attempt(tx._session, owner, identifier)
            questions = self._assessment(tx._session, owner, row['assessment_id'])['questions']
            self.validate_mcq_answers(questions, body.answers, partial=True)
            if row['state'] != 'draft':
                raise AppError('REVISION_CONFLICT', 'Only draft answers can be saved.', 409)
            # Exact retries after a lost response are safe without incrementing revision.
            if row['answers'] == body.answers: return self.attempt_public(row)
            if row['revision'] != body.expected_revision:
                raise AppError('REVISION_CONFLICT', 'Answers changed. Reload before saving.', 409)
            values = dict(answers=body.answers, revision=row['revision']+1)
            tx._session.execute(update(t).where(t.c.id == identifier).values(**values))
            return self.attempt_public(dict(row, **values))

    @staticmethod
    def validate_mcq_answers(questions, answers, partial=False):
        allowed = {q['id']:q for q in questions}
        if set(answers)-set(allowed):
            raise AppError('ASSESSMENT_INVALID_ANSWER', 'Unknown question.', 422)
        for key, answer in answers.items():
            q = allowed[key]
            if not isinstance(answer, str) or not answer.strip():
                raise AppError('ASSESSMENT_INVALID_ANSWER', 'Choose a valid answer.', 422)
            if q.get('options'):
                from ..choice_answers import selected_options
                selected_options(q, answer)

    @staticmethod
    def normalize_answers(questions, answers):
        from ..choice_answers import normalized_choice
        normalized = dict(answers)
        for question in questions:
            if question.get('options') and question['id'] in answers:
                normalized[question['id']] = normalized_choice(question, answers[question['id']])
        return normalized

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
            assessment = self._assessment(session, owner, row['assessment_id'])
            questions = assessment['questions']
            if set(body.answers) != {q['id'] for q in questions} or any(not answer.strip() for answer in body.answers.values()):
                raise AppError('ASSESSMENT_INCOMPLETE', 'Answer every question or part.', 422)
            answers = self.normalize_answers(questions, body.answers)
            self.validate_mcq_answers(questions, answers)
            values = dict(answers=answers, state='submitted', revision=row['revision']+1, submitted_at=self.clock(),
                profile_context_version=self.profile_version(session, owner),
                submission_id=str(body.client_request_id), submission_hash=digest, evidence_status='pending', assistance='assisted' if assessment.get('practice_lineage') else body.assistance, error=None, log_context=workflow_logger.envelope())
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
            assessment=self._assessment(session,owner,row['assessment_id'])
            questions=assessment['questions']
            if set(body.answers)!={question['id'] for question in questions} or any(not answer.strip() for answer in body.answers.values()):
                raise AppError('ASSESSMENT_INCOMPLETE','Review every answer before submitting a correction.',422)
            if row['extraction'] and not body.transcription_confirmed:
                raise AppError('TRANSCRIPTION_CONFIRMATION_REQUIRED','Confirm the corrected transcription.',422)
            answers = self.normalize_answers(questions, body.answers)
            self.validate_mcq_answers(questions, answers)
            history=[*row['grade_history'],dict(grade_revision=row['grade_revision'],grades=row['grades'],answers=row['answers'],assistance=row.get('assistance','unknown'),corrected_at=self.clock().isoformat())]
            if len(history)>10:raise AppError('CORRECTION_LIMIT','This attempt has reached its correction limit.',409)
            values=dict(grade_history=history,grade_revision=row['grade_revision']+1,answers=answers,grades=None,grading_progress={},
                profile_context_version=self.profile_version(session, owner),
                revision=row['revision']+1,state='submitted',submitted_at=self.clock(),worker_attempts=0,retry_at=None,
                submission_id=str(body.client_request_id),submission_hash=digest,evidence_status='pending',assistance='assisted' if assessment.get('practice_lineage') else body.assistance,error=None,log_context=workflow_logger.envelope())
            session.execute(update(t).where(t.c.id==identifier).values(**values))
            return self.attempt_public(dict(row,**values))

    def retry_grading(self, owner, identifier, body):
        with self.transactions.write(owner) as tx:
            row = self._attempt(tx._session, owner, identifier)
            if row['retry_request_id'] == str(body.client_request_id):
                return self.attempt_public(row)
            if row['state'] != 'failed' or row['revision'] != body.expected_revision:
                raise AppError('REVISION_CONFLICT', 'Only the current failed attempt can be retried.', 409)
            if not row['submission_id'] or row['manual_retries'] >= 3:
                raise AppError('ASSESSMENT_RETRY_LIMIT', 'Start a new attempt to continue.', 409)
            values = dict(state='submitted', revision=row['revision'] + 1, worker_attempts=0,
                retry_at=None, claim_id=None, claim_until=None, error=None,
                retry_request_id=str(body.client_request_id), manual_retries=row['manual_retries'] + 1,
                log_context=workflow_logger.envelope())
            tx._session.execute(update(t).where(t.c.id == identifier).values(**values))
            return self.attempt_public(dict(row, **values))

    def claim(self):
        now = self.clock()
        with self.sessions.begin() as session:
            session.execute(update(t).where(t.c.state == 'grading', t.c.claim_until <= now, t.c.worker_attempts >= 3).values(
                state='failed', error='Grading could not complete. Please retry this assessment.', claim_id=None,
                claim_until=None, retry_at=None, revision=t.c.revision+1))
            eligible_rows = select(t.c.id, t.c.learner_id, t.c.created_at,
                func.row_number().over(partition_by=t.c.learner_id, order_by=(t.c.created_at, t.c.id)).label('owner_rank')).where(t.c.worker_attempts < 3,
                or_(t.c.state == 'submitted', and_(t.c.state == 'grading', t.c.claim_until <= now),
                    and_(t.c.state == 'failed', t.c.retry_at <= now))).subquery()
            candidates = session.execute(select(eligible_rows.c.id, eligible_rows.c.learner_id)
                .order_by(eligible_rows.c.owner_rank, eligible_rows.c.created_at, eligible_rows.c.id).limit(32)).all()
        for identifier, owner in candidates:
            with self.transactions.try_write(owner) as tx:
                if tx is None:
                    continue
                row = tx._session.execute(select(*ATTEMPT_COLUMNS, t.c.grading_progress).where(t.c.id == identifier, t.c.learner_id == owner)).mappings().first()
                if not row:
                    continue
                eligible = row['state'] == 'submitted' or (row['state'] == 'grading' and row['claim_until'] and row['claim_until'] <= now) or (row['state'] == 'failed' and row['retry_at'] and row['retry_at'] <= now)
                if not eligible or row['worker_attempts'] >= 3:
                    continue
                token = str(uuid4())
                assessment = self._assessment(tx._session, owner, row['assessment_id'])
                from ..grading_progress import GRADING_LEASE_SECONDS
                tx._session.execute(update(t).where(t.c.id == identifier).values(state='grading', claim_id=token,
                    claim_until=now+timedelta(seconds=GRADING_LEASE_SECONDS), worker_attempts=row['worker_attempts']+1))
                return dict(owner=owner, id=identifier, claim_id=token, attempt=dict(row, worker_attempts=row['worker_attempts']+1),
                    assessment=assessment, profile_context_version=row['profile_context_version'])
        return None

    def checkpoint_grades(self, job, grades):
        from ..grading_progress import grading_signature
        with self.transactions.write(job['owner']) as tx:
            row = self._attempt(tx._session, job['owner'], job['id'])
            if row['claim_id'] != job['claim_id'] or row['state'] != 'grading' or row['claim_until'] <= self.clock() or row['grade_revision'] != job['attempt']['grade_revision']:
                raise AppError('ATTEMPT_CLAIM_EXPIRED', 'Grading ownership changed.', 409)
            tx._session.execute(update(t).where(t.c.id==job['id']).values(grading_progress=dict(
                signature=grading_signature(job), grades=[grade.model_dump(mode='json') for grade in grades])))

    def complete(self, job, grades, apply_evidence=None):
        with self.transactions.write(job['owner']) as tx:
            row = self._attempt(tx._session, job['owner'], job['id'])
            if row['claim_id'] != job['claim_id'] or row['state'] != 'grading' or row['claim_until'] <= self.clock():
                raise AppError('ATTEMPT_CLAIM_EXPIRED', 'Grading lease expired.', 409)
            # The evidence producer admits each observation independently and
            # withdraws obsolete evidence even when a corrected grade is uncertain.
            # The durable worker publishes results and its outbox atomically.
            # Trusted composed callers may still request synchronous persistence.
            receipt = apply_evidence(tx) if apply_evidence else None
            expected = sum(len(question.concept_grades) for question in grades.questions)
            accepted = sum(bool(item.get('accepted')) for item in receipt or [])
            evidence_status = ('applied' if accepted == expected else 'partial' if accepted else 'unavailable') if apply_evidence else 'pending'
            questions = {str(question['id']): question for question in job['assessment']['questions']}
            public_grades = []
            for grade in grades.questions:
                question = questions[grade.question_id]
                correct_ids = set(question.get('correct_option_ids') or [question.get('correct_option_id')])
                correct = '\n\n'.join(option['label'] for option in question.get('options', []) if option['id'] in correct_ids) or None
                public_grades.append(dict(grade.model_dump(mode='json'),
                    outcome='correct' if grade.score == question['marks'] else 'wrong' if grade.score == 0 else 'partial',
                    correct_answer=correct))
            tx._session.execute(update(t).where(t.c.id == job['id']).values(state='graded', grades=public_grades,
                evidence_status=evidence_status, evidence_receipt=receipt if apply_evidence else row.get('evidence_receipt'),
                revision=row['revision']+1, claim_id=None, claim_until=None, retry_at=None, error=None, grading_progress={}))
            if not apply_evidence:
                from .tables import evidence_jobs
                from sqlalchemy.dialects.postgresql import insert
                tx._session.execute(insert(evidence_jobs).values(attempt_id=job['id'], learner_id=job['owner'],
                    grade_revision=row['grade_revision'], state='queued', created_at=self.clock()).on_conflict_do_nothing())

    def fail(self, job, *, retry=True, error=None):
        with self.transactions.write(job['owner']) as tx:
            row = self._attempt(tx._session, job['owner'], job['id'])
            if row['claim_id'] != job['claim_id']: return
            tx._session.execute(update(t).where(t.c.id == job['id']).values(state='failed', error=error or 'Grading is temporarily unavailable.',
                retry_at=self.clock()+timedelta(seconds=5*2**row['worker_attempts']) if retry and row['worker_attempts'] < 3 else None, claim_id=None, claim_until=None, revision=row['revision']+1))
        workflow_logger.event('job.retry_scheduled' if retry and row['worker_attempts'] < 3 else 'job.failed', job_id=job['id'], attempt=row['worker_attempts'])

    def remove(self, owner, identifier):
        with self.transactions.write(owner) as tx:
            self._assessment(tx._session, owner, identifier)
            from app.langchain.repositories.checkpoint_tables import delete_thread
            for attempt_id in tx._session.execute(select(t.c.id).where(t.c.learner_id == owner, t.c.assessment_id == identifier)).scalars():
                delete_thread(tx._session, f'assessment-transcription-v1:{owner}:{attempt_id}')
            tx._session.execute(delete(a).where(a.c.learner_id == owner, a.c.id == identifier))
