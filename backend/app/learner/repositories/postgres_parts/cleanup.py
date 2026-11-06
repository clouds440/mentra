"""Explicit maintenance only: preview and guarded removal of abandoned stages."""
from hashlib import sha256
from datetime import timedelta
from sqlalchemy import select,delete,cast,Text,or_,inspect,MetaData,Table,text,LargeBinary,func
from sqlalchemy.dialects.postgresql import JSONB
from .base import PostgresRepositoryBase,utcnow
from ..tables import concept
from ..tables.topics import topic_skill
from app.core.exceptions import AppError


class CleanupStore(PostgresRepositoryBase):
    def cleanup_staged_skills(self,owner,*,expected_digest=None,apply=False,after_id=''):
        # Maintenance acquires ontology/owner locks and briefly blocks writes to
        # reference tables during recheck. It never runs on a request hot path.
        with self.transaction(learner_ids=[owner],ontology=True) as repo:
            with repo._session() as session:
                inspector=inspect(session.connection())
                metadata=MetaData()
                references=[]
                for name in sorted(inspector.get_table_names()):
                    if name in ('concept','topic_skill','alembic_version'): continue
                    columns=inspector.get_columns(name)
                    if any(isinstance(col['type'],(JSONB,LargeBinary)) for col in columns) or any(
                        fk['referred_table']=='concept' for fk in inspector.get_foreign_keys(name)):
                        references.append(Table(name,metadata,autoload_with=session.connection()))
                if apply:
                    preparer=session.bind.dialect.identifier_preparer
                    for table in references:
                        session.execute(text('LOCK TABLE '+preparer.quote(table.name)+' IN SHARE ROW EXCLUSIVE MODE'))
                candidates=list(session.scalars(select(topic_skill.c.concept_id).join(concept,concept.c.id==topic_skill.c.concept_id).where(
                    topic_skill.c.learner_id==owner,topic_skill.c.concept_id>after_id,topic_skill.c.published.is_(False),
                    topic_skill.c.created_at<utcnow()-timedelta(days=7),concept.c.canonical_name.like('unclassified-%'))
                    .order_by(topic_skill.c.concept_id).limit(101)))
                next_cursor=candidates[99] if len(candidates)>100 else None
                candidates=candidates[:100]
                removable=[]
                for identifier in candidates:
                    protected=False
                    for table in references:
                        predicates=[]
                        for column in table.c:
                            if isinstance(column.type,JSONB):
                                # Nested draft/checkpoint/review and source lineage
                                # references are retained, including unknown shapes.
                                predicates.append(cast(column,Text).contains('"'+identifier+'"',autoescape=True))
                            elif isinstance(column.type,LargeBinary):
                                # PostgresSaver msgpack blobs retain literal UUID
                                # strings. Do not discard resumable tool state.
                                predicates.append(func.encode(column,'escape').contains(identifier,autoescape=True))
                            elif any(fk.column.table.name=='concept' for fk in column.foreign_keys):
                                predicates.append(column==identifier)
                        if predicates and session.scalar(select(select(table).where(or_(*predicates)).exists())):
                            protected=True;break
                    # A shared canonical identity may belong to another owner.
                    if session.scalar(select(topic_skill.c.concept_id).where(topic_skill.c.concept_id==identifier,
                            topic_skill.c.learner_id!=owner).limit(1)): protected=True
                    if not protected: removable.append(identifier)
                digest=sha256((str(owner)+'\n'+after_id+'\n'+'\n'.join(removable)).encode()).hexdigest()
                if apply:
                    if expected_digest!=digest:
                        raise AppError('LEARNER_CLEANUP_CHANGED','The cleanup preview changed. Preview it again.',409)
                    session.execute(delete(topic_skill).where(topic_skill.c.learner_id==owner,topic_skill.c.concept_id.in_(removable)))
                    session.execute(delete(concept).where(concept.c.id.in_(removable)))
                return dict(ids=removable,digest=digest,applied=apply,protected=len(candidates)-len(removable),limit=100,next_cursor=next_cursor)
