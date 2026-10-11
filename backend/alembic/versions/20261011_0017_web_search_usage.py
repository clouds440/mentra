"""Add shared free-search admission; no queries or source data stored here."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261011_0017'
down_revision = '20261010_0016'
branch_labels = depends_on = None


def upgrade():
    op.create_table('web_search_guard', sa.Column('provider', sa.Text(), primary_key=True))
    op.create_table('web_search_call',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('provider', sa.Text(), sa.ForeignKey('web_search_guard.provider'), nullable=False),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='SET NULL')),
        sa.Column('reserved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state', sa.Text(), nullable=False),
        sa.CheckConstraint("state IN ('reserved', 'sent', 'completed', 'unknown', 'released')", name='state'))
    op.create_index('idx_web_search_window', 'web_search_call', ['provider', 'reserved_at'])
    op.create_index('idx_web_search_owner_window', 'web_search_call', ['learner_id', 'reserved_at'])
    op.create_table('web_search_cache',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cached_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', JSONB, nullable=False),
        sa.CheckConstraint('octet_length(payload::text) <= 32768', name='payload_size'))
    op.create_index('idx_web_search_cache_expiry', 'web_search_cache', ['expires_at'])


def downgrade():
    op.drop_table('web_search_cache')
    op.drop_table('web_search_call')
    op.drop_table('web_search_guard')
