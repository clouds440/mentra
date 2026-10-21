"""Owner-first durable queue for completed chat exchanges."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.dialects.postgresql import insert
from app.db.owner_transactions import lock_owner
from app.summarization.execution import MAX_ATTEMPTS, LEASE_SECONDS, retry_delay
from .tables import summary_jobs as j, conversations as c, sync_state
from .postgres import now


def queue(session, owner, chat, sequence):
    stamp = now()
    session.execute(insert(j).values(learner_id=owner, conversation_id=chat, target_sequence=sequence,
        queued_at=stamp, available_at=stamp+timedelta(seconds=1)).on_conflict_do_update(
            index_elements=[j.c.conversation_id], set_=dict(target_sequence=func.greatest(j.c.target_sequence, sequence),
                available_at=func.least(stamp+timedelta(seconds=1), j.c.queued_at+timedelta(seconds=5)),
                failed=False, attempts=0, error_code=None)))


class ChatSummaryJobs:
    def __init__(self, sessions):
        self.sessions = sessions

    def claim(self):
        with self.sessions.begin() as session:
            candidates = list(session.execute(select(j.c.learner_id, j.c.conversation_id).join(c,
                c.c.id == j.c.conversation_id).where(c.c.deleted_at.is_(None), j.c.failed.is_(False),
                j.c.available_at <= now(), or_(j.c.lease_until.is_(None), j.c.lease_until < now()))
                .order_by(j.c.available_at).limit(16)))
            for owner, chat in candidates:
                session.execute(insert(sync_state).values(learner_id=owner, revision=0, floor=0).on_conflict_do_nothing())
                if not session.execute(select(sync_state).where(sync_state.c.learner_id == owner).with_for_update(skip_locked=True)).first():
                    continue
                row = session.execute(select(j).where(j.c.conversation_id == chat, j.c.failed.is_(False), j.c.available_at <= now(),
                    or_(j.c.lease_until.is_(None), j.c.lease_until < now())).with_for_update(skip_locked=True)).mappings().first()
                if row:
                    token = str(uuid4())
                    session.execute(update(j).where(j.c.conversation_id == chat).values(lease_token=token,
                        lease_until=now()+timedelta(seconds=LEASE_SECONDS)))
                    return dict(row, token=token)

    def finish(self, claim, *, more=False, error=None, retry_at=None):
        with self.sessions.begin() as session:
            lock_owner(session, claim['learner_id'])
            scope = (j.c.conversation_id == claim['conversation_id'], j.c.learner_id == claim['learner_id'],
                     j.c.lease_token == claim['token'], j.c.lease_until > now())
            row = session.execute(select(j).where(*scope)).mappings().first()
            if not row:
                return False
            if not more and not error and not retry_at and row['target_sequence'] == claim['target_sequence']:
                session.execute(delete(j).where(*scope))
            else:
                attempts = claim['attempts']+1 if error and row['target_sequence'] == claim['target_sequence'] else 0
                session.execute(update(j).where(*scope).values(lease_token=None, lease_until=None,
                    attempts=attempts, failed=attempts >= MAX_ATTEMPTS, error_code=type(error).__name__ if error else None,
                    available_at=retry_at or now()+timedelta(seconds=retry_delay(attempts) if error else 0)))
            return True

    def retry(self, owner, chat):
        from .tables import summaries
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            row = session.execute(select(c).where(c.c.learner_id == owner, c.c.id == chat, c.c.deleted_at.is_(None))).mappings().first()
            if not row:
                from app.core.exceptions import AppError
                raise AppError('CHAT_NOT_FOUND', 'Conversation not found.', 404)
            queue(session, owner, chat, max(1,row['message_count']))
            # Preserve live generation leases; only clear the legacy failure cooldown.
            session.execute(update(summaries).where(summaries.c.conversation_id == chat, summaries.c.learner_id == owner,
                summaries.c.lease_token.is_(None)).values(lease_until=None))

    def diagnostics(self):
        with self.sessions() as session:
            return dict(session.execute(select(func.count().label('pending'), func.count().filter(j.c.failed).label('failed'),
                func.min(j.c.queued_at).label('oldest_queued_at')).join(c, c.c.id == j.c.conversation_id)
                .where(c.c.deleted_at.is_(None))).mappings().one())
