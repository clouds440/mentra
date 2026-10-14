"""Explicit same-attempt grading recovery; original submission stays immutable."""
from alembic import op
import sqlalchemy as sa

revision = '20261014_0021'
down_revision = '20261014_0020'
branch_labels = depends_on = None


def upgrade():
    op.add_column('assessment_attempt', sa.Column('retry_request_id', sa.Uuid(as_uuid=False)))
    op.add_column('assessment_attempt', sa.Column('manual_retries', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('assessment_attempt', 'manual_retries')
    op.drop_column('assessment_attempt', 'retry_request_id')
