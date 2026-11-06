from sqlalchemy import Table,Column,Text,Integer,Double,Uuid,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,Index,text
from sqlalchemy.dialects.postgresql import JSONB
from .common import metadata,timestamp

learning_signals=Table('learning_signal',metadata,
    Column('id',Uuid(as_uuid=False),primary_key=True),
    Column('learner_id',Uuid(as_uuid=False),ForeignKey('learner.id'),nullable=False),
    Column('turn_id',Uuid(as_uuid=False),nullable=False),Column('attempt',Integer,nullable=False),
    Column('context_id',Text),Column('concept_id',Text,ForeignKey('concept.id')),
    Column('kind',Text,nullable=False),Column('label',Text,nullable=False),Column('normalized_label',Text,nullable=False),Column('topic',Text,nullable=False),
    Column('source_id',Text,nullable=False),Column('source_kind',Text,nullable=False),Column('source_revision',Text,nullable=False),
    Column('quote',Text,nullable=False),Column('span_start',Integer,nullable=False),Column('span_end',Integer,nullable=False),
    Column('confidence',Double,nullable=False),Column('fingerprint',Text,nullable=False),Column('details',JSONB,nullable=False),
    Column('status',Text,nullable=False,server_default='active'),timestamp('observed_at'),timestamp('created_at'),
    ForeignKeyConstraint(['learner_id','turn_id'],['chat_turn.learner_id','chat_turn.id'],ondelete='CASCADE'),
    ForeignKeyConstraint(['learner_id','context_id'],['learning_context.learner_id','learning_context.id']),
    UniqueConstraint('learner_id','turn_id','attempt','fingerprint',name='uq_learning_signal_source'),
    CheckConstraint("kind IN ('encounter','struggle','self_report','guided_work','demonstration') AND status IN ('active','pending','withdrawn') AND source_kind IN ('user','attachment') AND confidence BETWEEN 0 AND 1 AND span_start >= 0 AND span_end > span_start AND attempt > 0",name='learning_signal_bounds'),
    Index('idx_learning_signal_context','learner_id','context_id','status','observed_at','id'),
    Index('idx_learning_signal_recent','learner_id','status','observed_at','id'),
    Index('idx_learning_signal_label','learner_id','normalized_label','topic','observed_at'),
    Index('idx_learning_signal_search',text("to_tsvector('simple'::regconfig, (normalized_label || ' '::text) || topic)"),postgresql_using='gin'))
