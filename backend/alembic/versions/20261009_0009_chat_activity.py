"""Durable bounded execution activity; canonical chat remains unchanged."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261009_0009'
down_revision = '20261009_0008'
branch_labels = depends_on = None


def upgrade():
    op.add_column('rag_document_version', sa.Column('extracted_content', JSONB()))
    op.create_unique_constraint('uq_chat_turn_learner_id', 'chat_turn', ['learner_id', 'id'])
    op.add_column('chat_turn', sa.Column('attachment_ids', JSONB(), nullable=False, server_default='[]'))
    op.create_table('chat_activity',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('turn_id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.ForeignKeyConstraint(['learner_id', 'turn_id'], ['chat_turn.learner_id', 'chat_turn.id'], ondelete='CASCADE'),
        sa.Column('attempt', sa.Integer(), primary_key=True),
        sa.Column('sequence', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', JSONB(), nullable=False),
        sa.CheckConstraint('attempt > 0 AND sequence > 0 AND sequence <= 256', name='chat_activity_sequence'))
    op.create_index('idx_chat_activity_retention', 'chat_activity', ['learner_id', 'created_at'])
    op.create_table('chat_attachment',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id'), nullable=False),
        sa.Column('conversation_id', sa.Uuid(as_uuid=False)), sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False), sa.Column('extraction', JSONB()),
        sa.Column('library_result', JSONB()), sa.Column('extraction_error', sa.Text()),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
        sa.CheckConstraint('size_bytes > 0 AND size_bytes <= 26214400', name='chat_attachment_size'))
    op.create_index('idx_chat_attachment_owner', 'chat_attachment', ['learner_id', 'conversation_id'])


def downgrade():
    op.drop_column('rag_document_version', 'extracted_content')
    op.drop_table('chat_attachment')
    op.drop_table('chat_activity')
    op.drop_column('chat_turn', 'attachment_ids')
    op.drop_constraint('uq_chat_turn_learner_id', 'chat_turn', type_='unique')
