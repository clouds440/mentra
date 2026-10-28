"""Separate response fulfillment from graph/transport termination."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261028_0036'
down_revision = '20261028_0035'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_turn', sa.Column('response_outcome', postgresql.JSONB(none_as_null=True)))
    op.add_column('chat_turn', sa.Column('orchestration_policy', sa.Text()))
    op.add_column('chat_turn', sa.Column('recovery_state', postgresql.JSONB(none_as_null=True)))


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM chat_turn WHERE response_outcome IS NOT NULL OR recovery_state IS NOT NULL)')):
        raise RuntimeError('Preserve semantic outcome/recovery data; roll application code forward instead of deleting it.')
    op.drop_column('chat_turn', 'orchestration_policy')
    op.drop_column('chat_turn', 'recovery_state')
    op.drop_column('chat_turn', 'response_outcome')
