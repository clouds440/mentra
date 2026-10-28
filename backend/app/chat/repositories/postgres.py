"""Short transactions; no model calls or network I/O while holding locks."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from uuid import uuid4, UUID
from sqlalchemy import select, update, delete, and_, or_, text, func, cast, Text
from app.core.exceptions import AppError
from .tables import conversations as c, messages as m, turns as t, sync_state as ss, changes as ch
from app.chat.titles import NewChatReply, provisional_title
from pydantic import ValidationError


def now():
    return datetime.now(timezone.utc)


def conflict():
    return AppError('CHAT_CONFLICT', 'This conversation changed. Synchronize it and try again.', 409)


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class ChatRepository:
    def __init__(self, sessions):
        self.sessions = sessions
        from app.core.read_cache import ReadCache
        self._contexts = ReadCache(capacity=32, ttl=None)

    def _sync_lock(self, session, owner):
        from app.db.owner_transactions import lock_owner
        return lock_owner(session, owner)

    def _change(self, session, owner, conversation_id, state):
        revision = state['revision'] + 1
        # This owner-only lock is retained until commit: revisions cannot commit out of order.
        floor = max(state['floor'], revision - 10000)
        session.execute(update(ss).where(ss.c.learner_id == owner).values(revision=revision, floor=floor))
        session.execute(ch.insert().values(learner_id=owner, revision=revision, conversation_id=conversation_id, created_at=now()))
        if floor > state['floor']:
            session.execute(delete(ch).where(ch.c.learner_id == owner, ch.c.revision <= floor))

    def _conversation(self, session, owner, conversation_id, lock=False):
        query = select(c).where(c.c.learner_id == owner, c.c.id == conversation_id, c.c.deleted_at.is_(None))
        row = session.execute(query.with_for_update() if lock else query).mappings().first()
        if not row:
            raise AppError('CHAT_NOT_FOUND', 'Conversation not found.', 404)
        return dict(row)

    @staticmethod
    def _public_message(row):
        value = dict(row)
        metadata = value.pop('metadata')
        value.pop('learner_id', None)
        public = {**metadata, **value}
        if value.get('role') == 'assistant' and not public.get('response_outcome'):
            from app.langchain.task_outcomes import legacy_outcome
            public['response_outcome'] = legacy_outcome({'state':'SUCCEEDED'}, metadata)
        return public

    def _page(self, session, owner, conversation_id, before=None, after=None, limit=40):
        query = select(m).where(m.c.learner_id == owner, m.c.conversation_id == conversation_id)
        if before is not None:
            query = query.where(m.c.sequence < before)
        if after is not None:
            query = query.where(m.c.sequence > after)
        ascending = after is not None
        rows = session.execute(query.order_by(m.c.sequence.asc() if ascending else m.c.sequence.desc()).limit(limit + 1)).mappings().all()
        more = len(rows) > limit
        rows = rows[:limit]
        items = [self._public_message(row) for row in (rows if ascending else reversed(rows))]
        from .response_outcomes import project_outcomes
        items = project_outcomes(session, owner, items)
        return dict(items=items, has_more=more, next_cursor=(items[-1 if ascending else 0]['sequence'] if more else None))

    def history(self, owner, conversation_id, before=None, after=None, limit=40):
        with self.sessions() as session:
            conversation = self._conversation(session, owner, conversation_id)
            return dict(conversation=conversation, **self._page(session, owner, conversation_id, before, after, limit))

    def recent(self, owner, cursor=None, limit=40):
        with self.sessions() as session:
            query = select(c).where(c.c.learner_id == owner, c.c.deleted_at.is_(None))
            if cursor:
                try:
                    stamp, identifier = json.loads(cursor)
                    stamp = datetime.fromisoformat(stamp)
                    identifier = str(UUID(identifier))
                    if stamp.tzinfo is None:
                        raise ValueError('Cursor timestamp must include timezone')
                    query = query.where(or_(c.c.updated_at < stamp, and_(c.c.updated_at == stamp, c.c.id < identifier)))
                except (ValueError, TypeError, KeyError, AttributeError):
                    raise AppError('CHAT_CURSOR_INVALID', 'Invalid conversation cursor.', 422)
            rows = [dict(row) for row in session.execute(query.order_by(c.c.updated_at.desc(), c.c.id.desc()).limit(limit + 1)).mappings()]
            more = len(rows) > limit
            rows = rows[:limit]
            return dict(items=rows, next_cursor=json.dumps([rows[-1]['updated_at'].isoformat(), rows[-1]['id']]) if more else None)

    def sync(self, owner, cursor=None, active=None, limit=100):
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            reset = cursor is None or cursor < state['floor'] or cursor > state['revision']
            if reset:
                rows = [dict(row) for row in session.execute(select(c).where(c.c.learner_id == owner, c.c.deleted_at.is_(None))
                    .order_by(c.c.updated_at.desc(), c.c.id.desc()).limit(41)).mappings()]
                more = len(rows) > 40
                rows = rows[:40]
                result = dict(reset=True, cursor=state['revision'], has_more=False, conversations=rows, deleted_ids=[],
                    list_cursor=json.dumps([rows[-1]['updated_at'].isoformat(), rows[-1]['id']]) if more else None)
            else:
                events = session.execute(select(ch).where(ch.c.learner_id == owner, ch.c.revision > cursor)
                    .order_by(ch.c.revision).limit(limit + 1)).mappings().all()
                more = len(events) > limit
                events = events[:limit]
                ids = list(dict.fromkeys(row['conversation_id'] for row in events))
                rows = [dict(row) for row in session.execute(select(c).where(c.c.learner_id == owner, c.c.id.in_(ids))).mappings()] if ids else []
                result = dict(reset=False, cursor=events[-1]['revision'] if events else state['revision'], has_more=more,
                    conversations=[row for row in rows if row['deleted_at'] is None],
                    deleted_ids=[row['id'] for row in rows if row['deleted_at'] is not None])
            if active:
                row = session.execute(select(c).where(c.c.learner_id == owner, c.c.id == active, c.c.deleted_at.is_(None))).mappings().first()
                if row:
                    result['active'] = dict(conversation=dict(row), **self._page(session, owner, active))
            return result

    @staticmethod
    def _request_hash(request):
        conversation_id = str(request.conversation_id)
        content = request.content
        selection = request.retrieval.model_dump(mode='json')
        attachment_ids = list(dict.fromkeys(str(value) for value in request.attachment_ids))
        # Retain fingerprints for existing clients/turns without attachments.
        fingerprint = sha256(json.dumps([conversation_id, content, selection] + ([attachment_ids] if attachment_ids else []), sort_keys=True).encode()).hexdigest()
        if request.interaction_response:
            reply = request.interaction_response
            # Empty additive fields must not invalidate pre-upgrade pending sends.
            excluded = {name for name in ('option_inputs', 'values', 'answers', 'additional_responses') if not getattr(reply, name)}
            data = reply.model_dump(mode='json', exclude=excluded)
            # Preserve the pre-questionnaire field order in existing receipts.
            ordered = {key:data[key] for key in ('message_id', 'interaction_id', 'selected',
                'option_inputs', 'values', 'answers', 'additional_responses') if key in data}
            fingerprint = sha256((fingerprint + json.dumps(ordered, ensure_ascii=False, separators=(',', ':'))).encode()).hexdigest()
        if request.timezone:
            fingerprint = sha256((fingerprint + request.timezone).encode()).hexdigest()
        return fingerprint

    def replay_turn(self, owner, request):
        with self.sessions() as session:
            row = session.execute(select(t).where(t.c.id == str(request.client_turn_id))).mappings().first()
            if not row:
                return None
            if row['learner_id'] != owner or row['request_hash'] != self._request_hash(request):
                raise AppError('CHAT_IDEMPOTENCY_CONFLICT', 'This send identifier is already in use.', 409)
            if row['state'] == 'RUNNING' and row['lease_until'] < now() or request.retry and (row['state'] == 'FAILED' or self._legacy_incomplete(session, row)):
                return None
            return self.status(owner, str(request.conversation_id), str(request.client_turn_id), True)

    @staticmethod
    def _legacy_incomplete(session, turn):
        if turn.get('response_outcome') or not turn.get('assistant_sequence'):
            return False
        metadata = session.scalar(select(m.c.metadata).where(m.c.learner_id == turn['learner_id'],
            m.c.conversation_id == turn['conversation_id'], m.c.sequence == turn['assistant_sequence'])) or {}
        return any(item.get('code') == 'REQUEST_OUTCOME_INCOMPLETE' for item in metadata.get('tool_warnings', []))

    def begin_turn(self, owner, request, *, log_context=None):
        log_context = log_context or workflow_logger.envelope()
        conversation_id, turn_id = str(request.conversation_id), str(request.client_turn_id)
        content = request.content
        selection = request.retrieval.model_dump(mode='json')
        attachment_ids = list(dict.fromkeys(str(value) for value in request.attachment_ids))
        fingerprint = self._request_hash(request)
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            existing = session.execute(select(t).where(t.c.id == turn_id)).mappings().first()
            if existing:
                if existing['learner_id'] != owner or existing['request_hash'] != fingerprint:
                    raise AppError('CHAT_IDEMPOTENCY_CONFLICT', 'This send identifier is already in use.', 409)
                conversation = self._conversation(session, owner, conversation_id, True)
                if request.retry and self._legacy_incomplete(session, existing):
                    existing = dict(existing, state='FAILED')
                if existing['state'] == 'RUNNING' and existing['lease_until'] < now():
                    session.execute(update(t).where(t.c.id == turn_id).values(state='FAILED', error='Generation interrupted. Retry this message.', lease_until=None,resume_until=now()+timedelta(minutes=30)))
                    conversation['revision'] += 1
                    session.execute(update(c).where(c.c.id == conversation_id).values(revision=conversation['revision'], updated_at=now()))
                    if not request.retry:
                        self._change(session, owner, conversation_id, state)
                    existing = dict(existing, state='FAILED', error='Generation interrupted. Retry this message.',resume_until=now()+timedelta(minutes=30))
                if not request.retry or existing['state'] != 'FAILED':
                    return dict(run=False, turn_id=turn_id, conversation_id=conversation_id)
                if existing.get('response_outcome') and not existing['response_outcome'].get('retryable'):
                    raise AppError('CHAT_RETRY_UNAVAILABLE','This action needs review or new information before retrying.',409)
                if existing.get('orchestration_policy')=='semantic-v3' and (not existing['resume_until'] or existing['resume_until']<=now()):
                    raise AppError('CHAT_RESUME_EXPIRED','Saved response recovery has expired. Send a new request.',409)
                # Only the most recent question can be retried without branching history.
                if conversation['message_count'] not in (existing['user_sequence'], existing['assistant_sequence']):
                    raise conflict()
                attempt = existing['attempt'] + 1
                session.execute(update(t).where(t.c.id == turn_id).values(state='RUNNING', error=None, response_outcome=None, attempt=attempt, lease_until=now() + timedelta(minutes=3),resume_until=None,log_context=log_context))
                session.execute(update(c).where(c.c.id == conversation_id).values(revision=conversation['revision']+1, updated_at=now()))
                self._change(session, owner, conversation_id, state)
                return dict(run=True, turn_id=turn_id, conversation_id=conversation_id, attempt=attempt, selection=selection, attachment_ids=attachment_ids, user_sequence=existing['user_sequence'], resume_instruction=existing['resume_instruction'], title_revision=conversation['revision']+1, recovery_state=existing.get('recovery_state'))
            row = session.execute(select(c).where(c.c.id == conversation_id)).mappings().first()
            if row is None:
                if request.expected_revision != 0:
                    raise conflict()
                title = provisional_title(content)
                stamp = now()
                conversation = dict(id=conversation_id, learner_id=owner, title=title or 'New chat', selection=selection,
                    revision=1, message_count=0, created_at=stamp, updated_at=stamp)
                session.execute(c.insert().values(**conversation))
            else:
                conversation = self._conversation(session, owner, conversation_id, True)
                if conversation['revision'] != request.expected_revision:
                    raise conflict()
            running = session.execute(select(t).where(t.c.learner_id == owner, t.c.conversation_id == conversation_id, t.c.state == 'RUNNING')).mappings().all()
            for pending in running:
                if pending['lease_until'] >= now():
                    raise AppError('CHAT_BUSY', 'Wait for the current response before sending another message.', 409)
                session.execute(update(t).where(t.c.id == pending['id']).values(state='FAILED', error='Generation interrupted.'))
            interaction_metadata = {}
            if request.interaction_response:
                from app.chat.interactions import resolve_responses
                reply = request.interaction_response
                source = session.execute(select(m).where(m.c.id == str(reply.message_id), m.c.learner_id == owner,
                    m.c.conversation_id == conversation_id, m.c.role == 'assistant')).mappings().first()
                if not source: raise AppError('INTERACTION_NOT_FOUND', 'This interaction is unavailable.', 404)
                metadata = dict(source['metadata'])
                cards = [dict(x) for x in metadata.get('interactions', [])]
                content = resolve_responses(cards, reply, turn_id)
                metadata['interactions'] = cards
                session.execute(update(m).where(m.c.id == source['id']).values(metadata=metadata))
                interaction_metadata = dict(interaction_response=reply.model_dump(mode='json'))
            sequence = conversation['message_count'] + 1
            from .attachments import AttachmentRepository
            attachment_metadata = AttachmentRepository.bind(session, owner, attachment_ids, conversation_id)
            session.execute(m.insert().values(id=str(uuid4()), learner_id=owner, conversation_id=conversation_id, sequence=sequence,
                role='user', content=content, metadata={**interaction_metadata, **({'timezone':request.timezone} if request.timezone else {}), **({'attachments': attachment_metadata} if attachment_metadata else {})}, created_at=now()))
            session.execute(t.insert().values(id=turn_id, learner_id=owner, conversation_id=conversation_id, request_hash=fingerprint,
                user_sequence=sequence, state='RUNNING', orchestration_policy='semantic-v3', attempt=1, selection=selection, attachment_ids=attachment_ids, lease_until=now()+timedelta(minutes=3), created_at=now(),log_context=log_context))
            session.execute(update(c).where(c.c.id == conversation_id).values(message_count=sequence, revision=conversation['revision']+1, selection=selection, updated_at=now()))
            self._change(session, owner, conversation_id, state)
            return dict(run=True, turn_id=turn_id, conversation_id=conversation_id, attempt=1, selection=selection, attachment_ids=attachment_ids, user_sequence=sequence, title_revision=conversation['revision']+1)

    def finish(self, owner, job, response=None, error=None):
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            turn = session.execute(select(t).where(t.c.id == job['turn_id'], t.c.learner_id == owner).with_for_update()).mappings().first()
            if not turn or turn['state'] != 'RUNNING' or turn['attempt'] != job['attempt']:
                workflow_logger.set_outcome('skipped', code='CHAT_STALE_ATTEMPT')
                from app.core.observability.context import current
                current.get().outcome = 'skipped'
                return False
            row = session.execute(select(c).where(c.c.id == job['conversation_id'], c.c.learner_id == owner).with_for_update()).mappings().one()
            if row['deleted_at'] is not None:
                workflow_logger.set_outcome('skipped', code='CHAT_DELETED')
                from app.core.observability.context import current
                current.get().outcome = 'skipped'
                return False
            from app.langchain.decision_schemas import ResponseOutcome
            outcome = ResponseOutcome.model_validate((response or {}).get('response_outcome') or dict(
                state='failed' if error else 'completed', retryable=bool(error),reason_code=job.get('_failure_code')))
            incomplete = error is not None or outcome.state in ('partial','failed')
            public_error = error or ('This response is incomplete. Retry the unfinished part.' if incomplete else None)
            values = dict(state='FAILED' if incomplete else 'SUCCEEDED', error=public_error, lease_until=None,
                response_outcome=outcome.model_dump(mode='json'), orchestration_policy='semantic-v3',
                recovery_state=(job.get('_recovery_state') or turn.get('recovery_state')) if incomplete else None,
                resume_until=now()+timedelta(minutes=30) if incomplete and (outcome.retryable or job.get('_recovery_state') or turn.get('recovery_state')) else None)
            conversation_values = dict()
            context_changed = False
            sequence = row['message_count']
            if not error:
                # Composer source consent is one-turn; retain the immutable
                # turn selection for retry/audit while clearing the next draft.
                from app.rag.schemas import ChatSelection
                conversation_values['selection'] = ChatSelection().model_dump()
                replacing_pause = turn['assistant_sequence'] is not None
                if not replacing_pause:
                    sequence += 1
                payload = dict(response)
                payload['response_outcome'] = outcome.model_dump(mode='json')
                if turn['resume_instruction']: payload['resume_instructions'] = turn['resume_instruction']
                generated_title = payload.pop('conversation_title', None)
                from app.history_management.repositories.postgres import MemoryRepository
                if not MemoryRepository.references_current(session, owner, payload):
                    context_changed = incomplete = True
                    outcome = ResponseOutcome(state='partial' if any(payload.get(key) for key in ('assessment_cards','interactions','event_proposals','event_references')) else 'failed',
                        retryable=True,reason_code='SAVED_CONTEXT_CHANGED',tasks=outcome.tasks)
                    values.update(state='FAILED',error='Saved context changed. Retry to use current information.',response_outcome=outcome.model_dump(mode='json'),
                        resume_until=now()+timedelta(minutes=30),recovery_state=job.get('_recovery_state') or turn.get('recovery_state'))
                    job['_discard_checkpoint']=True
                    payload = dict({key:payload[key] for key in ('assessment_cards','interactions','event_proposals','event_references') if key in payload},
                        content='The referenced memory or conversation changed while I was answering. Retry to use current information.',
                        history_references=[],memory_references=[],response_outcome=outcome.model_dump(mode='json'))
                    generated_title = None
                payload.pop('_memory_summary_fence', None)
                if generated_title is not None and turn['user_sequence'] == 1 and row['revision'] == job.get('title_revision'):
                    first_content = session.execute(select(m.c.content).where(m.c.conversation_id == row['id'], m.c.learner_id == owner, m.c.sequence == 1)).scalar_one()
                    if row['title'] == provisional_title(first_content):
                        try:
                            conversation_values['title'] = NewChatReply(content=payload['content'], conversation_title=generated_title).conversation_title
                        except ValidationError:
                            pass
                content = payload.pop('content')
                payload.pop('role', None)
                if replacing_pause:
                    sequence = turn['assistant_sequence']
                    session.execute(update(m).where(m.c.learner_id == owner, m.c.conversation_id == row['id'],
                        m.c.sequence == sequence).values(content=content, metadata=payload))
                else:
                    session.execute(m.insert().values(id=str(uuid4()), learner_id=owner, conversation_id=row['id'], sequence=sequence,
                        role='assistant', content=content, metadata=payload, created_at=now()))
                values['assistant_sequence'] = sequence
            session.execute(update(t).where(t.c.id == job['turn_id']).values(**values))
            workflow_logger.set_outcome('failed' if outcome.state=='failed' else 'degraded' if outcome.state=='partial' else
                'deferred' if outcome.state in ('awaiting_input','in_progress','paused') else 'success',code=outcome.reason_code)
            from app.langchain.repositories.response_checkpoints import delete_response_checkpoints
            if not incomplete or not outcome.retryable or job.get('_discard_checkpoint'): delete_response_checkpoints(session, owner, job['turn_id'])
            if response is not None and not context_changed:
                from app.langchain.repositories.evidence import ChatEvidenceRepository
                ChatEvidenceRepository.queue(session, owner, job)
            session.execute(update(c).where(c.c.id == row['id']).values(message_count=sequence, revision=row['revision']+1, updated_at=now(), **conversation_values))
            if not error:
                from .summary_jobs import queue
                queue(session, owner, row['id'], sequence)
                if not incomplete:
                    from app.history_management.repositories.memory_capture import enqueue
                    enqueue(session, owner, None, job['turn_id'], job['attempt'])
            self._change(session, owner, row['id'], state)

        return True

    def stop_turn(self, owner, conversation_id, turn_id, attempt, stopped_job=None):
        """Fence publication first; cancellation must never overwrite a finished turn."""
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            row = self._conversation(session, owner, conversation_id, True)
            turn = session.execute(select(t).where(t.c.id == turn_id, t.c.learner_id == owner,
                t.c.conversation_id == conversation_id).with_for_update()).mappings().first()
            if not turn:
                raise AppError('CHAT_NOT_FOUND', 'This response is unavailable.', 404)
            if turn['attempt'] != attempt:
                raise AppError('CHAT_STALE_ATTEMPT', 'This response has changed. Check the conversation.', 409)
            from app.assessments.repositories.postgres import AssessmentRepository
            from app.assessments.repositories.generation import GenerationJobs
            from app.assessments.repositories.tables import generation_jobs
            from app.db.owner_transactions import OwnedUnitOfWork
            jobs = GenerationJobs(AssessmentRepository(self.sessions))
            linked = session.scalars(select(generation_jobs.c.id).where(generation_jobs.c.learner_id == owner,
                generation_jobs.c.source_turn_id == turn_id, generation_jobs.c.state.in_(['queued', 'running']))).all()
            stopped_jobs = [jobs.stop_in_transaction(OwnedUnitOfWork(owner, session), identifier) for identifier in linked]
            if stopped_job:
                identifier, revision = stopped_job
                acknowledged = session.execute(select(generation_jobs).where(generation_jobs.c.id == identifier,
                    generation_jobs.c.learner_id == owner, generation_jobs.c.source_turn_id == turn_id).with_for_update()).mappings().first()
                if not acknowledged or acknowledged['revision'] != revision or acknowledged['state'] != 'stopped':
                    raise AppError('REVISION_CONFLICT', 'This generation changed. Refresh its progress.', 409)
                if identifier not in linked: stopped_jobs.append(jobs.public(acknowledged))
                if turn['state'] == 'FAILED' and not linked: return False
            if turn['state'] != 'RUNNING' and not any(item['state'] == 'stopped' for item in stopped_jobs):
                return False
            sequence = turn['assistant_sequence'] or row['message_count'] + 1
            from .tables import activity
            partial = session.scalars(select(activity.c.payload).where(activity.c.learner_id == owner,
                activity.c.turn_id == turn_id, activity.c.attempt == attempt).order_by(activity.c.sequence)).all()
            text_parts = []
            for event in partial:
                if event.get('token_reset'): text_parts = []
                if event.get('token_delta'): text_parts.append(event['token_delta'])
            paused_tasks = [dict(id='generation:'+item['id'],operation='assessment_generate',state='paused',
                job_kind='generation',job_id=item['id'],required=True,effect_certainty='committed') for item in stopped_jobs]
            metadata = dict(response_stopped=True, response_outcome=dict(version=3, state='paused', retryable=False, tasks=paused_tasks))
            if turn['state'] == 'SUCCEEDED': metadata['background_handoff'] = True
            cards = [dict(id=item['id'], generation_job_id=item['id'], title=item['title']) for item in stopped_jobs]
            if cards: metadata['assessment_cards'] = cards
            notice = ''.join(text_parts)[:32000] or 'Response paused. Resume within 30 minutes, or send a new message.'
            if turn['assistant_sequence']:
                prior = session.execute(select(m).where(m.c.conversation_id == conversation_id, m.c.sequence == sequence)).mappings().one()
                existing_tasks = (prior['metadata'].get('response_outcome') or {}).get('tasks', [])
                if existing_tasks:
                    paused_ids = {item['id'] for item in stopped_jobs}
                    preserved = [dict(task,state='paused') if task.get('job_id') in paused_ids else dict(task) for task in existing_tasks]
                    represented = {task.get('job_id') for task in preserved}
                    metadata['response_outcome']['tasks'] = preserved + [task for task in paused_tasks if task['job_id'] not in represented]
                metadata = dict(prior['metadata'], **metadata)
                session.execute(update(m).where(m.c.id == prior['id']).values(metadata=metadata))
            else:
                session.execute(m.insert().values(id=str(uuid4()), learner_id=owner, conversation_id=conversation_id,
                    sequence=sequence, role='assistant', content=notice, metadata=metadata, created_at=now()))
            session.execute(update(t).where(t.c.id == turn_id).values(state='FAILED', error='Response stopped.',
                response_outcome=metadata['response_outcome'],
                assistant_sequence=sequence, lease_until=None, resume_until=now() + timedelta(minutes=30)))
            session.execute(update(c).where(c.c.id == conversation_id).values(message_count=max(row['message_count'], sequence),
                revision=row['revision'] + 1, updated_at=now()))
            self._change(session, owner, conversation_id, state)
            return True

    def resume_turn(self, owner, conversation_id, turn_id, attempt, revision, instruction=None, operation=None, fingerprint=None):
        from app.assessments.repositories.generation import GenerationJobs
        from app.assessments.repositories.postgres import AssessmentRepository
        GenerationJobs(AssessmentRepository(self.sessions)).expire_stopped(owner)
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            row = self._conversation(session, owner, conversation_id, True)
            turn = session.execute(select(t).where(t.c.id == turn_id, t.c.learner_id == owner,
                t.c.conversation_id == conversation_id).with_for_update()).mappings().first()
            if not turn: raise AppError('CHAT_NOT_FOUND', 'This response is unavailable.', 404)
            if operation and turn['resume_operation_id'] == operation:
                if turn['resume_request_hash'] != fingerprint: raise conflict()
                return dict(run=False, turn_id=turn_id, conversation_id=conversation_id)
            if turn['attempt'] != attempt or row['revision'] != revision: raise conflict()
            if turn['state'] != 'FAILED' or not turn['resume_until'] or turn['resume_until'] <= now():
                raise AppError('CHAT_RESUME_EXPIRED', 'This paused response has expired. Send a new request.', 409)
            latest = session.scalar(select(func.max(t.c.user_sequence)).where(t.c.learner_id == owner, t.c.conversation_id == conversation_id))
            if latest != turn['user_sequence']: raise conflict()
            from app.assessments.repositories.tables import generation_jobs
            # Requeue without nesting owner transactions; same operation IDs and
            # saved question batches survive. Changes are handled by chat tools.
            if not instruction:
                active = session.scalar(select(func.count()).select_from(generation_jobs).where(
                    generation_jobs.c.learner_id == owner, generation_jobs.c.state.in_(['queued', 'running'])))
                pending = session.scalar(select(func.count()).select_from(generation_jobs).where(
                    generation_jobs.c.learner_id == owner, generation_jobs.c.source_turn_id == turn_id,
                    generation_jobs.c.state == 'stopped'))
                if active + pending > 2:
                    raise AppError('ASSESSMENT_GENERATION_BUSY', 'Let your current assessments finish before resuming this response.', 409)
                session.execute(update(generation_jobs).where(generation_jobs.c.learner_id == owner,
                    generation_jobs.c.source_turn_id == turn_id, generation_jobs.c.state == 'stopped').values(
                        state='queued', revision=generation_jobs.c.revision + 1, attempts=0,
                        resume_until=None, claim_id=None, claim_until=None))
            amendments = '\n'.join(filter(None, [turn['resume_instruction'], instruction]))[-8000:] or None
            background_response = None
            if not instruction and turn['assistant_sequence']:
                prior = session.execute(select(m).where(m.c.learner_id == owner,m.c.conversation_id == conversation_id,
                    m.c.sequence == turn['assistant_sequence'])).mappings().one()
                if prior['metadata'].get('background_handoff'):
                    background_response = dict(prior['metadata'],content=prior['content'])
                    background_response.pop('response_stopped',None)
                    background_response.pop('background_handoff',None)
                    outcome = dict(background_response['response_outcome'],state='in_progress',retryable=False)
                    outcome['tasks'] = [dict(task,state='in_progress') if task.get('job_kind')=='generation' else task for task in outcome['tasks']]
                    background_response['response_outcome'] = outcome
            session.execute(update(t).where(t.c.id == turn_id).values(state='RUNNING', error=None,
                response_outcome=None, attempt=attempt+1, lease_until=now()+timedelta(minutes=3), resume_until=None, resume_instruction=amendments))
            if operation:
                session.execute(update(t).where(t.c.id == turn_id).values(resume_operation_id=operation, resume_request_hash=fingerprint))
            session.execute(update(c).where(c.c.id == conversation_id).values(revision=row['revision']+1, updated_at=now()))
            self._change(session, owner, conversation_id, state)
            return dict(run=True, turn_id=turn_id, conversation_id=conversation_id, attempt=attempt+1,
                selection=turn['selection'], attachment_ids=turn['attachment_ids'], user_sequence=turn['user_sequence'],
                resume=True, resume_instruction=amendments, new_instruction=instruction, title_revision=row['revision']+1,
                background_response=background_response,recovery_state=turn.get('recovery_state'))

    def status(self, owner, conversation_id, turn_id=None, incremental=False, after=None):
        self.expire_paused(owner)
        with self.sessions.begin() as session:
            session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            row = self._conversation(session, owner, conversation_id)
            query = select(t).where(t.c.learner_id == owner, t.c.conversation_id == conversation_id)
            if turn_id:
                query = query.where(t.c.id == turn_id)
            turn = session.execute(query.order_by(t.c.user_sequence.desc()).limit(1)).mappings().first()
            expired = turn and turn['state'] == 'RUNNING' and turn['lease_until'] < now()
            if not expired:
                return self._status_page(session, owner, conversation_id, row, turn, incremental, after)
        # Lease expiry is a mutation; recheck under the owner lock before changing it.
        return self._status_locked(owner, conversation_id, turn_id, incremental, after)

    def expire_paused(self, owner=None):
        from app.langchain.repositories.response_checkpoints import delete_response_checkpoints
        with self.sessions.begin() as session:
            query = select(t.c.learner_id, t.c.id).where(t.c.resume_until <= now())
            if owner: query = query.where(t.c.learner_id == owner)
            rows = session.execute(query.limit(100).with_for_update(skip_locked=True)).all()
            for learner, identifier in rows:
                delete_response_checkpoints(session, learner, identifier)
                session.execute(update(t).where(t.c.id == identifier).values(resume_until=None, resume_instruction=None,recovery_state=None))

    def _status_locked(self, owner, conversation_id, turn_id=None, incremental=False, after=None):
        with self.sessions.begin() as session:
            # Consistent locking order across every writer.
            state = self._sync_lock(session, owner)
            row = self._conversation(session, owner, conversation_id)
            query = select(t).where(t.c.learner_id == owner, t.c.conversation_id == conversation_id)
            if turn_id:
                query = query.where(t.c.id == turn_id)
            turn = session.execute(query.order_by(t.c.user_sequence.desc()).limit(1)).mappings().first()
            if turn and turn['state'] == 'RUNNING' and turn['lease_until'] < now():
                session.execute(update(t).where(t.c.id == turn['id']).values(state='FAILED', error='Generation interrupted. Retry this message.', lease_until=None, resume_until=now()+timedelta(minutes=30)))
                row = dict(row, revision=row['revision']+1, updated_at=now())
                session.execute(update(c).where(c.c.id == conversation_id).values(revision=row['revision'], updated_at=row['updated_at']))
                self._change(session, owner, conversation_id, state)
                turn = dict(turn, state='FAILED', error='Generation interrupted. Retry this message.', resume_until=now()+timedelta(minutes=30))
            return self._status_page(session, owner, conversation_id, row, turn, incremental, after)

    def _status_page(self, session, owner, conversation_id, row, turn, incremental, after):
        if after is not None:
            page = self._page(session, owner, conversation_id, after=after)
            incremental = True
        elif incremental and turn:
            rows = session.execute(select(m).where(m.c.learner_id == owner, m.c.conversation_id == conversation_id,
                m.c.sequence.in_([turn['user_sequence'], turn['assistant_sequence']])).order_by(m.c.sequence)).mappings().all()
            from .response_outcomes import project_outcomes
            page = dict(items=project_outcomes(session, owner, [self._public_message(item) for item in rows]), has_more=False, next_cursor=None)
        else:
            page = self._page(session, owner, conversation_id)
        public_turn = {k:v for k,v in turn.items() if k not in ('log_context', 'resume_instruction', 'resume_request_hash', 'recovery_state')} if turn else None
        if public_turn:
            public_turn['can_resume'] = bool(turn['resume_until'] and turn['resume_until'] > now() and turn['error'] == 'Response stopped.')
            from .response_outcomes import turn_outcome, project_outcomes
            outcome_items = page['items']
            if turn.get('assistant_sequence') and not any(item.get('sequence')==turn['assistant_sequence'] for item in outcome_items):
                if turn.get('response_outcome'):
                    outcome_items = [dict(sequence=turn['assistant_sequence'],response_outcome=turn['response_outcome'])]
                else:
                    stored = session.execute(select(m.c.metadata,m.c.role,m.c.sequence).where(m.c.learner_id==owner,
                        m.c.conversation_id==conversation_id,m.c.sequence==turn['assistant_sequence'])).mappings().first()
                    outcome_items = [self._public_message(stored)] if stored else []
                outcome_items = project_outcomes(session,owner,outcome_items)
            public_turn['response_outcome'] = turn_outcome(turn, outcome_items)
            public_turn['can_retry'] = public_turn['response_outcome'].get('retryable',False) and public_turn['response_outcome']['state'] in ('partial','failed')
            public_turn['control_action'] = public_turn['response_outcome'].get('control_action')
            if turn.get('orchestration_policy')=='semantic-v3' and turn['state']=='FAILED' and not public_turn['control_action'] and (
                    not turn['resume_until'] or turn['resume_until']<=now()):
                public_turn['can_retry']=False
            if turn['state'] == 'RUNNING':
                public_turn.update(response_outcome=dict(version=3,state='in_progress',retryable=False,tasks=[]), can_retry=False, control_action=None)
            from app.assessments.repositories.tables import generation_jobs
            public_turn['can_stop'] = turn['state'] == 'RUNNING' or bool(session.scalar(select(generation_jobs.c.id).where(
                generation_jobs.c.learner_id == owner, generation_jobs.c.source_turn_id == turn['id'],
                generation_jobs.c.state.in_(['queued', 'running'])).limit(1)))
        return dict(conversation=row, turn=public_turn, incremental=incremental, **page)

    def edit(self, owner, conversation_id, revision, title=None, remove=False):
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            row = self._conversation(session, owner, conversation_id, True)
            if row['revision'] != revision:
                raise conflict()
            values = dict(revision=revision+1, updated_at=now())
            if remove:
                from app.history_management.repositories.tables import capture_jobs
                session.execute(delete(capture_jobs).where(capture_jobs.c.learner_id == owner, capture_jobs.c.conversation_id == conversation_id))
                from .tables import summary_jobs
                session.execute(delete(summary_jobs).where(summary_jobs.c.learner_id == owner, summary_jobs.c.conversation_id == conversation_id))
                values['deleted_at'] = now()
                from app.history_management.repositories.postgres import MemoryRepository
                MemoryRepository.detach_chat(session, owner, conversation_id)
                from app.history_management.repositories.events.postgres import EventRepository
                EventRepository.detach_chat(session, owner, conversation_id)
                from app.history_management.repositories.events.proposals import EventProposalRepository
                EventProposalRepository.detach_chat(session, owner, conversation_id)
                # Keep only the conversation tombstone; content is actually removed.
                from .tables import attachments, summaries
                from app.langchain.repositories.response_checkpoints import delete_response_checkpoints
                for identifier in session.scalars(select(t.c.id).where(t.c.conversation_id == conversation_id, t.c.learner_id == owner)):
                    delete_response_checkpoints(session, owner, identifier)
                session.execute(delete(summaries).where(summaries.c.conversation_id == conversation_id, summaries.c.learner_id == owner))
                from app.assessments.repositories.chat import ChatAssessmentRepository
                ChatAssessmentRepository.detach_chat(session, owner, conversation_id)
                session.execute(delete(attachments).where(attachments.c.conversation_id == conversation_id, attachments.c.learner_id == owner))
                session.execute(delete(t).where(t.c.conversation_id == conversation_id, t.c.learner_id == owner))
                session.execute(delete(m).where(m.c.conversation_id == conversation_id, m.c.learner_id == owner))
                values['message_count'] = 0
            else:
                values['title'] = title.strip()
                if not values['title']:
                    raise AppError('CHAT_TITLE_INVALID', 'Enter a conversation title.', 422)
            session.execute(update(c).where(c.c.id == conversation_id).values(**values))
            self._change(session, owner, conversation_id, state)
            return dict(row, **values)

    def context_rows(self, owner, conversation_id, through=None, limit=256):
        with self.sessions() as session:
            self._conversation(session, owner, conversation_id)
            # Completed exchanges only, plus the current question. Failed questions remain visible in UI history.
            completed = select(t.c.user_sequence).where(t.c.learner_id == owner, t.c.conversation_id == conversation_id, t.c.state == 'SUCCEEDED')
            query = select(m.c.id, m.c.sequence, func.md5(m.c.role + m.c.content).label('content_version'),
                func.md5(cast(m.c.metadata, Text)).label('metadata_version')).where(m.c.learner_id == owner, m.c.conversation_id == conversation_id,
                m.c.metadata['response_stopped'].as_boolean().is_not(True),
                or_(m.c.role != 'user', m.c.sequence.in_(completed), m.c.sequence == through if through is not None else False))
            if through is not None:
                query = query.where(m.c.sequence <= through)
            versions = session.execute(query.order_by(m.c.sequence.desc()).limit(max(1, min(limit, 1000)))).mappings().all()
            cached = self._contexts.get((owner, conversation_id)) or {}
            missing = [row['id'] for row in versions if row['id'] not in cached or
                cached[row['id']][0] != (row['content_version'], row['metadata_version'])]
            missing_ids = set(missing)
            fresh = {row['id']: dict(row) for row in session.execute(select(m).where(m.c.learner_id == owner,
                m.c.conversation_id == conversation_id, m.c.id.in_(missing))).mappings()} if missing else {}
            result, retained = [], {}
            for row in reversed(versions):
                value = fresh.get(row['id']) or (cached[row['id']][1] if row['id'] in cached and row['id'] not in missing_ids else None)
                if value is not None:
                    result.append(value)
                    retained[row['id']] = ((row['content_version'], row['metadata_version']), value)
            # Bound bytes as well as entry count. Unusually large windows still
            # load correctly, without occupying unbounded process memory.
            if len(json.dumps(result, default=str).encode()) <= 262144:
                self._contexts.put((owner, conversation_id), retained)
            return result

    def summary_rows(self, owner, conversation_id, after, before=None):
        with self.sessions() as session:
            self._conversation(session, owner, conversation_id)
            # Read oldest unsummarized completed exchanges so long chats cannot skip gaps.
            query = (select(m).join(t, and_(t.c.conversation_id == m.c.conversation_id,
                t.c.learner_id == m.c.learner_id, or_(t.c.user_sequence == m.c.sequence, t.c.assistant_sequence == m.c.sequence)))
                .where(m.c.learner_id == owner, m.c.conversation_id == conversation_id, m.c.sequence > after,
                    t.c.state == 'SUCCEEDED', m.c.metadata['response_stopped'].as_boolean().is_not(True)))
            if before is not None:
                query = query.where(m.c.sequence < before)
            rows = session.execute(query.order_by(m.c.sequence).limit(512)).mappings().all()
            return [dict(row) for row in rows]
