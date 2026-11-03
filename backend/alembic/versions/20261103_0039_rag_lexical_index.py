"""Repair the unattached RAG expression index without changing canonical data."""
from alembic import op
from sqlalchemy import text

revision='20261103_0039'
down_revision='20261029_0038'
branch_labels=None
depends_on=None


def upgrade():
    with op.get_context().autocommit_block():
        row=op.get_bind().execute(text("""SELECT i.indisvalid,pg_get_expr(i.indexprs,i.indrelid) AS expression,am.amname
            FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_am am ON am.oid=c.relam
            WHERE c.relname='idx_rag_chunk_lexical' AND n.nspname=current_schema()""")).mappings().first()
        if row and not row['indisvalid']:
            op.execute('DROP INDEX CONCURRENTLY idx_rag_chunk_lexical')
        elif row and (row['amname']!='gin' or row['expression']!="to_tsvector('simple'::regconfig, content)"):
            raise RuntimeError('Existing idx_rag_chunk_lexical has an incompatible definition; inspect it before migrating.')
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunk_lexical ON rag_chunk USING gin (to_tsvector('simple'::regconfig,content))")


def downgrade():
    with op.get_context().autocommit_block():
        op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_rag_chunk_lexical')
