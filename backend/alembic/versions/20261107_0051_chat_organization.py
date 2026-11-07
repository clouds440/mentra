"""Chat pins, archive metadata and durable owner-scoped management jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261107_0051'
down_revision = '20261106_0050'
branch_labels = depends_on = None


def upgrade():
    for name in ('archived_at', 'pinned_at'):
        op.add_column('chat_conversation', sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column('chat_conversation', sa.Column('pending_action', sa.Text()))
    op.add_column('chat_conversation', sa.Column('pending_action_id', sa.Uuid(as_uuid=False)))
    op.create_check_constraint('chat_organization_state', 'chat_conversation', "(pending_action IS NULL) = (pending_action_id IS NULL) AND (pending_action IS NULL OR pending_action IN ('archive','unarchive','delete')) AND (archived_at IS NULL OR pinned_at IS NULL)")
    op.create_index('idx_chat_archive', 'chat_conversation', ['learner_id', 'archived_at', 'id'], postgresql_where=sa.text('deleted_at IS NULL AND archived_at IS NOT NULL'))
    op.create_index('idx_chat_pinned', 'chat_conversation', ['learner_id', 'pinned_at', 'id'], postgresql_where=sa.text('deleted_at IS NULL AND pinned_at IS NOT NULL'))
    op.create_table('chat_management_job',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id'), nullable=False),
        sa.Column('action', sa.Text(), nullable=False), sa.Column('request_hash', sa.Text(), nullable=False),
        sa.Column('items', JSONB(), nullable=False),
        sa.Column('completed_ids', JSONB(), nullable=False, server_default='[]'),
        sa.Column('failed_items', JSONB(), nullable=False, server_default='[]'),
        sa.Column('state', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("action IN ('archive','unarchive','delete') AND state IN ('queued','running','completed')", name='chat_management_state'),
        sa.CheckConstraint('jsonb_array_length(items) BETWEEN 1 AND 100', name='chat_management_size'))
    op.create_index('idx_chat_management_claim', 'chat_management_job', ['state', 'created_at'])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM chat_conversation WHERE archived_at IS NOT NULL OR pinned_at IS NOT NULL OR pending_action IS NOT NULL) OR EXISTS(SELECT 1 FROM chat_management_job)")):
        raise RuntimeError('Preserve chat organization and management receipts before rollback; use an application rollback with the additive schema retained.')
    op.drop_table('chat_management_job')
    op.drop_index('idx_chat_pinned', table_name='chat_conversation')
    op.drop_index('idx_chat_archive', table_name='chat_conversation')
    op.drop_constraint('chat_organization_state', 'chat_conversation', type_='check')
    for name in ('pending_action_id', 'pending_action', 'pinned_at', 'archived_at'):
        op.drop_column('chat_conversation', name)
