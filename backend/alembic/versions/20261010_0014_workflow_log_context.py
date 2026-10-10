"""Add optional internal workflow correlation without changing domain identities."""
from alembic import op
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261010_0014'
down_revision = '20261009_0013'
branch_labels = depends_on = None
TABLES = ('rag_job', 'chat_turn', 'assessment_attempt', 'chat_evidence_job')


def upgrade():
    for table in TABLES:
        op.add_column(table, Column('log_context', JSONB, nullable=True))


def downgrade():
    for table in reversed(TABLES):
        op.drop_column(table, 'log_context')
