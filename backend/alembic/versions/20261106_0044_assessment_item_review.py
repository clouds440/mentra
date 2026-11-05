"""Preserve private original items through invalidation and trusted corrections."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision='20261106_0044'
down_revision='20261106_0043'
branch_labels=depends_on=None


def upgrade():
    op.create_table('assessment_item_review',
        sa.Column('id',UUID(as_uuid=False),primary_key=True),
        sa.Column('learner_id',UUID(as_uuid=False),sa.ForeignKey('learner.id'),nullable=False),
        sa.Column('assessment_id',UUID(as_uuid=False),nullable=False),sa.Column('question_id',UUID(as_uuid=False),nullable=False),
        sa.Column('revision',sa.BigInteger(),nullable=False),sa.Column('reason',sa.Text(),nullable=False),
        sa.Column('decision',sa.Text(),nullable=False),sa.Column('previous_question',JSONB,nullable=False),
        sa.Column('fingerprint',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['learner_id','assessment_id'],['assessment.learner_id','assessment.id'],ondelete='CASCADE'),
        sa.CheckConstraint("decision IN ('invalidated','corrected')",name='assessment_item_review_decision'))
    op.create_index('idx_assessment_item_review_owner','assessment_item_review',['learner_id','assessment_id','question_id','revision'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM assessment_item_review)')):
        raise RuntimeError('Export item-review history before schema rollback; prior code can run with this additive table.')
    op.drop_table('assessment_item_review')
