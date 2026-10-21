"""Durable owner-scoped incremental memory summaries; preserve canonical facts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261021_0029'
down_revision = '20261020_0028'
branch_labels = None
depends_on = None


def upgrade():
    # Freeze the migration schema; future application table changes must not
    # change what this historical revision creates on a fresh installation.
    op.create_table('hm_memory_summary_state',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source_revision', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('published_source_revision', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('summary_revision', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('blocks', JSONB(), nullable=False, server_default='[]'),
        sa.Column('prompt_version', sa.Text(), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('reconciled_at', sa.DateTime(timezone=True)),
        sa.Column('reconciled_revision', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('next_expiry_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('source_revision >= published_source_revision AND published_source_revision >= 0 AND summary_revision >= 0', name=op.f('ck_hm_memory_summary_state_memory_summary_revisions')),
        sa.CheckConstraint("jsonb_typeof(blocks) = 'array' AND octet_length(blocks::text) <= 32768", name=op.f('ck_hm_memory_summary_state_memory_summary_blocks')))
    op.create_index('idx_memory_summary_expiry', 'hm_memory_summary_state', ['next_expiry_at'])
    op.create_table('hm_memory_summary_change',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('hm_memory_summary_state.learner_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source_revision', sa.BigInteger(), primary_key=True),
        sa.Column('memory_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('after', JSONB()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('source_revision > 0', name=op.f('ck_hm_memory_summary_change_memory_summary_change_revision')))
    op.create_table('hm_memory_summary_job',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('hm_memory_summary_state.learner_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('lease_token', sa.Uuid(as_uuid=False)), sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('attempts', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Boolean(), nullable=False, server_default='false'), sa.Column('error_code', sa.Text()),
        sa.Column('rebuild', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('checkpoint', JSONB(), nullable=False, server_default='{}'),
        sa.CheckConstraint('attempts >= 0 AND ((lease_token IS NULL) = (lease_until IS NULL))', name=op.f('ck_hm_memory_summary_job_memory_summary_lease')),
        sa.CheckConstraint('octet_length(checkpoint::text) <= 32768', name=op.f('ck_hm_memory_summary_job_memory_summary_checkpoint')))
    op.create_index('idx_memory_summary_claim', 'hm_memory_summary_job', ['failed', 'available_at', 'lease_until'])
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO hm_memory_summary_state (learner_id, source_revision, next_expiry_at)
        SELECT learner_id, 1, min(expires_at) FROM hm_memory
        WHERE status = 'active' AND (expires_at IS NULL OR expires_at > now()) GROUP BY learner_id
    """))
    connection.execute(sa.text("""
        INSERT INTO hm_memory_summary_job (learner_id, rebuild)
        SELECT learner_id, true FROM hm_memory_summary_state
    """))


def downgrade():
    for table in ('hm_memory_summary_job', 'hm_memory_summary_change', 'hm_memory_summary_state'):
        op.drop_table(table)
