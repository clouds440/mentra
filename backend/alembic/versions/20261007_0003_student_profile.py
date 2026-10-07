"""Separate high-level profile, controlled calibration, and broad evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '20261007_0003'
down_revision = '20261007_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('student_profile',
        sa.Column('learner_id', UUID(as_uuid=False), sa.ForeignKey('learner.id'), primary_key=True),
        sa.Column('details', JSONB), sa.Column('estimates', JSONB, nullable=False),
        sa.Column('details_source', sa.String(64)),
        sa.Column('onboarding_phase', sa.String(20), nullable=False),
        sa.Column('calibration_status', sa.String(20), nullable=False),
        sa.Column('evaluation_status', sa.String(20), nullable=False),
        sa.Column('version', sa.Integer, nullable=False), sa.Column('context_version', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('version >= 1 AND context_version >= 0', name='versions'),
        sa.CheckConstraint("onboarding_phase IN ('information','calibration','complete')", name='phase'),
        sa.CheckConstraint("calibration_status IN ('not_started','in_progress','skipped','completed')", name='calibration_status'),
        sa.CheckConstraint("evaluation_status IN ('not_started','pending','evaluating','applied','failed','superseded')", name='evaluation_status'),
        sa.CheckConstraint("(details IS NULL AND onboarding_phase='information') OR (details IS NOT NULL AND onboarding_phase<>'information')", name='required_details'),
        sa.CheckConstraint("jsonb_typeof(estimates)='object' AND (details IS NULL OR jsonb_typeof(details)='object')", name='objects'),
        sa.CheckConstraint('(details IS NULL) = (details_source IS NULL)', name='details_source'),
        sa.CheckConstraint('(details IS NULL AND context_version=0) OR (details IS NOT NULL AND context_version>=1)', name='context_scope'),
    )
    op.create_table('student_calibration_attempt',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('learner_id', UUID(as_uuid=False), sa.ForeignKey('student_profile.learner_id'), nullable=False),
        sa.Column('context_version', sa.Integer, nullable=False), sa.Column('blueprint_version', sa.String(120), nullable=False),
        sa.Column('payload', JSONB, nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('version', sa.Integer, nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('id', 'learner_id', name='uq_student_calibration_attempt_owner'),
        sa.CheckConstraint('version >= 1 AND context_version >= 1', name='versions'),
        sa.CheckConstraint("status IN ('in_progress','completed','skipped','superseded')", name='status'),
        sa.CheckConstraint("(status='in_progress') = (completed_at IS NULL)", name='completion'),
    )
    op.create_index('idx_student_calibration_learner', 'student_calibration_attempt', ['learner_id', 'created_at'])
    op.create_index('uq_student_calibration_active', 'student_calibration_attempt', ['learner_id'], unique=True,
                    postgresql_where=sa.text("status='in_progress'"))
    op.create_table('student_profile_evidence',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('learner_id', UUID(as_uuid=False), sa.ForeignKey('student_profile.learner_id'), nullable=False),
        sa.Column('calibration_attempt_id', UUID(as_uuid=False)),
        sa.Column('context_version', sa.Integer, nullable=False),
        sa.Column('source_type', sa.String(40), nullable=False), sa.Column('source_id', sa.String(160), nullable=False),
        sa.Column('payload', JSONB, nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('evaluation_token', UUID(as_uuid=False)), sa.Column('claimed_at', sa.DateTime(timezone=True)),
        sa.Column('evaluation', JSONB), sa.Column('policy_version', sa.String(80)), sa.Column('applied_estimates', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['calibration_attempt_id','learner_id'], ['student_calibration_attempt.id','student_calibration_attempt.learner_id'], name='fk_student_profile_evidence_attempt_owner'),
        sa.UniqueConstraint('learner_id','source_type','source_id', name='uq_student_profile_evidence_source'),
        sa.CheckConstraint('context_version >= 1', name='context_version'),
        sa.CheckConstraint("source_type IN ('onboarding_calibration','assessment','interaction')", name='source_type'),
        sa.CheckConstraint("status IN ('pending','evaluating','applied','failed','superseded')", name='status'),
        sa.CheckConstraint("(source_type='onboarding_calibration') = (calibration_attempt_id IS NOT NULL)", name='calibration_reference'),
        sa.CheckConstraint("status<>'evaluating' OR (evaluation_token IS NOT NULL AND claimed_at IS NOT NULL)", name='claim'),
        sa.CheckConstraint("status<>'applied' OR (evaluation IS NOT NULL AND applied_estimates IS NOT NULL AND policy_version IS NOT NULL)", name='application'),
    )
    op.create_index('idx_student_profile_evidence_learner', 'student_profile_evidence', ['learner_id','created_at'])
    op.execute("""CREATE FUNCTION protect_student_profile_evidence() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' OR TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'Student profile observations are immutable';
      END IF;
      IF OLD.status = 'applied' OR
         ROW(OLD.id,OLD.learner_id,OLD.calibration_attempt_id,OLD.context_version,OLD.source_type,OLD.source_id,OLD.payload,OLD.created_at)
         IS DISTINCT FROM
         ROW(NEW.id,NEW.learner_id,NEW.calibration_attempt_id,NEW.context_version,NEW.source_type,NEW.source_id,NEW.payload,NEW.created_at) THEN
        RAISE EXCEPTION 'Student profile observations and applied evaluations are immutable';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute('CREATE TRIGGER student_profile_evidence_immutable BEFORE UPDATE OR DELETE ON student_profile_evidence FOR EACH ROW EXECUTE FUNCTION protect_student_profile_evidence()')
    op.execute('CREATE TRIGGER student_profile_evidence_no_truncate BEFORE TRUNCATE ON student_profile_evidence FOR EACH STATEMENT EXECUTE FUNCTION protect_student_profile_evidence()')
    op.execute("""CREATE FUNCTION protect_student_calibration_attempt() RETURNS trigger AS $$
    BEGIN
      IF TG_OP='DELETE' OR TG_OP='TRUNCATE' THEN
        RAISE EXCEPTION 'Calibration history is immutable';
      END IF;
      IF OLD.status<>'in_progress' OR
         ROW(OLD.id,OLD.learner_id,OLD.context_version,OLD.blueprint_version,OLD.created_at,OLD.payload-'answers')
         IS DISTINCT FROM
         ROW(NEW.id,NEW.learner_id,NEW.context_version,NEW.blueprint_version,NEW.created_at,NEW.payload-'answers') THEN
        RAISE EXCEPTION 'Calibration snapshots and finished answers are immutable';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute('CREATE TRIGGER student_calibration_snapshot_immutable BEFORE UPDATE OR DELETE ON student_calibration_attempt FOR EACH ROW EXECUTE FUNCTION protect_student_calibration_attempt()')
    op.execute('CREATE TRIGGER student_calibration_no_truncate BEFORE TRUNCATE ON student_calibration_attempt FOR EACH STATEMENT EXECUTE FUNCTION protect_student_calibration_attempt()')


def downgrade():
    op.drop_table('student_profile_evidence')
    op.execute('DROP FUNCTION protect_student_profile_evidence()')
    op.drop_table('student_calibration_attempt')
    op.execute('DROP FUNCTION protect_student_calibration_attempt()')
    op.drop_table('student_profile')
