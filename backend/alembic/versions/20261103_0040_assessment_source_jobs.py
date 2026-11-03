"""Durable source extraction; canonical attempts and original bytes stay intact."""
from alembic import op
import sqlalchemy as sa

revision = '20261103_0040'
down_revision = '20261103_0039'
branch_labels = depends_on = None


def upgrade():
    op.add_column('file_speech_operation',sa.Column('request_hash',sa.Text()))
    op.create_table('assessment_source_job',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('attempt_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('file_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('expected_revision', sa.Integer(), nullable=False),
        sa.Column('from_chat', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_retries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retry_at', sa.DateTime(timezone=True)),
        sa.Column('claim_id', sa.Uuid(as_uuid=False)),
        sa.Column('claim_until', sa.DateTime(timezone=True)), sa.Column('error', sa.Text()),
        sa.UniqueConstraint('learner_id','attempt_id','file_id','expected_revision', name='uq_source_job_operation'),
        sa.ForeignKeyConstraint(['learner_id','attempt_id'], ['assessment_attempt.learner_id','assessment_attempt.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['learner_id','file_id'], ['file_asset.learner_id','file_asset.id']),
        sa.CheckConstraint("state IN ('queued','running','completed','failed') AND attempts BETWEEN 0 AND 3 AND manual_retries BETWEEN 0 AND 3 AND expected_revision >= 1", name='source_job_state'))
    op.create_index('idx_assessment_source_queue','assessment_source_job',['state','retry_at','claim_until'])


def downgrade():
    # Pending source requests are user work. Require an explicit drain first.
    if op.get_bind().execute(sa.text("SELECT 1 FROM assessment_source_job WHERE state IN ('queued','running') LIMIT 1")).first():
        raise RuntimeError('Drain assessment source jobs before downgrading')
    op.drop_table('assessment_source_job')
    op.drop_column('file_speech_operation','request_hash')
