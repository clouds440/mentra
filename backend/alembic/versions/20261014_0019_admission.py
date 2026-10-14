"""Durable bounded admission for authentication and expensive workflows."""
from alembic import op
import sqlalchemy as sa

revision = '20261014_0019'
down_revision = '20261013_0018'
branch_labels = depends_on = None


def upgrade():
    op.create_table('work_admission',
        sa.Column('id', sa.Text(), primary_key=True), sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('owner', sa.Text(), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('request_rate',
        sa.Column('kind', sa.Text(), primary_key=True), sa.Column('bucket', sa.Integer(), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False), sa.Column('count', sa.Integer(), nullable=False))


def downgrade():
    op.drop_table('request_rate')
    op.drop_table('work_admission')
