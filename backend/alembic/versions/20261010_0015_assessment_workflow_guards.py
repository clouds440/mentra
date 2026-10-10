"""Additive generation fencing and explicit assistance provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261010_0015'
down_revision = '20261010_0014'
branch_labels = depends_on = None


def upgrade():
    op.add_column('assessment_attempt', sa.Column('profile_context_version', sa.BigInteger()))
    op.add_column('chat_evidence_job', sa.Column('profile_context_version', sa.BigInteger()))
    op.create_table('chat_assessment_draft',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('conversation_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('operation_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('assessment_id', sa.Uuid(as_uuid=False)),
        sa.Column('payload', JSONB, nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['learner_id','conversation_id'], ['chat_conversation.learner_id','chat_conversation.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('learner_id','operation_id'))
    op.create_index('idx_chat_assessment_recent','chat_assessment_draft',['learner_id','conversation_id','created_at'])
    op.create_table('assessment_preferences',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('auto_add', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('revision', sa.BigInteger, nullable=False),
        sa.CheckConstraint('revision >= 1', name='assessment_preferences_revision'))
    op.drop_constraint(op.f('ck_assessment_attempt_assessment_evidence_state'), 'assessment_attempt', type_='check')
    op.create_check_constraint('assessment_evidence_state', 'assessment_attempt', "evidence_status IN ('pending','applied','partial','unavailable','none')")
    op.add_column('assessment_attempt', sa.Column('assistance', sa.Text(), nullable=False, server_default='unknown'))
    op.create_check_constraint('assessment_assistance', 'assessment_attempt', "assistance IN ('unknown','independent','assisted')")
    op.create_table('assessment_generation_claim',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('operation_id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('claim_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('claim_until', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_column('chat_evidence_job','profile_context_version')
    op.drop_column('assessment_attempt','profile_context_version')
    op.drop_table('assessment_preferences')
    op.drop_table('chat_assessment_draft')
    op.drop_table('assessment_generation_claim')
    op.drop_constraint('assessment_assistance', 'assessment_attempt', type_='check')
    op.drop_column('assessment_attempt', 'assistance')
    op.execute("UPDATE assessment_attempt SET evidence_status='applied' WHERE evidence_status='partial'")
    op.drop_constraint(op.f('ck_assessment_attempt_assessment_evidence_state'), 'assessment_attempt', type_='check')
    op.create_check_constraint('assessment_evidence_state', 'assessment_attempt', "evidence_status IN ('pending','applied','unavailable','none')")
