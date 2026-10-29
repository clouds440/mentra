"""Remember accepted subject-scoped skill aliases without repeating model work."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision='20261029_0037'
down_revision='20261028_0036'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('skill_resolution_binding',
        sa.Column('learner_id',postgresql.UUID(as_uuid=False),sa.ForeignKey('learner.id'),primary_key=True),
        sa.Column('context_id',sa.Text(),primary_key=True),
        sa.Column('subject_key',sa.Text(),primary_key=True),sa.Column('label_key',sa.Text(),primary_key=True),
        sa.Column('concept_id',sa.Text(),nullable=False),
        sa.Column('topic_id',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['learner_id','context_id'],['learning_context.learner_id','learning_context.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['learner_id','concept_id'],['topic_skill.learner_id','topic_skill.concept_id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['learner_id','topic_id'],['learning_topic.learner_id','learning_topic.id'],ondelete='CASCADE'))

def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM skill_resolution_binding)')):
        raise RuntimeError('Preserve accepted skill aliases; roll forward instead of deleting identity bindings.')
    op.drop_table('skill_resolution_binding')
