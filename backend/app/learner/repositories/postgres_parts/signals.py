from sqlalchemy import select,update,func,literal,or_
from app.core.exceptions import AppError
from .base import PostgresRepositoryBase
from ..tables.signals import learning_signals


class SignalsStore(PostgresRepositoryBase):
    def assessment_metadata(self,owner,context_id,ids,terms):
        from ..tables.topics import topic_skill,learning_topic
        from sqlalchemy.dialects.postgresql import JSONB
        memberships=select(topic_skill,learning_topic.c.name,learning_topic.c.scope,
            learning_topic.c.context_id,learning_topic.c.revision).outerjoin(learning_topic,
                (learning_topic.c.id==topic_skill.c.topic_id)&(learning_topic.c.learner_id==owner)).where(
                    topic_skill.c.learner_id==owner,topic_skill.c.concept_id.in_(ids)).subquery()
        filters=[learning_signals.c.learner_id==owner,learning_signals.c.status=='active',
            or_(learning_signals.c.context_id==context_id,learning_signals.c.context_id.is_(None))]
        if terms:
            filters.append(or_(*[or_(learning_signals.c.normalized_label.contains(term,autoescape=True),
                func.lower(learning_signals.c.topic).contains(term,autoescape=True)) for term in terms],
                learning_signals.c.concept_id.in_(ids)))
        else:
            filters.append(learning_signals.c.concept_id.in_(ids))
        observations=select(learning_signals.c.id,learning_signals.c.kind,learning_signals.c.label,
            learning_signals.c.concept_id,learning_signals.c.quote,learning_signals.c.source_revision,
            learning_signals.c.source_kind).where(*filters).order_by(
                learning_signals.c.observed_at.desc(),learning_signals.c.id).limit(8).subquery()
        def packed(rows):
            return select(func.coalesce(func.jsonb_agg(func.to_jsonb(rows.table_valued())),literal([],type_=JSONB))).scalar_subquery()
        with self._session() as session:
            membership,signals=session.execute(select(packed(memberships),packed(observations))).one()
            return {row['concept_id']:row for row in membership},signals

    def review_signal(self,owner,identifier,context_id,concept_id,source_revision):
        from ..tables import context_concept
        with self.transaction(learner_ids=[owner]) as repo:
            with repo._session() as session:
                row=session.execute(select(learning_signals).where(learning_signals.c.learner_id==owner,
                    learning_signals.c.id==identifier).with_for_update()).mappings().first()
                if not row: raise AppError('LEARNING_SIGNAL_NOT_FOUND','Learning observation unavailable.',404)
                if row['status']=='withdrawn' or row['source_revision']!=source_revision:
                    raise AppError('LEARNING_SIGNAL_CHANGED','This source changed. Refresh before reviewing it.',409)
                owned=session.scalar(select(context_concept.c.concept_id).where(context_concept.c.learner_id==owner,
                    context_concept.c.context_id==context_id,context_concept.c.concept_id==concept_id))
                if not owned: raise AppError('LEARNING_SIGNAL_TARGET','Choose a skill in your learning area.',404)
                if row['details'].get('reviewed') and (row['context_id'],row['concept_id'])!=(context_id,concept_id):
                    raise AppError('LEARNING_SIGNAL_CHANGED','This observation was already reviewed. Refresh it.',409)
                details=dict(row['details'],reviewed=True,scoring='not_admitted')
                session.execute(update(learning_signals).where(learning_signals.c.id==identifier).values(
                    context_id=context_id,concept_id=concept_id,status='active',details=details))
                return dict(id=identifier,context_id=context_id,concept_id=concept_id,status='active',scoring='not_admitted')

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
