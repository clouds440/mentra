"""Retain repeat-practice identity and exposure independently of source deletion."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261017_0026'
down_revision = '20261015_0025'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('assessment', sa.Column('practice_lineage', postgresql.JSONB(none_as_null=True), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text("""SELECT
        EXISTS (SELECT 1 FROM assessment WHERE practice_lineage IS NOT NULL AND practice_lineage <> 'null'::jsonb)
        OR EXISTS (SELECT 1 FROM chat_assessment_draft WHERE payload->'practice_lineage' IS NOT NULL
            AND payload->'practice_lineage' <> 'null'::jsonb)""")):
        raise RuntimeError('Cannot remove exposure lineage while mistake-practice assessments exist. Preserve these records before rollback.')
    op.drop_column('assessment', 'practice_lineage')
