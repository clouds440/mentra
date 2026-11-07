from sqlalchemy import Table, Column, Text, Integer, Boolean, DateTime, Uuid, ForeignKey, Index, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata

def owner():
    return Column('learner_id',Uuid(as_uuid=False),ForeignKey('learner.id',ondelete='CASCADE'),primary_key=True)

choices=Table('challenge_choice',metadata,owner(),Column('id',Uuid(as_uuid=False),primary_key=True),
    Column('context_id',Text,nullable=False),Column('family',Text,nullable=False),
    Column('direction',Text,nullable=False),Column('source_kind',Text,nullable=False),
    Column('source_id',Uuid(as_uuid=False),nullable=False),Column('source_revision',Integer,nullable=False),
    Column('job_id',Uuid(as_uuid=False),nullable=False),Column('conversation_id',Uuid(as_uuid=False),nullable=False),
    Column('created_at',DateTime(timezone=True),nullable=False),Column('served_at',DateTime(timezone=True)),
    Column('assessment_id',Uuid(as_uuid=False)),Column('payload',JSONB,nullable=False),
    CheckConstraint("direction IN ('easier','harder') AND source_kind IN ('draft','assessment') AND source_revision>0",name='challenge_choice_bounds'),
    Index('idx_challenge_choice_owner','learner_id','created_at'),
    Index('idx_challenge_choice_source','learner_id','source_id'),
    Index('idx_challenge_choice_served','learner_id','assessment_id'))

outcomes=Table('challenge_outcome',metadata,owner(),Column('attempt_id',Uuid(as_uuid=False),primary_key=True),
    Column('grade_revision',Integer,primary_key=True),Column('scope_key',Text,primary_key=True),
    Column('assessment_id',Uuid(as_uuid=False),nullable=False),Column('choice_id',Uuid(as_uuid=False),nullable=False),
    Column('family',Text,nullable=False),Column('occurred_at',DateTime(timezone=True),nullable=False),
    Column('payload',JSONB,nullable=False),
    Index('idx_challenge_outcome_source','learner_id','assessment_id'))

families=Table('challenge_family',metadata,owner(),Column('scope_key',Text,primary_key=True),
    Column('family',Text,primary_key=True),Column('assessment_id',Uuid(as_uuid=False),nullable=False),
    Column('attempt_id',Uuid(as_uuid=False),nullable=False),Column('grade_revision',Integer,nullable=False),
    Column('occurred_at',DateTime(timezone=True),nullable=False),Column('valid',Boolean,nullable=False),
    Column('payload',JSONB,nullable=False),
    Index('idx_challenge_family_window','learner_id','scope_key','valid','occurred_at','family'),
    Index('idx_challenge_family_source','learner_id','assessment_id'))

states=Table('challenge_state',metadata,owner(),Column('scope_key',Text,primary_key=True),
    Column('context_id',Text,nullable=False),Column('concept_id',Text,nullable=False),
    Column('language',Text,nullable=False),Column('answer_mode',Text,nullable=False),
    Column('updated_at',DateTime(timezone=True),nullable=False),Column('expires_at',DateTime(timezone=True),nullable=False),
    Column('policy',Text,nullable=False),Column('payload',JSONB,nullable=False),
    CheckConstraint("language IN ('en','ar','und') AND answer_mode IN ('text','single_choice','multiple_choice')",name='challenge_state_scope'),
    Index('idx_challenge_state_skill','learner_id','concept_id','context_id'),
    Index('idx_challenge_state_page','learner_id','scope_key'))

controls=Table('challenge_control',metadata,owner(),Column('context_id',Text,primary_key=True),
    Column('concept_id',Text,primary_key=True),Column('enabled',Boolean,nullable=False),
    Column('reset_at',DateTime(timezone=True),nullable=False),Column('revision',Integer,nullable=False),
    CheckConstraint('revision>0',name='challenge_control_revision'))
control_operations=Table('challenge_control_operation',metadata,owner(),Column('id',Uuid(as_uuid=False),primary_key=True),
    Column('fingerprint',Text,nullable=False),Column('result',JSONB,nullable=False))
jobs=Table('challenge_job',metadata,owner(),Column('id',Uuid(as_uuid=False),primary_key=True),
    Column('kind',Text,nullable=False),Column('subject',Text,nullable=False),Column('payload',JSONB,nullable=False),
    Column('state',Text,nullable=False),Column('attempts',Integer,nullable=False),
    Column('created_at',DateTime(timezone=True),nullable=False),Column('claim_id',Uuid(as_uuid=False)),
    Column('claim_until',DateTime(timezone=True)),Column('retry_at',DateTime(timezone=True)),
    UniqueConstraint('learner_id','kind','subject'),
    CheckConstraint("state IN ('queued','running','applied','failed') AND attempts BETWEEN 0 AND 3",name='challenge_job_state'),
    Index('idx_challenge_job_ready','state','retry_at','created_at'))
TABLES=(choices,outcomes,families,states,controls,control_operations,jobs)
