"""Fence exposed work for older workers and retain deleted operation outcomes."""
from alembic import op
import sqlalchemy as sa

revision = '20261017_0027'
down_revision = '20261017_0026'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('assessment_practice_operation',
        sa.Column('learner_id', sa.Uuid(as_uuid=False), sa.ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('operation_id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('assessment_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.execute("""INSERT INTO assessment_practice_operation
        SELECT learner_id, operation_id, id, fingerprint, created_at FROM assessment
        WHERE practice_lineage IS NOT NULL AND practice_lineage <> 'null'::jsonb""")
    op.execute("""CREATE FUNCTION qualify_exposed_assessment_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM assessment WHERE id=NEW.assessment_id AND learner_id=NEW.learner_id
                AND practice_lineage->>'known_exposure'='true') THEN
                NEW.assistance := 'assisted';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER assessment_exposure_assistance
        BEFORE INSERT OR UPDATE OF assistance,assessment_id,learner_id ON assessment_attempt FOR EACH ROW
        EXECUTE FUNCTION qualify_exposed_assessment_attempt()""")
    op.execute("""UPDATE assessment_attempt AS attempt SET assistance='assisted' FROM assessment AS paper
        WHERE paper.id=attempt.assessment_id AND paper.learner_id=attempt.learner_id
        AND paper.practice_lineage->>'known_exposure'='true' AND attempt.state<>'graded'
        AND attempt.assistance<>'assisted'""")


def downgrade():
    if op.get_bind().scalar(sa.text("""SELECT EXISTS (SELECT 1 FROM assessment_practice_operation)
        OR EXISTS (SELECT 1 FROM chat_assessment_draft WHERE payload->'practice_lineage'->>'known_exposure'='true')""")):
        raise RuntimeError('Cannot remove exposure lineage or operation outcomes while saved practice history exists.')
    op.execute('DROP TRIGGER assessment_exposure_assistance ON assessment_attempt')
    op.execute('DROP FUNCTION qualify_exposed_assessment_attempt()')
    op.drop_table('assessment_practice_operation')
