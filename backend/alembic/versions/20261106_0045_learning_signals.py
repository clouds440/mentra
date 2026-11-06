"""Typed, provenance-backed chat observations; distinct from scored evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB

revision='20261106_0045'
down_revision='20261106_0044'
branch_labels=depends_on=None


def upgrade():
    op.add_column('chat_evidence_job',sa.Column('disposition',sa.Text()))
    op.add_column('chat_evidence_job',sa.Column('progress',JSONB,nullable=False,server_default='{}'))
    op.create_table('learning_signal',
        sa.Column('id',UUID(as_uuid=False),primary_key=True),
        sa.Column('learner_id',UUID(as_uuid=False),sa.ForeignKey('learner.id'),nullable=False),
        sa.Column('turn_id',UUID(as_uuid=False),nullable=False),sa.Column('attempt',sa.Integer(),nullable=False),
        sa.Column('context_id',sa.Text()),sa.Column('concept_id',sa.Text(),sa.ForeignKey('concept.id')),
        *[sa.Column(name,sa.Text(),nullable=False) for name in ('kind','label','normalized_label','topic','source_id','source_kind','source_revision','quote','fingerprint')],
        sa.Column('span_start',sa.Integer(),nullable=False),sa.Column('span_end',sa.Integer(),nullable=False),
        sa.Column('confidence',sa.Float(),nullable=False),sa.Column('details',JSONB,nullable=False),
        sa.Column('status',sa.Text(),nullable=False,server_default='active'),
        sa.Column('observed_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['learner_id','turn_id'],['chat_turn.learner_id','chat_turn.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['learner_id','context_id'],['learning_context.learner_id','learning_context.id']),
        sa.UniqueConstraint('learner_id','turn_id','attempt','fingerprint',name='uq_learning_signal_source'),
        sa.CheckConstraint("kind IN ('encounter','struggle','self_report','guided_work','demonstration') AND status IN ('active','pending','withdrawn') AND source_kind IN ('user','attachment') AND confidence BETWEEN 0 AND 1 AND span_start >= 0 AND span_end > span_start AND attempt > 0",name='learning_signal_bounds'))
    op.create_index('idx_learning_signal_context','learning_signal',['learner_id','context_id','status','observed_at','id'])
    op.create_index('idx_learning_signal_recent','learning_signal',['learner_id','status','observed_at','id'])
    op.create_index('idx_learning_signal_label','learning_signal',['learner_id','normalized_label','topic','observed_at'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM learning_signal)')):
        raise RuntimeError('Preserve learning-signal source receipts before removing this phase.')
    op.drop_table('learning_signal')
    op.drop_column('chat_evidence_job','progress')
    op.drop_column('chat_evidence_job','disposition')
