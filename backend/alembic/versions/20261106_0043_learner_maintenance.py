"""Durable background organization and policy replay; no learner evidence rewrite."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '20261106_0043'
down_revision = '20261105_0042'
branch_labels = depends_on = None


def upgrade():
    op.create_table('learner_maintenance_job',
        sa.Column('learner_id', UUID(as_uuid=False), sa.ForeignKey('learner.id'), primary_key=True),
        sa.Column('context_id', sa.Text(), primary_key=True),
        sa.Column('kind', sa.Text(), primary_key=True), sa.Column('state', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('claim_id', sa.Text()), sa.Column('claim_until', sa.DateTime(timezone=True)),
        sa.Column('retry_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('organization','policy_replay') AND state IN ('queued','running','completed','failed') AND attempts BETWEEN 0 AND 3", name='learner_maintenance_state'),
        sa.ForeignKeyConstraint(['learner_id','context_id'], ['learning_context.learner_id','learning_context.id'], ondelete='CASCADE'))
    op.create_index('idx_learner_maintenance_queue', 'learner_maintenance_job', ['state','retry_at','claim_until','created_at'])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM learner_maintenance_job WHERE state IN ('queued','running'))")):
        raise RuntimeError('Drain or export pending learner maintenance before schema rollback; prior code can run with this additive table.')
    op.drop_table('learner_maintenance_job')
