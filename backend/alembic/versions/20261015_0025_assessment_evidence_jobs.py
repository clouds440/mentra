"""Publish grades before applying durable background learning updates."""
from alembic import op
import sqlalchemy as sa

revision = '20261015_0025'
down_revision = '20261014_0024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('assessment_evidence_job',
        sa.Column('attempt_id', sa.Uuid(as_uuid=False), sa.ForeignKey('assessment_attempt.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('grade_revision', sa.Integer(), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), nullable=False),
        sa.Column('state', sa.Text(), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('retry_at', sa.DateTime(timezone=True)),
        sa.Column('claim_id', sa.Uuid(as_uuid=False)), sa.Column('claim_until', sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('queued','running','applied','skipped','failed') AND attempts BETWEEN 0 AND 3 AND grade_revision >= 1", name='assessment_evidence_job_state'))
    op.create_index('idx_assessment_evidence_queue', 'assessment_evidence_job', ['state', 'retry_at', 'claim_until'])


def downgrade():
    op.drop_table('assessment_evidence_job')
