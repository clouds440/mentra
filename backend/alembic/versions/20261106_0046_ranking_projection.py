"""Replaceable scalar ranking index; no historical backfill or dual reader."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision='20261106_0046'
down_revision='20261106_0045'
branch_labels=depends_on=None


def upgrade():
    op.create_table('learner_ranking_projection',
        sa.Column('learner_id',UUID(as_uuid=False),sa.ForeignKey('learner.id'),primary_key=True),sa.Column('concept_id',sa.Text(),primary_key=True),
        sa.Column('state_version',sa.Integer(),nullable=False),sa.Column('policy_identity',sa.Text(),nullable=False),
        sa.Column('base_half_life',sa.Float(),nullable=False),sa.Column('anchor',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('independent_items',sa.Integer(),nullable=False),sa.Column('retention_half_life',sa.Float(),nullable=False),
        sa.Column('mastery',sa.Float()),sa.Column('estimate_confidence',sa.Float()),sa.Column('retention_confidence',sa.Float()),
        sa.Column('last_demonstrated_at',sa.DateTime(timezone=True)),sa.Column('verification_required',sa.Boolean(),nullable=False),
        sa.Column('mastery_policy_version',sa.Text(),nullable=False),sa.Column('retention_policy_version',sa.Text(),nullable=False),
        *[sa.Column(f'{band}_{field}',sa.Boolean() if field=='supported' else sa.Float(),nullable=False)
          for band in ('easy','medium','hard') for field in ('amplitude','half_life','supported')],
        sa.ForeignKeyConstraint(['learner_id','concept_id'],['learner_concept_state.learner_id','learner_concept_state.concept_id'],ondelete='CASCADE'),
        sa.CheckConstraint('base_half_life > 0 AND retention_half_life > 0 AND independent_items >= 0',name='ranking_projection_bounds'))
    op.execute('''CREATE FUNCTION invalidate_learner_ranking_projection() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN DELETE FROM learner_ranking_projection WHERE learner_id=OLD.learner_id AND concept_id=OLD.concept_id;
        RETURN NEW; END $$''')
    op.execute('''CREATE TRIGGER learner_ranking_projection_source_changed AFTER UPDATE ON learner_concept_state
        FOR EACH ROW EXECUTE FUNCTION invalidate_learner_ranking_projection()''')


def downgrade():
    # This index contains no unique evidence or user decisions.
    op.execute('DROP TRIGGER learner_ranking_projection_source_changed ON learner_concept_state')
    op.execute('DROP FUNCTION invalidate_learner_ranking_projection()')
    op.drop_table('learner_ranking_projection')
