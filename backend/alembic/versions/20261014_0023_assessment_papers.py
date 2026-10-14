"""Preserve structured mock-paper metadata without changing existing assessments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261014_0023'
down_revision = '20261014_0022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('assessment', sa.Column('paper', postgresql.JSONB(), nullable=True))
    op.add_column('assessment_attempt', sa.Column('grading_progress', postgresql.JSONB(), nullable=False, server_default='{}'))
    op.create_table('assessment_generation_job',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), nullable=False),
        sa.Column('operation_id', sa.Uuid(as_uuid=False), nullable=False), sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(as_uuid=False)), sa.Column('request', postgresql.JSONB(), nullable=False),
        sa.Column('state', sa.Text(), nullable=False), sa.Column('progress', postgresql.JSONB(), nullable=False),
        sa.Column('result', postgresql.JSONB()), sa.Column('error', sa.Text()),
        sa.Column('attempts', sa.Integer(), nullable=False), sa.Column('claim_id', sa.Uuid(as_uuid=False)),
        sa.Column('claim_until', sa.DateTime(timezone=True)), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('learner_id', 'operation_id'),
        sa.ForeignKeyConstraint(['learner_id','conversation_id'], ['chat_conversation.learner_id','chat_conversation.id'], ondelete='CASCADE'),
        sa.CheckConstraint("state IN ('queued','running','completed','failed')", name='assessment_generation_job_state'))
    op.create_index('idx_assessment_generation_queue', 'assessment_generation_job', ['state','created_at'])


def downgrade():
    op.drop_table('assessment_generation_job')
    op.drop_column('assessment_attempt', 'grading_progress')
    op.drop_column('assessment', 'paper')
