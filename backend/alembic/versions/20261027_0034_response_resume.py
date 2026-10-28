"""Temporary, owner-bound response continuation and checkpoint expiry."""
from alembic import op
import sqlalchemy as sa

revision = '20261027_0034'
down_revision = '20261027_0033'
branch_labels = depends_on = None


def upgrade():
    op.add_column('chat_turn', sa.Column('resume_until', sa.DateTime(timezone=True)))
    op.add_column('chat_turn', sa.Column('resume_instruction', sa.Text()))
    op.add_column('chat_turn', sa.Column('resume_operation_id', sa.Uuid(as_uuid=False)))
    op.add_column('chat_turn', sa.Column('resume_request_hash', sa.Text()))
    op.create_index('idx_chat_resume_expiry', 'chat_turn', ['resume_until'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM chat_turn WHERE resume_until IS NOT NULL OR resume_operation_id IS NOT NULL)')):
        raise RuntimeError('Keep response continuation receipts; roll back application reads without dropping this schema.')
    op.drop_index('idx_chat_resume_expiry', table_name='chat_turn')
    op.drop_column('chat_turn', 'resume_instruction')
    op.drop_column('chat_turn', 'resume_operation_id')
    op.drop_column('chat_turn', 'resume_request_hash')
    op.drop_column('chat_turn', 'resume_until')
