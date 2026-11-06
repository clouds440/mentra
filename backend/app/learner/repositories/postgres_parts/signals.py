from sqlalchemy import select,update
from app.core.exceptions import AppError
from .base import PostgresRepositoryBase
from ..tables.signals import learning_signals


class SignalsStore(PostgresRepositoryBase):
    def signal_page(self,owner,context_ids=None,query='',limit=20,offset=0,status='active'):
        filters=[learning_signals.c.learner_id==owner,learning_signals.c.status.in_(['active','pending']) if status=='all' else learning_signals.c.status==status]
        if context_ids is not None: filters.append(learning_signals.c.context_id.in_(context_ids))
        if query: filters.append(learning_signals.c.normalized_label.contains(query,autoescape=True))
        with self._session() as session:
            rows=list(session.execute(select(learning_signals).where(*filters).order_by(
                learning_signals.c.observed_at.desc(),learning_signals.c.id).limit(limit+1).offset(offset)).mappings())
            return dict(items=[dict(row) for row in rows[:limit]],next_offset=offset+limit if len(rows)>limit else None,
                scoring='unscored_source_observations')

    def withdraw_signal(self,owner,identifier):
        from app.db.owner_transactions import OwnerTransactions
        with OwnerTransactions(self._session_factory).write(owner) as tx:
            row=tx._session.execute(select(learning_signals.c.id).where(learning_signals.c.learner_id==owner,
                learning_signals.c.id==identifier)).first()
            if not row: raise AppError('LEARNING_SIGNAL_NOT_FOUND','Learning observation unavailable.',404)
            tx._session.execute(update(learning_signals).where(learning_signals.c.learner_id==owner,
                learning_signals.c.id==identifier).values(status='withdrawn',
                    details=learning_signals.c.details.op('||')(dict(withdrawal='user'))))

    def retry_signal_capture(self,owner,turn_id):
        from app.db.owner_transactions import OwnerTransactions
        from app.langchain.repositories.evidence_tables import jobs
        from app.chat.repositories.tables import turns,conversations
        with OwnerTransactions(self._session_factory).write(owner) as tx:
            source=tx._session.execute(select(turns).join(conversations,(turns.c.conversation_id==conversations.c.id)&
                (turns.c.learner_id==conversations.c.learner_id)).where(turns.c.learner_id==owner,
                turns.c.id==turn_id,conversations.c.deleted_at.is_(None))).mappings().first()
            job=tx._session.execute(select(jobs).where(jobs.c.learner_id==owner,jobs.c.turn_id==turn_id)).mappings().first()
            if not source or not job: raise AppError('LEARNING_SIGNAL_NOT_FOUND','Learning source unavailable.',404)
            if source['attempt']!=job['attempt'] or source['state']!='SUCCEEDED' or (source['response_outcome'] or {}).get('state') not in (None,'completed'):
                raise AppError('EVIDENCE_SOURCE_EXPIRED','Learning source is no longer available.',409)
            if job['state']!='failed': return dict(state=job['state'],disposition=job['disposition'])
            tx._session.execute(update(jobs).where(jobs.c.learner_id==owner,jobs.c.turn_id==turn_id).values(
                state='queued',attempts=0,claim_id=None,claim_until=None,retry_at=None,disposition='explicit_retry'))
            return dict(state='queued',disposition='explicit_retry')
