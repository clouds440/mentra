"""Typed assistance disclosure and auditable final-score adjustments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261025_0031'
down_revision = '20261021_0030'
branch_labels = depends_on = None


def upgrade():
    op.execute("CREATE TYPE assessment_assistance_kind AS ENUM ('unknown','independent','assisted')")
    op.execute('DROP TRIGGER assessment_exposure_assistance ON assessment_attempt')
    op.drop_constraint(op.f('ck_assessment_attempt_assessment_assistance'), 'assessment_attempt', type_='check')
    op.execute("ALTER TABLE assessment_attempt ALTER COLUMN assistance DROP DEFAULT")
    op.execute("ALTER TABLE assessment_attempt ALTER COLUMN assistance TYPE assessment_assistance_kind USING assistance::assessment_assistance_kind")
    op.execute("ALTER TABLE assessment_attempt ALTER COLUMN assistance SET DEFAULT 'unknown'::assessment_assistance_kind")
    op.create_check_constraint(op.f('ck_assessment_attempt_assessment_assistance'), 'assessment_attempt', "assistance IN ('unknown','independent','assisted')")
    op.execute("""CREATE TRIGGER assessment_exposure_assistance
        BEFORE INSERT OR UPDATE OF assistance,assessment_id,learner_id ON assessment_attempt FOR EACH ROW
        EXECUTE FUNCTION qualify_exposed_assessment_attempt()""")
    kind = postgresql.ENUM('unknown', 'independent', 'assisted', name='assessment_assistance_kind', create_type=False)
    op.add_column('assessment_attempt', sa.Column('reported_assistance', kind, nullable=False, server_default='unknown'))
    op.add_column('assessment_attempt', sa.Column('scoring', postgresql.JSONB(), nullable=True))
    # Exposure was historically forced to "assisted" for revision practice.
    # Only non-exposed history has an unambiguous original self-report.
    op.execute("""UPDATE assessment_attempt AS attempt SET reported_assistance=attempt.assistance
        FROM assessment AS paper WHERE paper.id=attempt.assessment_id AND paper.learner_id=attempt.learner_id
        AND coalesce(paper.practice_lineage->>'known_exposure','false') <> 'true'""")
    # Existing grades and totals are deliberately unchanged (scoring stays NULL).


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM assessment_attempt WHERE scoring IS NOT NULL)")):
        raise RuntimeError('Cannot discard saved assessment score-adjustment provenance.')
    op.drop_column('assessment_attempt', 'scoring')
    op.drop_column('assessment_attempt', 'reported_assistance')
    op.execute('DROP TRIGGER assessment_exposure_assistance ON assessment_attempt')
    op.drop_constraint(op.f('ck_assessment_attempt_assessment_assistance'), 'assessment_attempt', type_='check')
    op.execute('ALTER TABLE assessment_attempt ALTER COLUMN assistance DROP DEFAULT')
    op.execute('ALTER TABLE assessment_attempt ALTER COLUMN assistance TYPE text USING assistance::text')
    op.execute("ALTER TABLE assessment_attempt ALTER COLUMN assistance SET DEFAULT 'unknown'")
    op.create_check_constraint(op.f('ck_assessment_attempt_assessment_assistance'), 'assessment_attempt', "assistance IN ('unknown','independent','assisted')")
    op.execute("""CREATE TRIGGER assessment_exposure_assistance
        BEFORE INSERT OR UPDATE OF assistance,assessment_id,learner_id ON assessment_attempt FOR EACH ROW
        EXECUTE FUNCTION qualify_exposed_assessment_attempt()""")
    op.execute('DROP TYPE assessment_assistance_kind')
