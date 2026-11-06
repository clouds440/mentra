import json
from hashlib import sha256
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from sqlalchemy import select,update,and_,or_,func,literal
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert
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
        # One INSERT SELECT in the response transaction: durable after commit,
        # with all semantic classification and source reads off the hot path.
        stamp=datetime.now(timezone.utc)
        source=select(turns.c.id,turns.c.learner_id,turns.c.attempt,literal('queued'),literal(0),
            literal(stamp),literal(workflow_logger.envelope(),JSONB)).where(turns.c.id == job['turn_id'],
            turns.c.learner_id == owner, turns.c.attempt == job['attempt'], turns.c.state == 'SUCCEEDED',
            or_(turns.c.response_outcome.is_(None),turns.c.response_outcome['state'].astext=='completed'))
        statement=insert(jobs).from_select(['turn_id','learner_id','attempt','state','attempts','created_at','log_context'],source)
        # Retire/requeue only an older, unapplied source attempt. Accepted evidence
        # and an in-flight claim must never be silently overwritten on replay.
        session.execute(statement.on_conflict_do_update(index_elements=[jobs.c.turn_id],
            set_=dict(attempt=job['attempt'], state='queued', attempts=0, claim_id=None,
                claim_until=None, retry_at=None, disposition=None,progress={},created_at=stamp,log_context=workflow_logger.envelope()),
            where=(jobs.c.attempt < job['attempt']) & jobs.c.state.in_(['queued','ignored','failed'])))

    def source(self,session,owner,turn_id,attempt):
        turn=session.execute(select(turns).join(conversations,(turns.c.conversation_id==conversations.c.id)&(turns.c.learner_id==conversations.c.learner_id)).where(turns.c.learner_id==owner,turns.c.id==turn_id,conversations.c.deleted_at.is_(None))).mappings().first()
        if not turn or turn['attempt']!=attempt or turn['state']!='SUCCEEDED' or (turn.get('response_outcome') or {}).get('state') not in (None,'completed'):
            raise AppError('EVIDENCE_SOURCE_EXPIRED','Evidence source is no longer available.',409)
        rows=session.execute(select(messages).where(messages.c.learner_id==owner,messages.c.conversation_id==turn['conversation_id'],messages.c.sequence.in_([turn['user_sequence']-1,turn['user_sequence'],turn['assistant_sequence']]))).mappings().all()
        question = next((row for row in rows if row['role']=='assistant' and row['sequence']==turn['user_sequence']-1), None)
        reply=next((row for row in rows if row['role']=='assistant' and row['sequence']==turn['assistant_sequence']),None)
        user = next((row for row in rows if row['role']=='user'), None)
        if user is None:
            raise AppError('EVIDENCE_SOURCE_EXPIRED', 'Evidence source is no longer available.', 409)
        sources=[dict(id='user',kind='user',text=user['content'],revision=sha256(user['content'].encode()).hexdigest(),coverage='complete')]
        from app.chat.repositories.tables import attachments
        ids=[str(value) for value in turn['attachment_ids'] or []][:4]
        unavailable=0
        if ids:
            attached=session.execute(select(attachments.c.id,attachments.c.extraction).where(attachments.c.learner_id==owner,
                attachments.c.conversation_id==turn['conversation_id'],attachments.c.id.in_(ids))).mappings().all()
            unavailable=len(ids)-len(attached)
            for item in attached:
                extraction=item['extraction'] or {};blocks=extraction.get('blocks') or []
                text='\n\n'.join(block.get('text','') for block in blocks[:32])
                if not text:
                    unavailable+=1;continue
                sources.append(dict(id=str(item['id']),kind='attachment',text=text[:8000],
                    revision=str(extraction.get('reader_revision','unverified'))+':'+sha256(text[:8000].encode()).hexdigest(),
                    coverage='partial' if len(blocks)>32 or len(text)>8000 else 'complete'))
        tasks=((reply['metadata'] if reply else {}).get('response_outcome') or {}).get('tasks',[])
        formal=any(task.get('operation')=='assessment_answer' for task in tasks)
        digest=sha256(json.dumps(dict(sources=sources,formal=formal,
            question=question['content'] if question else ''),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return dict(turn=dict(turn),question=question['content'] if question else '',user=dict(user),
            sources=sources,source_hash=digest,formal_assessment=formal,unavailable_attachments=unavailable)

    def claim(self):
        now=datetime.now(timezone.utc)
        self.sweep_exhausted(now)
        with self.sessions() as session:
            eligible = select(jobs.c.turn_id, jobs.c.learner_id, jobs.c.created_at,
                func.row_number().over(partition_by=jobs.c.learner_id, order_by=(jobs.c.created_at, jobs.c.turn_id)).label('owner_rank')).where(
                jobs.c.attempts<3,or_(jobs.c.state=='queued',and_(jobs.c.state=='running',jobs.c.claim_until<=now),and_(jobs.c.state=='failed',jobs.c.retry_at<=now))).subquery()
            candidates = session.execute(select(eligible.c.turn_id, eligible.c.learner_id).order_by(
                eligible.c.owner_rank, eligible.c.created_at, eligible.c.turn_id).limit(32)).all()
        for turn_id, owner in candidates:
            with self.transactions.try_write(owner) as tx:
                if tx is None:
                    continue
                row=tx._session.execute(select(jobs).where(jobs.c.turn_id==turn_id,jobs.c.learner_id==owner)).mappings().first()
                if not row or row['state'] in ('applied','ignored') or row['attempts']>=3 or row['claim_until'] and row['claim_until']>now:
                    continue
                if row['state']=='failed' and (not row['retry_at'] or row['retry_at']>now):
                    continue
                try:
                    source=self.source(tx._session,owner,turn_id,row['attempt'])
                except AppError as error:
                    if error.code != 'EVIDENCE_SOURCE_EXPIRED':
                        raise
                    tx._session.execute(update(jobs).where(jobs.c.turn_id==turn_id,
                        jobs.c.learner_id==owner).values(state='ignored',disposition='source_expired',
                            receipt=dict(version=2,signal_ids=[],disposition='source_expired'),progress={},claim_id=None,claim_until=None,retry_at=None))
                    continue
                claim=str(uuid4())
                tx._session.execute(update(jobs).where(jobs.c.turn_id==turn_id).values(state='running',claim_id=claim,claim_until=now+timedelta(seconds=90),attempts=row['attempts']+1))
                return dict(owner=owner,turn_id=turn_id,attempt=row['attempt'],claim_id=claim,log_context=row['log_context'],
                    created_at=row['created_at'],progress=row['progress'],previous_receipt=row['receipt'] or {},capture_attempt=row['attempts']+1,**source)
        return None

    def sweep_exhausted(self, now):
        with self.sessions() as session:
            candidates = session.execute(select(jobs.c.turn_id, jobs.c.learner_id).where(
                jobs.c.state == 'running', jobs.c.attempts >= 3, jobs.c.claim_until <= now).limit(32)).all()
        for turn_id, owner in candidates:
            with self.transactions.try_write(owner) as tx:
                if tx is not None:
                    tx._session.execute(update(jobs).where(jobs.c.turn_id == turn_id, jobs.c.learner_id == owner,
                        jobs.c.state == 'running', jobs.c.attempts >= 3, jobs.c.claim_until <= now).values(
                            state='failed', disposition='retry_exhausted',claim_id=None, claim_until=None, retry_at=None))

    def complete(self,job,apply,*,disposition='no_supported_signal'):
        with self.transactions.write(job['owner']) as tx:
            row=tx._session.execute(select(jobs).where(jobs.c.turn_id==job['turn_id'],jobs.c.learner_id==job['owner'])).mappings().first()
            if not row:return
            if row['attempt']==job['attempt'] and row['state'] in ('applied','ignored'): return row['receipt']
            if row['claim_id']!=job['claim_id'] or row['claim_until']<=datetime.now(timezone.utc):raise AppError('EVIDENCE_CLAIM_EXPIRED','Evidence claim expired.',409)
            current=self.source(tx._session,job['owner'],job['turn_id'],job['attempt'])
            if current['source_hash']!=job['source_hash']: raise AppError('EVIDENCE_SOURCE_EXPIRED','Learning-signal source changed.',409)
            receipt=apply(tx)
            tx._session.execute(update(jobs).where(jobs.c.turn_id==job['turn_id']).values(state='applied' if receipt and receipt.get('signal_ids') else 'ignored',
                disposition=disposition,receipt=receipt,claim_id=None,claim_until=None,progress={},retry_at=None))
            workflow_logger.event('learner.signal_capture_terminal',disposition=disposition,signals=len((receipt or {}).get('signal_ids',[])),
                lag_ms=round((datetime.now(timezone.utc)-row['created_at']).total_seconds()*1000))
            return receipt

    def checkpoint(self,job,progress):
        now=datetime.now(timezone.utc)
        with self.sessions.begin() as session:
            result=session.execute(update(jobs).where(jobs.c.turn_id==job['turn_id'],jobs.c.learner_id==job['owner'],
                jobs.c.claim_id==job['claim_id'],jobs.c.state=='running',jobs.c.claim_until>now).values(
                    progress=progress,claim_until=now+timedelta(seconds=90)))
            if result.rowcount!=1: raise AppError('EVIDENCE_CLAIM_EXPIRED','Signal capture ownership changed.',409)

    def complete_signals(self,job,signals,disposition,rejected):
        from uuid import uuid5,NAMESPACE_URL
        from app.learner.repositories.tables.signals import learning_signals
        def apply(tx):
            # Source revisions supersede observations, never the original source
            # or a student's explicit withdrawal. Unchanged sources are skipped
            # by the worker when an attachment becomes available later.
            for source in job['sources']:
                tx._session.execute(update(learning_signals).where(learning_signals.c.learner_id==job['owner'],
                    learning_signals.c.turn_id==job['turn_id'],learning_signals.c.attempt==job['attempt'],
                    learning_signals.c.source_id==source['id'],learning_signals.c.source_revision!=source['revision'],
                    learning_signals.c.status.in_(['active','pending'])).values(status='withdrawn',
                        details=learning_signals.c.details.op('||')(dict(withdrawal='source_superseded'))))
            for signal in signals:
                identifier=str(uuid5(NAMESPACE_URL,f"learning-signal:{job['owner']}:{job['turn_id']}:{job['attempt']}:{signal['fingerprint']}"))
                tx._session.execute(insert(learning_signals).values(id=identifier,learner_id=job['owner'],turn_id=job['turn_id'],
                    attempt=job['attempt'],observed_at=job['user']['created_at'],**signal).on_conflict_do_nothing())
            rows=tx._session.execute(select(learning_signals.c.id,learning_signals.c.status).where(
                learning_signals.c.learner_id==job['owner'],learning_signals.c.turn_id==job['turn_id'],
                learning_signals.c.attempt==job['attempt'],learning_signals.c.status.in_(['active','pending']))).all()
            return dict(version=2,signal_ids=[row.id for row in rows],rejected=rejected,disposition=disposition,
                source_hash=job['source_hash'],unavailable_attachments=job['unavailable_attachments'],
                source_coverage=job.get('source_coverage',{}),
                source_revisions={source['id']:source['revision'] for source in job['sources']})
        return self.complete(job,apply,disposition=disposition)

    def fail(self,job,*,deferred=False,reason='classifier_failure'):
        with self.transactions.write(job['owner']) as tx:
            row=tx._session.execute(select(jobs).where(jobs.c.turn_id==job['turn_id'],jobs.c.learner_id==job['owner'])).mappings().first()
            if not row or row['claim_id']!=job['claim_id']:return
            tx._session.execute(update(jobs).where(jobs.c.turn_id==job['turn_id']).values(state='failed',claim_id=None,claim_until=None,
                disposition=reason,
                attempts=max(0,row['attempts']-1) if deferred else row['attempts'],
                retry_at=datetime.now(timezone.utc)+timedelta(seconds=5 if deferred else 5*2**row['attempts'])))
        workflow_logger.event('job.retry_scheduled' if row['attempts'] < 3 else 'job.failed', turn_id=job['turn_id'], attempt=row['attempts'])
