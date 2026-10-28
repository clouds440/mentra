"""Durable, quiet capture of explicitly stated personal context."""
from alembic import op
import sqlalchemy as sa

revision = '20261028_0035'
down_revision = '20261027_0034'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('hm_memory_capture_job',
        sa.Column('message_id', sa.Uuid(as_uuid=False), sa.ForeignKey('chat_message.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id'), nullable=False),
        sa.Column('conversation_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('turn_id', sa.Uuid(as_uuid=False), sa.ForeignKey('chat_turn.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_attempt', sa.BigInteger(), nullable=False), sa.Column('preference_revision', sa.BigInteger(), nullable=False),
        sa.Column('content_offset', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('lease_token', sa.Uuid(as_uuid=False)), sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('attempts', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Boolean(), nullable=False, server_default='false'), sa.Column('error_code', sa.Text()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
        sa.CheckConstraint('content_offset >= 0 AND attempts >= 0 AND source_attempt >= 1 AND preference_revision >= 1', name='memory_capture_bounds'),
        sa.CheckConstraint('(lease_token IS NULL) = (lease_until IS NULL)', name='memory_capture_lease'))
    op.create_index('idx_memory_capture_claim', 'hm_memory_capture_job', ['completed_at', 'failed', 'available_at', 'lease_until'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM hm_memory_capture_job)')):
        raise RuntimeError('Preserve memory capture receipts; roll back application code without dropping this table.')
    op.drop_table('hm_memory_capture_job')
