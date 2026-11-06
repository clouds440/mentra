"""Retain the student's report explanation for private review."""
from alembic import op
import sqlalchemy as sa

revision = '20261106_0049'
down_revision = '20261106_0048'
branch_labels = depends_on = None


def upgrade():
    op.add_column('assessment_item_review', sa.Column('details', sa.Text(), nullable=False, server_default=''))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM assessment_item_review WHERE details <> '')")):
        raise RuntimeError('Export report explanations before schema rollback; retain the additive column for application rollback.')
    op.drop_column('assessment_item_review', 'details')
