"""Defer capacity-blocked reminders without changing their original due time."""
from alembic import op
import sqlalchemy as sa

revision = '20261014_0020'
down_revision = '20261014_0019'
branch_labels = depends_on = None


def upgrade():
    op.add_column('hm_event_reminder', sa.Column('retry_at', sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column('hm_event_reminder', 'retry_at')
