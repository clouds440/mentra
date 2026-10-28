"""Fence stopped assessment jobs and expire their private partial checkpoints."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261027_0033'
down_revision = '20261027_0032'
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint(op.f('ck_assessment_generation_job_assessment_generation_job_state'), 'assessment_generation_job', type_='check')
    op.create_check_constraint(op.f('ck_assessment_generation_job_assessment_generation_job_state'),
        'assessment_generation_job', "state IN ('queued','running','completed','failed','stopped')")
    op.add_column('assessment_generation_job', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('assessment_generation_job', sa.Column('resume_until', sa.DateTime(timezone=True)))
    op.add_column('assessment_generation_job', sa.Column('source_turn_id', postgresql.UUID(as_uuid=False)))
    op.create_foreign_key('fk_generation_source_turn', 'assessment_generation_job', 'chat_turn',
        ['learner_id', 'source_turn_id'], ['learner_id', 'id'], ondelete='CASCADE')
    op.create_index('idx_generation_stopped_expiry', 'assessment_generation_job', ['state', 'resume_until'])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM assessment_generation_job WHERE state='stopped')")):
        raise RuntimeError('Keep stopped-generation receipts; use the current schema when rolling back application reads.')
    op.drop_index('idx_generation_stopped_expiry', table_name='assessment_generation_job')
    op.drop_constraint('fk_generation_source_turn', 'assessment_generation_job', type_='foreignkey')
    for name in ('source_turn_id', 'resume_until', 'revision'):
        op.drop_column('assessment_generation_job', name)
    op.drop_constraint(op.f('ck_assessment_generation_job_assessment_generation_job_state'), 'assessment_generation_job', type_='check')
    op.create_check_constraint(op.f('ck_assessment_generation_job_assessment_generation_job_state'),
        'assessment_generation_job', "state IN ('queued','running','completed','failed')")
