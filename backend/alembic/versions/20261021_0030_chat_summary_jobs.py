"""Durable chat compaction, consumed by the shared summarizer worker."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_0030'
down_revision = '20261021_0029'
branch_labels = depends_on = None


def upgrade():
    op.create_table('chat_summary_job',
        sa.Column('conversation_id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id'), nullable=False),
        sa.Column('target_sequence', sa.BigInteger(), nullable=False),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('lease_token', sa.Uuid(as_uuid=False)), sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('attempts', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Boolean(), nullable=False, server_default='false'), sa.Column('error_code', sa.Text()),
        sa.ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
        sa.CheckConstraint('target_sequence > 0 AND attempts >= 0 AND ((lease_token IS NULL) = (lease_until IS NULL))', name=op.f('ck_chat_summary_job_chat_summary_job_bounds')))
    op.create_index('idx_chat_summary_job_claim', 'chat_summary_job', ['failed', 'available_at', 'lease_until'])
    op.execute("""INSERT INTO chat_summary_job (conversation_id, learner_id, target_sequence)
        SELECT id, learner_id, message_count FROM chat_conversation WHERE deleted_at IS NULL AND message_count >= 2""")


def downgrade():
    op.drop_table('chat_summary_job')
