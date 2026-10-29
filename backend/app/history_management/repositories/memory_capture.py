"""Source-pointer jobs; existing memory admission/writes remain authoritative."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, func, or_, literal
from sqlalchemy.dialects.postgresql import insert
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from app.chat.repositories.tables import messages, turns, conversations
from app.student_profile.repositories.tables import student_profile
from app.summarization.execution import LEASE_SECONDS, MAX_ATTEMPTS, retry_delay, SummaryDeferred
from .tables import capture_jobs as j, preferences as p, memories as m, suppression
from .postgres import now, source_fingerprint


def enqueue(session, owner, message_id, turn_id, attempt):
    if not settings.memory_capture_enabled:
        return
    source = select(messages.c.id, messages.c.learner_id, messages.c.conversation_id,
          literal(turn_id, type_=j.c.turn_id.type), literal(attempt), func.coalesce(p.c.revision, 1)).select_from(messages.join(turns,
              (turns.c.conversation_id==messages.c.conversation_id) & (turns.c.learner_id==messages.c.learner_id) &
              (turns.c.user_sequence==messages.c.sequence)).outerjoin(p, p.c.learner_id == messages.c.learner_id)).where(
            turns.c.id==turn_id,turns.c.attempt==attempt,turns.c.state=='SUCCEEDED',
            messages.c.learner_id == owner, messages.c.role == 'user',
            or_(p.c.automatic_memory.is_(True), p.c.learner_id.is_(None)))
    if message_id is not None: source=source.where(messages.c.id==message_id)
    session.execute(insert(j).from_select(['message_id', 'learner_id', 'conversation_id', 'turn_id', 'source_attempt', 'preference_revision'], source).on_conflict_do_nothing())


def current(session, owner, claim):
    row = session.execute(select(j, p.c.automatic_memory, p.c.revision.label('preferences_revision'), conversations.c.deleted_at,
        turns.c.state.label('turn_state'), turns.c.attempt.label('turn_attempt')).join(conversations,
        conversations.c.id == j.c.conversation_id).join(turns, turns.c.id == j.c.turn_id).outerjoin(p, p.c.learner_id == j.c.learner_id)
        .where(j.c.learner_id == owner, j.c.message_id == claim['message_id'], j.c.lease_token == claim['token'], j.c.lease_until > now())).mappings().first()
    if not row or row['deleted_at'] is not None or row['automatic_memory'] is False or (row['preferences_revision'] or 1) != claim['preference_revision']:
        raise AppError('MEMORY_CAPTURE_CANCELLED', 'Automatic capture was cancelled.', 409)
    if row['turn_state'] != 'SUCCEEDED' or row['turn_attempt'] != claim['source_attempt']:
        raise AppError('MEMORY_CAPTURE_CANCELLED', 'The source turn changed.', 409)
    # A new background memory would invalidate a running answer's strict context
    # fence. Defer capture instead of cancelling/repeating the visible answer.
    if session.scalar(select(turns.c.id).where(turns.c.learner_id == owner, turns.c.state == 'RUNNING').limit(1)):
        raise SummaryDeferred(now() + timedelta(seconds=2))
    return row


class MemoryCaptureRepository:
    def __init__(self, sessions): self.sessions = sessions

    def claim(self):
        with self.sessions.begin() as session:
            rows = list(session.execute(select(j.c.message_id, j.c.learner_id).join(conversations, conversations.c.id == j.c.conversation_id)
                .where(conversations.c.deleted_at.is_(None), j.c.completed_at.is_(None), j.c.failed.is_(False), j.c.available_at <= now(),
                    or_(j.c.lease_until.is_(None), j.c.lease_until < now())).order_by(j.c.queued_at, j.c.message_id).limit(24)))
            seen = set()
            for identifier, owner in rows:
                if owner in seen: continue
                seen.add(owner)
                from app.chat.repositories.tables import sync_state
                if not session.execute(select(sync_state).where(sync_state.c.learner_id == owner).with_for_update(skip_locked=True)).first():
                    continue
                if session.scalar(select(turns.c.id).where(turns.c.learner_id == owner, turns.c.state == 'RUNNING').limit(1)):
                    continue
                if session.scalar(select(j.c.message_id).where(j.c.learner_id == owner, j.c.lease_until > now()).limit(1)):
                    continue
                row = session.execute(select(j).where(j.c.message_id == identifier, j.c.completed_at.is_(None),
                    j.c.failed.is_(False), or_(j.c.lease_until.is_(None), j.c.lease_until < now()))
                    .with_for_update(skip_locked=True)).mappings().first()
                if row:
                    token = str(uuid4()); session.execute(update(j).where(j.c.message_id == identifier).values(lease_token=token, lease_until=now()+timedelta(seconds=LEASE_SECONDS)))
                    return dict(row, token=token)

    def packet(self, claim):
        with self.sessions.begin() as session:
            current(session, claim['learner_id'], claim)
            if session.scalar(select(suppression.c.fingerprint).where(suppression.c.learner_id == claim['learner_id'],
                    suppression.c.fingerprint == source_fingerprint(claim['message_id']))):
                return None
            source = session.execute(select(messages).where(messages.c.id == claim['message_id'], messages.c.learner_id == claim['learner_id'], messages.c.role == 'user')).mappings().first()
            if not source: return None
            offset = claim['content_offset']; text = source['content'][offset:offset+6000]
            profile = session.scalar(select(student_profile.c.details).where(student_profile.c.learner_id == claim['learner_id']))
            existing = [dict(row) for row in session.execute(select(m).where(
                m.c.learner_id == claim['learner_id'], m.c.status == 'active').order_by(m.c.pinned.desc(), m.c.updated_at.desc()).limit(12)).mappings()]
            active_count=session.scalar(select(func.count()).select_from(m).where(m.c.learner_id==claim['learner_id'],m.c.status=='active'))
            return dict(source=dict(source), text=text, prefix=source['content'][:500] if offset else '',
                next_offset=offset+len(text), complete=offset+len(text) >= len(source['content']), profile=profile, existing=existing,active_count=active_count)

    def finish(self, claim, *, packet=None, error=None, retry_at=None):
        with self.sessions.begin() as session:
            lock_owner(session, claim['learner_id'])
            scope = (j.c.message_id == claim['message_id'], j.c.learner_id == claim['learner_id'], j.c.lease_token == claim['token'], j.c.lease_until > now())
            attempts = claim['attempts'] + 1 if error else 0
            values = dict(lease_token=None, lease_until=None, attempts=attempts, failed=attempts >= MAX_ATTEMPTS,
                error_code=type(error).__name__ if error else None, available_at=retry_at or now()+timedelta(seconds=retry_delay(attempts) if error else 0))
            if not error and not retry_at:
                if packet: values['content_offset'] = packet['next_offset']
                if packet is None or packet['complete']: values['completed_at'] = now()
            return bool(session.execute(update(j).where(*scope).values(**values)).rowcount)

    def diagnostics(self):
        with self.sessions() as session:
            return dict(session.execute(select(func.count().filter(j.c.completed_at.is_(None)).label('pending'),
                func.count().filter(j.c.failed).label('failed'), func.count().filter(j.c.completed_at.is_not(None)).label('completed'))).mappings().one())

    def backfill(self, owner, days=30):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            # Historical consent cannot be reconstructed after a preference toggle.
            pref = session.execute(select(p).where(p.c.learner_id == owner)).mappings().first()
            if pref and (not pref['automatic_memory'] or pref['revision'] != 1):
                raise AppError('MEMORY_BACKFILL_DISABLED', 'Historical automatic-memory consent is unavailable.', 409)
            if session.scalar(select(suppression.c.fingerprint).where(suppression.c.learner_id == owner).limit(1)):
                raise AppError('MEMORY_BACKFILL_DISABLED', 'Historical replay is disabled to preserve forgotten information.', 409)
            rows = list(session.execute(select(messages.c.id, turns.c.id.label('turn_id'), turns.c.attempt).join(turns,
                (turns.c.conversation_id == messages.c.conversation_id) & (turns.c.user_sequence == messages.c.sequence)).join(conversations,
                conversations.c.id == messages.c.conversation_id).where(messages.c.learner_id == owner, messages.c.role == 'user',
                    turns.c.state == 'SUCCEEDED', conversations.c.deleted_at.is_(None), messages.c.created_at >= now()-timedelta(days=days)).limit(300)))
            for row in rows: enqueue(session, owner, row.id, row.turn_id, row.attempt)
            return len(rows)
