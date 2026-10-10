import re
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from sqlalchemy import select,update,and_,or_
from app.db.owner_transactions import OwnerTransactions
from app.chat.repositories.tables import messages,turns,conversations
from app.core.exceptions import AppError
from .evidence_tables import jobs

from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={'claim': {'quiet':True}})
class ChatEvidenceRepository:
    def __init__(self,sessions): self.sessions,self.transactions=sessions,OwnerTransactions(sessions)

    @staticmethod
    def queue(session,owner,job):
        user=session.execute(select(messages).where(messages.c.learner_id==owner,messages.c.conversation_id==job['conversation_id'],messages.c.sequence==job['user_sequence'])).mappings().first()
        if not user or len(user['content'])>12000 or user['metadata'].get('attachments'): return
        previous=session.execute(select(messages.c.content).where(messages.c.learner_id==owner,messages.c.conversation_id==job['conversation_id'],messages.c.sequence==job['user_sequence']-1,messages.c.role=='assistant')).scalar_one_or_none()
        text=user['content'].strip().casefold()
        if not previous or '?' not in previous or re.match(r'^(please|help|explain|what|how|why|can you|could you|i don.t know|my exam|remember)\b',text): return
        session.execute(jobs.insert().values(turn_id=job['turn_id'],learner_id=owner,attempt=job['attempt'],state='queued',attempts=0,created_at=datetime.now(timezone.utc),log_context=workflow_logger.envelope()))

    def source(self,session,owner,turn_id,attempt):
        turn=session.execute(select(turns).join(conversations,(turns.c.conversation_id==conversations.c.id)&(turns.c.learner_id==conversations.c.learner_id)).where(turns.c.learner_id==owner,turns.c.id==turn_id,conversations.c.deleted_at.is_(None))).mappings().first()
        if not turn or turn['attempt']!=attempt or turn['state']!='SUCCEEDED': raise AppError('EVIDENCE_SOURCE_EXPIRED','Evidence source is no longer available.',409)
        rows=session.execute(select(messages).where(messages.c.learner_id==owner,messages.c.conversation_id==turn['conversation_id'],messages.c.sequence.in_([turn['user_sequence']-1,turn['user_sequence']]))).mappings().all()
        return dict(turn=dict(turn),question=next(row['content'] for row in rows if row['role']=='assistant'),user=dict(next(row for row in rows if row['role']=='user')))

    def claim(self):
        now=datetime.now(timezone.utc)
        with self.sessions() as session:
            candidate=session.execute(select(jobs.c.turn_id,jobs.c.learner_id).where(jobs.c.attempts<3,or_(jobs.c.state=='queued',and_(jobs.c.state=='running',jobs.c.claim_until<=now),and_(jobs.c.state=='failed',jobs.c.retry_at<=now))).order_by(jobs.c.created_at).limit(1)).first()
        if not candidate:return None
        turn_id,owner=candidate
        with self.transactions.write(owner) as tx:
            row=tx._session.execute(select(jobs).where(jobs.c.turn_id==turn_id,jobs.c.learner_id==owner)).mappings().first()
            if not row or row['state'] in ('applied','ignored') or row['attempts']>=3 or row['claim_until'] and row['claim_until']>now:return None
            if row['state']=='failed' and (not row['retry_at'] or row['retry_at']>now):return None
            source=self.source(tx._session,owner,turn_id,row['attempt'])
            claim=str(uuid4())
            tx._session.execute(update(jobs).where(jobs.c.turn_id==turn_id).values(state='running',claim_id=claim,claim_until=now+timedelta(seconds=90),attempts=row['attempts']+1))
            return dict(owner=owner,turn_id=turn_id,attempt=row['attempt'],claim_id=claim,log_context=row['log_context'],**source)

    def complete(self,job,apply):
        with self.transactions.write(job['owner']) as tx:
            row=tx._session.execute(select(jobs).where(jobs.c.turn_id==job['turn_id'],jobs.c.learner_id==job['owner'])).mappings().first()
            if not row:return
            if row['claim_id']!=job['claim_id'] or row['claim_until']<=datetime.now(timezone.utc):raise AppError('EVIDENCE_CLAIM_EXPIRED','Evidence claim expired.',409)
            self.source(tx._session,job['owner'],job['turn_id'],job['attempt'])
            receipt=apply(tx)
            tx._session.execute(update(jobs).where(jobs.c.turn_id==job['turn_id']).values(state='applied' if receipt else 'ignored',receipt=receipt,claim_id=None,claim_until=None))

    def fail(self,job):
        with self.transactions.write(job['owner']) as tx:
            row=tx._session.execute(select(jobs).where(jobs.c.turn_id==job['turn_id'],jobs.c.learner_id==job['owner'])).mappings().first()
            if not row or row['claim_id']!=job['claim_id']:return
            tx._session.execute(update(jobs).where(jobs.c.turn_id==job['turn_id']).values(state='failed',claim_id=None,claim_until=None,retry_at=datetime.now(timezone.utc)+timedelta(seconds=5*2**row['attempts'])))
        workflow_logger.event('job.retry_scheduled' if row['attempts'] < 3 else 'job.failed', turn_id=job['turn_id'], attempt=row['attempts'])
