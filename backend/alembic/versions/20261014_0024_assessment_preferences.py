"""Persist level and result display choices for all assessment formats."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261014_0024'
down_revision = '20261014_0023'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('assessment', sa.Column('preferences', postgresql.JSONB(), nullable=False, server_default='{}'))

def downgrade():
    op.drop_column('assessment', 'preferences')
