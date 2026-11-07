"""Typed challenge choices, source outcomes and replaceable bounded fit projections."""
from alembic import op
from sqlalchemy import text
revision='20261106_0050'
down_revision='20261106_0049'
branch_labels=depends_on=None

def upgrade():
    from app.challenge.repositories.tables import TABLES
    for table in TABLES:table.create(op.get_bind())
    op.execute("CREATE FUNCTION reject_challenge_outcome_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Challenge outcomes are immutable'; END $$")
    op.execute('CREATE TRIGGER challenge_outcome_immutable BEFORE UPDATE ON challenge_outcome FOR EACH ROW EXECUTE FUNCTION reject_challenge_outcome_update()')

def guard_downgrade(connection):
    for table in ('challenge_choice','challenge_outcome','challenge_control_operation'):
        if connection.scalar(text(f'SELECT EXISTS(SELECT 1 FROM {table})')):
            raise RuntimeError('Export challenge source records before schema rollback; keep additive tables for application rollback.')

def downgrade():
    guard_downgrade(op.get_bind())
    from app.challenge.repositories.tables import TABLES
    for table in reversed(TABLES):table.drop(op.get_bind())
    op.execute('DROP FUNCTION reject_challenge_outcome_update()')
