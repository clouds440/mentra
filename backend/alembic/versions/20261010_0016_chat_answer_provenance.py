"""Fence chat answer retries and retain multi-message answer provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261010_0016'
down_revision = '20261010_0015'
branch_labels = depends_on = None


def upgrade():
    op.add_column('assessment_attempt', sa.Column('start_fingerprint', sa.Text()))
    op.add_column('assessment_attempt', sa.Column('chat_inputs', JSONB, nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('assessment_attempt', 'chat_inputs')
    op.drop_column('assessment_attempt', 'start_fingerprint')
