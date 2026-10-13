"""Private summaries are tied to their owning chat; original messages stay intact."""
from alembic import op
import sqlalchemy as sa

revision = '20261013_0018'
down_revision = '20261011_0017'
branch_labels = depends_on = None


def upgrade():
    op.create_table('chat_summary',
        sa.Column('conversation_id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('through_sequence', sa.BigInteger(), nullable=False),
        sa.Column('revision', sa.BigInteger(), nullable=False),
        sa.Column('lease_token', sa.Uuid(as_uuid=False)),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['learner_id', 'conversation_id'], ['chat_conversation.learner_id', 'chat_conversation.id'], ondelete='CASCADE'),
        sa.CheckConstraint('through_sequence >= 0 AND revision >= 0', name='chat_summary_revision'))


def downgrade():
    op.drop_table('chat_summary')
