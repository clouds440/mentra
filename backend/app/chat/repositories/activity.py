"""Bounded durable activity projections fenced by the canonical chat attempt."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, delete, func, text
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from app.langchain.activity import ActivityEvent, ActivityUpdate
from .tables import activity, turns, conversations


class ActivityRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def append(self, owner, job, update: ActivityUpdate):
        with self.sessions.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            lock_owner(session, owner)
            now = datetime.now(timezone.utc)
            turn = session.execute(select(turns).join(conversations, turns.c.conversation_id == conversations.c.id).where(
                turns.c.id == job['turn_id'], turns.c.learner_id == owner,
                conversations.c.deleted_at.is_(None))).mappings().first()
            if not turn or turn['state'] != 'RUNNING' or turn['attempt'] != job['attempt'] or turn['lease_until'] <= now:
                raise AppError('CHAT_ATTEMPT_EXPIRED', 'This response is no longer running.', 409)
            scope = (activity.c.learner_id == owner, activity.c.turn_id == job['turn_id'], activity.c.attempt == job['attempt'])
            sequence = session.execute(select(func.coalesce(func.max(activity.c.sequence), 0)).where(*scope)).scalar_one() + 1
            if sequence > 256:
                raise AppError('ACTIVITY_LIMIT', 'The response exceeded its execution limit.', 422)
            event = ActivityEvent(**update.model_dump(), event_id=uuid4(), conversation_id=turn['conversation_id'],
                turn_id=turn['id'], attempt=turn['attempt'], sequence=sequence, occurred_at=now)
            session.execute(activity.insert().values(learner_id=owner, turn_id=turn['id'], attempt=turn['attempt'],
                sequence=sequence, created_at=now, payload=event.model_dump(mode='json')))
            # Owner-scoped retention also bounds abandoned operational payloads.
            session.execute(delete(activity).where(activity.c.learner_id == owner, activity.c.created_at < now - timedelta(days=1)))
            return event

    def page(self, owner, conversation_id, turn_id, attempt, after=0):
        with self.sessions.begin() as session:
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            turn = session.execute(select(turns).join(conversations, turns.c.conversation_id == conversations.c.id).where(
                turns.c.id == turn_id, turns.c.learner_id == owner, turns.c.conversation_id == conversation_id,
                conversations.c.deleted_at.is_(None))).mappings().first()
            if not turn:
                raise AppError('CHAT_NOT_FOUND', 'Conversation not found.', 404)
            reset = attempt != turn['attempt']
            events = session.execute(select(activity.c.payload).where(activity.c.learner_id == owner,
                activity.c.turn_id == turn_id, activity.c.attempt == turn['attempt'],
                activity.c.sequence > (0 if reset else after),
                activity.c.created_at >= datetime.now(timezone.utc) - timedelta(days=1))
                .order_by(activity.c.sequence).limit(256)).scalars().all()
            return dict(events=events, attempt=turn['attempt'], reset=reset,
                state=turn['state'], lease_until=turn['lease_until'])


class DurableActivitySink:
    def __init__(self, repository, owner, job):
        self.repository, self.owner, self.job = repository, owner, job

    async def publish(self, update):
        await run_in_threadpool(self.repository.append, self.owner, self.job, update)
