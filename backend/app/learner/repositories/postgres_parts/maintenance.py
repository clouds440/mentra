from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, or_, and_, case
from sqlalchemy.dialects.postgresql import insert
from .base import PostgresRepositoryBase
from ..tables.maintenance import maintenance_jobs as jobs


class MaintenanceStore(PostgresRepositoryBase):
    def enqueue_maintenance(self, owner, context_id, kind='organization'):
        now = datetime.now(timezone.utc)
        statement = insert(jobs).values(learner_id=owner, context_id=context_id,
            kind=kind, state='queued', attempts=0, created_at=now, updated_at=now)
        with self._session() as session:
            # updated_at records work arriving during an active lease. Completion
            # requeues that work instead of losing an overlapping publication.
            session.execute(statement.on_conflict_do_update(index_elements=['learner_id','context_id','kind'],
                set_=dict(updated_at=now,
                    state=case((jobs.c.state=='running','running'),else_='queued'),
                    attempts=case((jobs.c.state=='running',jobs.c.attempts),else_=0),
                    retry_at=None)))

    def claim_maintenance(self):
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            session.execute(update(jobs).where(jobs.c.state=='running',jobs.c.attempts>=3,
                jobs.c.claim_until<=now).values(state='failed',claim_id=None,claim_until=None,retry_at=None))
            row = session.execute(select(jobs).where(jobs.c.attempts<3,
                or_(jobs.c.state=='queued', and_(jobs.c.state=='running',jobs.c.claim_until<=now),
                    and_(jobs.c.state=='failed',jobs.c.retry_at<=now)))
                .order_by(jobs.c.created_at,jobs.c.learner_id).limit(1).with_for_update(skip_locked=True)).mappings().first()
            if not row: return None
            claim = str(uuid4())
            session.execute(update(jobs).where(jobs.c.learner_id==row['learner_id'],jobs.c.context_id==row['context_id'],
                jobs.c.kind==row['kind']).values(state='running',claim_id=claim,claim_until=now+timedelta(seconds=120),attempts=row['attempts']+1))
            return dict(row,claim_id=claim)

    def finish_maintenance(self, job, *, failed=False, more=False):
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            current = session.execute(select(jobs).where(jobs.c.learner_id==job['learner_id'],
                jobs.c.context_id==job['context_id'],jobs.c.kind==job['kind'], jobs.c.claim_id==job['claim_id'],
                jobs.c.state=='running',jobs.c.claim_until>now).with_for_update()).mappings().first()
            if not current: return False
            pending = more or current['updated_at']>job['updated_at']
            state = 'failed' if failed else 'queued' if pending else 'completed'
            session.execute(update(jobs).where(jobs.c.learner_id==job['learner_id'],jobs.c.context_id==job['context_id'],
                jobs.c.kind==job['kind']).values(state=state,claim_id=None,claim_until=None,
                    attempts=current['attempts'] if failed else 0,
                    retry_at=now+timedelta(seconds=5*2**current['attempts']) if failed and current['attempts']<3 else None))
            return True
