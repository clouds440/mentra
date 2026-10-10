"""Short transactions; no model calls or network I/O while holding locks."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from uuid import uuid4, UUID
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.dialects.postgresql import insert
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
        return {**metadata, **value}

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

    def begin_turn(self, owner, request):
        conversation_id, turn_id = str(request.conversation_id), str(request.client_turn_id)
        content = request.content
        selection = request.retrieval.model_dump(mode='json')
        attachment_ids = list(dict.fromkeys(str(value) for value in request.attachment_ids))
        # Retain fingerprints for existing clients/turns without attachments.
        fingerprint = sha256(json.dumps([conversation_id, content, selection] + ([attachment_ids] if attachment_ids else []), sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            existing = session.execute(select(t).where(t.c.id == turn_id)).mappings().first()
            if existing:
                if existing['learner_id'] != owner or existing['request_hash'] != fingerprint:
                    raise AppError('CHAT_IDEMPOTENCY_CONFLICT', 'This send identifier is already in use.', 409)
                conversation = self._conversation(session, owner, conversation_id, True)
                if existing['state'] == 'RUNNING' and existing['lease_until'] < now():
                    session.execute(update(t).where(t.c.id == turn_id).values(state='FAILED', error='Generation interrupted. Retry this message.', lease_until=None))
                    conversation['revision'] += 1
                    session.execute(update(c).where(c.c.id == conversation_id).values(revision=conversation['revision'], updated_at=now()))
                    if not request.retry:
                        self._change(session, owner, conversation_id, state)
                    existing = dict(existing, state='FAILED', error='Generation interrupted. Retry this message.')
                if not request.retry or existing['state'] != 'FAILED':
                    return dict(run=False, turn_id=turn_id, conversation_id=conversation_id)
                # Only the most recent question can be retried without branching history.
                if conversation['message_count'] != existing['user_sequence']:
                    raise conflict()
                attempt = existing['attempt'] + 1
                session.execute(update(t).where(t.c.id == turn_id).values(state='RUNNING', error=None, attempt=attempt, lease_until=now() + timedelta(minutes=3),log_context=workflow_logger.envelope()))
                session.execute(update(c).where(c.c.id == conversation_id).values(revision=conversation['revision']+1, updated_at=now()))
                self._change(session, owner, conversation_id, state)
                return dict(run=True, turn_id=turn_id, conversation_id=conversation_id, attempt=attempt, selection=selection, attachment_ids=attachment_ids, user_sequence=existing['user_sequence'], title_revision=conversation['revision']+1)
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
            sequence = conversation['message_count'] + 1
            from .attachments import AttachmentRepository
            attachment_metadata = AttachmentRepository.bind(session, owner, attachment_ids, conversation_id)
            session.execute(m.insert().values(id=str(uuid4()), learner_id=owner, conversation_id=conversation_id, sequence=sequence,
                role='user', content=content, metadata={'attachments': attachment_metadata} if attachment_metadata else {}, created_at=now()))
            session.execute(t.insert().values(id=turn_id, learner_id=owner, conversation_id=conversation_id, request_hash=fingerprint,
                user_sequence=sequence, state='RUNNING', attempt=1, selection=selection, attachment_ids=attachment_ids, lease_until=now()+timedelta(minutes=3), created_at=now(),log_context=workflow_logger.envelope()))
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
                return
            row = session.execute(select(c).where(c.c.id == job['conversation_id'], c.c.learner_id == owner).with_for_update()).mappings().one()
            if row['deleted_at'] is not None:
                workflow_logger.set_outcome('skipped', code='CHAT_DELETED')
                from app.core.observability.context import current
                current.get().outcome = 'skipped'
                return
            values = dict(state='FAILED' if error else 'SUCCEEDED', error=error, lease_until=None)
            conversation_values = dict()
            sequence = row['message_count']
            if not error:
                sequence += 1
                payload = dict(response)
                generated_title = payload.pop('conversation_title', None)
                from app.history_management.repositories.postgres import MemoryRepository
                if not MemoryRepository.references_current(session, owner, payload):
                    payload = dict(content='The referenced memory or conversation changed while I was answering. Please send your question again so I can use the current information.', history_references=[], memory_references=[])
                    generated_title = None
                if generated_title is not None and turn['user_sequence'] == 1 and row['revision'] == job.get('title_revision'):
                    first_content = session.execute(select(m.c.content).where(m.c.conversation_id == row['id'], m.c.learner_id == owner, m.c.sequence == 1)).scalar_one()
                    if row['title'] == provisional_title(first_content):
                        try:
                            conversation_values['title'] = NewChatReply(content=payload['content'], conversation_title=generated_title).conversation_title
                        except ValidationError:
                            pass
                content = payload.pop('content')
                payload.pop('role', None)
                session.execute(m.insert().values(id=str(uuid4()), learner_id=owner, conversation_id=row['id'], sequence=sequence,
                    role='assistant', content=content, metadata=payload, created_at=now()))
                values['assistant_sequence'] = sequence
            session.execute(update(t).where(t.c.id == job['turn_id']).values(**values))
            if response is not None:
                from app.langchain.repositories.evidence import ChatEvidenceRepository
                ChatEvidenceRepository.queue(session, owner, job)
            session.execute(update(c).where(c.c.id == row['id']).values(message_count=sequence, revision=row['revision']+1, updated_at=now(), **conversation_values))
            self._change(session, owner, row['id'], state)

    def status(self, owner, conversation_id, turn_id=None, incremental=False):
        with self.sessions.begin() as session:
            # Consistent locking order across every writer.
            state = self._sync_lock(session, owner)
            row = self._conversation(session, owner, conversation_id)
            query = select(t).where(t.c.learner_id == owner, t.c.conversation_id == conversation_id)
            if turn_id:
                query = query.where(t.c.id == turn_id)
            turn = session.execute(query.order_by(t.c.user_sequence.desc()).limit(1)).mappings().first()
            if turn and turn['state'] == 'RUNNING' and turn['lease_until'] < now():
                session.execute(update(t).where(t.c.id == turn['id']).values(state='FAILED', error='Generation interrupted. Retry this message.', lease_until=None))
                row = dict(row, revision=row['revision']+1, updated_at=now())
                session.execute(update(c).where(c.c.id == conversation_id).values(revision=row['revision'], updated_at=row['updated_at']))
                self._change(session, owner, conversation_id, state)
                turn = dict(turn, state='FAILED', error='Generation interrupted. Retry this message.')
            if incremental and turn:
                rows = session.execute(select(m).where(m.c.learner_id == owner, m.c.conversation_id == conversation_id,
                    m.c.sequence.in_([turn['user_sequence'], turn['assistant_sequence']])).order_by(m.c.sequence)).mappings().all()
                page = dict(items=[self._public_message(item) for item in rows], has_more=False, next_cursor=None)
            else:
                page = self._page(session, owner, conversation_id)
            return dict(conversation=row, turn={k:v for k,v in turn.items() if k != 'log_context'} if turn else None, incremental=incremental, **page)

    def edit(self, owner, conversation_id, revision, title=None, remove=False):
        with self.sessions.begin() as session:
            state = self._sync_lock(session, owner)
            row = self._conversation(session, owner, conversation_id, True)
            if row['revision'] != revision:
                raise conflict()
            values = dict(revision=revision+1, updated_at=now())
            if remove:
                values['deleted_at'] = now()
                from app.history_management.repositories.postgres import MemoryRepository
                MemoryRepository.detach_chat(session, owner, conversation_id)
                from app.history_management.repositories.events.postgres import EventRepository
                EventRepository.detach_chat(session, owner, conversation_id)
                from app.history_management.repositories.events.proposals import EventProposalRepository
                EventProposalRepository.detach_chat(session, owner, conversation_id)
                # Keep only the conversation tombstone; content is actually removed.
                from .tables import attachments
                from app.assessments.repositories.tables import chat_drafts
                session.execute(delete(chat_drafts).where(chat_drafts.c.conversation_id == conversation_id, chat_drafts.c.learner_id == owner))
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
            query = select(m).where(m.c.learner_id == owner, m.c.conversation_id == conversation_id,
                or_(m.c.role != 'user', m.c.sequence.in_(completed), m.c.sequence == through if through is not None else False))
            if through is not None:
                query = query.where(m.c.sequence <= through)
            rows = session.execute(query.order_by(m.c.sequence.desc()).limit(max(1, min(limit, 1000)))).mappings().all()
            return [dict(row) for row in reversed(rows)]
