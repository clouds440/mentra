"""Private pre-outcome assessment predictions, no historical backfill."""
from alembic import op

revision='20261106_0048'
down_revision='20261106_0047'
branch_labels=depends_on=None

def upgrade():
    from app.assessments.repositories.tables import prediction_snapshots
    prediction_snapshots.create(op.get_bind())
    op.execute("CREATE FUNCTION reject_prediction_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Prediction snapshots are immutable'; END $$")
    op.execute('CREATE TRIGGER prediction_immutable BEFORE UPDATE ON assessment_prediction_snapshot FOR EACH ROW EXECUTE FUNCTION reject_prediction_update()')

def guard_downgrade(connection):
    from sqlalchemy import text
    if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM assessment_prediction_snapshot)')):
        raise RuntimeError('Export pre-outcome snapshots before schema rollback; retain the additive table for application rollback.')

def downgrade():
    guard_downgrade(op.get_bind())
    op.drop_table('assessment_prediction_snapshot')
    op.execute('DROP FUNCTION reject_prediction_update()')
