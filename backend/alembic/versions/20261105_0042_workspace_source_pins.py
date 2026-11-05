"""Durable learner-owned source pins."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261105_0042'
down_revision = '20261103_0041'
branch_labels = depends_on = None


def upgrade():
    op.create_table('workspace_source_pin',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('resource_key', sa.Text(), nullable=False),
        sa.Column('source', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('learner_id', 'resource_key', name='workspace_source_pin_resource'))


def downgrade():
    op.drop_table('workspace_source_pin')
