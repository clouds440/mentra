"""Content-free worker progress and bounded queue diagnostics."""
from datetime import datetime, timezone
from time import monotonic
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert
from .health import workers


class Heartbeat:
    def __init__(self,sessions):
        self.sessions,self.sent=sessions,{}

    def pulse(self,role):
        if monotonic()-self.sent.get(role,-60)<15: return
        with self.sessions.begin() as session:
            statement=insert(workers).values(role=role,last_seen=datetime.now(timezone.utc))
            session.execute(statement.on_conflict_do_update(index_elements=[workers.c.role],set_=dict(last_seen=statement.excluded.last_seen)))
        self.sent[role]=monotonic()


def queue_status(sessions,clock=lambda:datetime.now(timezone.utc)):
    from app.assessments.repositories.tables import attempts, generation_jobs, source_jobs, evidence_jobs
    from app.langchain.repositories.evidence_tables import jobs as chat_evidence
    from app.rag.repositories.tables import jobs as rag
    from app.history_management.repositories.tables import summary_jobs as memory, capture_jobs
    from app.chat.repositories.tables import summary_jobs as chat
    from app.history_management.repositories.events.tables import reminders
    from app.files.tables import assets
    stamp=clock()
    specs=[
        ('assessment.grading',attempts,attempts.c.state.in_(['submitted','grading']) | ((attempts.c.state=='failed') & attempts.c.retry_at.is_not(None)),attempts.c.created_at,attempts.c.claim_until),
        ('assessment.generation',generation_jobs,generation_jobs.c.state.in_(['queued','running']),generation_jobs.c.created_at,generation_jobs.c.claim_until),
        ('assessment.source',source_jobs,source_jobs.c.state.in_(['queued','running']) | source_jobs.c.retry_at.is_not(None),source_jobs.c.created_at,source_jobs.c.claim_until),
        ('assessment.evidence',evidence_jobs,evidence_jobs.c.state.in_(['queued','running']) | evidence_jobs.c.retry_at.is_not(None),evidence_jobs.c.created_at,evidence_jobs.c.claim_until),
        ('chat.evidence',chat_evidence,(chat_evidence.c.attempts<3) & (chat_evidence.c.state.in_(['queued','running']) | chat_evidence.c.retry_at.is_not(None)),chat_evidence.c.created_at,chat_evidence.c.claim_until),
        ('rag.ingestion',rag,rag.c.state.in_(['QUEUED','RUNNING','RETRY_WAIT']),rag.c.created_at,rag.c.lease_until),
        ('summarizer',memory,memory.c.failed.is_(False),memory.c.queued_at,memory.c.lease_until),
        ('summarizer',chat,chat.c.failed.is_(False),chat.c.queued_at,chat.c.lease_until),
        ('summarizer',capture_jobs,capture_jobs.c.failed.is_(False) & capture_jobs.c.completed_at.is_(None),capture_jobs.c.queued_at,capture_jobs.c.lease_until),
        ('events.reminders',reminders,(reminders.c.state=='pending') & (reminders.c.due_at<=stamp),reminders.c.due_at,reminders.c.due_at),
        ('files.cleanup',assets,(assets.c.state!='DELETED') & ((assets.c.state=='DELETE_PENDING') | (assets.c.expires_at<=stamp)),assets.c.created_at,assets.c.lease_until),
    ]
    result=[]
    with sessions.begin() as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        session.execute(text("SET LOCAL statement_timeout = '1s'"))
        seen=dict(session.execute(select(workers.c.role,workers.c.last_seen)).all())
        for role,table,pending,created,lease in specs:
            count,oldest,leased=session.execute(select(func.count(),func.min(created),func.count().filter(lease>stamp)).select_from(table).where(pending)).one()
            age=max(0,(stamp-oldest).total_seconds()) if oldest else 0
            heartbeat=seen.get(role)
            fresh=heartbeat is not None and (stamp-heartbeat).total_seconds()<60
            status='idle' if not count else 'observed' if fresh else 'leased' if leased else 'stalled' if age>120 else 'starting'
            result.append(dict(queue=table.name,role=role,pending=count,oldest_seconds=round(age),active_leases=leased,status=status))
    return dict(status='error' if any(row['status']=='stalled' for row in result) else 'ok',queues=result)
