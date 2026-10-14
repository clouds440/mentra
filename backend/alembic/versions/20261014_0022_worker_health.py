"""Content-free worker liveness projection for readiness diagnostics."""
from alembic import op
import sqlalchemy as sa

revision = '20261014_0022'
down_revision = '20261014_0021'
branch_labels = depends_on = None


def upgrade():
    op.create_table('worker_health', sa.Column('role', sa.Text(), primary_key=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('worker_health')
