"""Bounded durable activity projections fenced by the canonical chat attempt."""
from datetime import datetime, timezone, timedelta
import asyncio
from collections import deque
from time import monotonic
from app.core.logging import workflow_logger
from uuid import uuid4
from sqlalchemy import select, delete, func, text
from app.core.observability.timing import run_in_threadpool

from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from app.langchain.activity import ActivityEvent, ActivityUpdate
from .tables import activity, turns, conversations


@workflow_logger.connect_module(default_outcome='success')
class ActivityRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def ensure_active(self, owner, job, fence=None):
        with self.sessions.begin() as session:
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            turn = session.execute(select(turns).join(conversations, turns.c.conversation_id == conversations.c.id).where(
                turns.c.id == job['turn_id'], turns.c.learner_id == owner,
                conversations.c.deleted_at.is_(None))).mappings().first()
            if not turn or turn['state'] != 'RUNNING' or turn['attempt'] != job['attempt'] or turn['lease_until'] <= datetime.now(timezone.utc):
                raise AppError('CHAT_ATTEMPT_EXPIRED', 'This response is no longer running.', 409)
            if fence:
                from app.history_management.repositories.memory_summaries import MemorySummaryRepository
                return MemorySummaryRepository.current(session, owner, fence)
            return True

    def append(self, owner, job, update: ActivityUpdate):
        events = self.append_many(owner, job, [update])
        return events[0] if events else None

    def append_many(self, owner, job, updates):
        if not updates:
            return []
        with self.sessions.begin() as session:
            session.execute(text("SELECT set_config('lock_timeout', '5s', true), set_config('statement_timeout', '5s', true)"))
            lock_owner(session, owner)
            now = datetime.now(timezone.utc)
            turn = session.execute(select(turns).join(conversations, turns.c.conversation_id == conversations.c.id).where(
                turns.c.id == job['turn_id'], turns.c.learner_id == owner,
                conversations.c.deleted_at.is_(None))).mappings().first()
            if not turn or turn['state'] != 'RUNNING' or turn['attempt'] != job['attempt'] or turn['lease_until'] <= now:
                raise AppError('CHAT_ATTEMPT_EXPIRED', 'This response is no longer running.', 409)
            scope = (activity.c.learner_id == owner, activity.c.turn_id == job['turn_id'], activity.c.attempt == job['attempt'])
            sequence = session.execute(select(func.coalesce(func.max(activity.c.sequence), 0)).where(*scope)).scalar_one() + 1
            first_batch = sequence == 1
            events, rows = [], []
            for update in updates:
                if sequence > 256 or (sequence > 192 and (update.token_delta is not None or update.step_id == 'response-stream')):
                    continue
                event = ActivityEvent(**update.model_dump(), event_id=uuid4(), conversation_id=turn['conversation_id'],
                    turn_id=turn['id'], attempt=turn['attempt'], sequence=sequence, occurred_at=now)
                events.append(event)
                rows.append(dict(learner_id=owner, turn_id=turn['id'], attempt=turn['attempt'],
                    sequence=sequence, created_at=now, payload=event.model_dump(mode='json')))
                sequence += 1
            if rows:
                session.execute(activity.insert(), rows)
            # Retention runs once per attempt, never once per token/progress update.
            if first_batch:
                session.execute(delete(activity).where(activity.c.learner_id == owner, activity.c.created_at < now - timedelta(days=1)))
            return events

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
    """One bounded ordered writer per attempt; domain writes still fence directly."""
    def __init__(self, repository, owner, job):
        self.repository, self.owner, self.job = repository, owner, job
        self.pending = deque()
        self.writer = None
        self.error = None
        self.closed = False

    def check(self):
        if isinstance(self.error, AppError) and self.error.code in ('CHAT_ATTEMPT_EXPIRED', 'CHAT_STALE_ATTEMPT', 'CHAT_DELETED', 'CHAT_NOT_FOUND'):
            raise self.error

    async def publish(self, update):
        self.check()
        if self.closed or self.error:
            return
        if len(self.pending) >= 256:
            await self.flush()
        if self.error:
            return
        self.pending.append((monotonic(), update))
        if self.writer is None or self.writer.done():
            self.writer = asyncio.create_task(self._write())

    async def _write(self):
        try:
            # Coalesce the synchronous planned/running bursts from concurrent reads.
            await asyncio.sleep(.02)
            while self.pending:
                batch = [self.pending.popleft() for _ in range(min(32, len(self.pending)))]
                workflow_logger.event('activity.queue', duration_ms=round((monotonic()-batch[0][0])*1000, 3), event_count=len(batch))
                await run_in_threadpool(self.repository.append_many, self.owner, self.job, [update for _, update in batch])
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.error = error
            self.pending.clear()
            workflow_logger.event('activity.failed', error_code=getattr(error, 'code', 'ACTIVITY_UNAVAILABLE'))

    async def flush(self):
        if self.error is not None:
            self.check()
            return
        if self.writer is not None:
            try:
                # A timeout belongs to this reporting wait, not to every
                # publisher awaiting the same writer. close() owns cancellation.
                await asyncio.wait_for(asyncio.shield(self.writer), timeout=5)
            except TimeoutError:
                self.error = TimeoutError('Activity publication timed out')
                self.pending.clear()
                workflow_logger.event('activity.failed', error_code='ACTIVITY_TIMEOUT')
        self.check()

    async def close(self):
        self.closed = True
        self.pending.clear()
        if self.writer is not None and not self.writer.done():
            self.writer.cancel()
            await asyncio.gather(self.writer, return_exceptions=True)

    async def ensure_active(self):
        self.check()
        await run_in_threadpool(self.repository.ensure_active, self.owner, self.job)
