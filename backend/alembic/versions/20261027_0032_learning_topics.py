"""Additive broad topics and subskill membership; preserve all learner evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261027_0032'
down_revision = '20261025_0031'
branch_labels = depends_on = None


def upgrade():
    op.create_table('learning_topic',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('learner_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('learner.id'), nullable=False),
        sa.Column('context_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False), sa.Column('normalized_name', sa.Text(), nullable=False),
        sa.Column('scope_key', sa.Text(), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('learner_id', 'id', name='uq_learning_topic_owner_identity'),
        sa.UniqueConstraint('learner_id', 'context_id', 'normalized_name', 'scope_key', name='uq_learning_topic_context_name'),
        sa.ForeignKeyConstraint(['learner_id', 'context_id'], ['learning_context.learner_id', 'learning_context.id']))
    op.create_index('idx_learning_topic_owner', 'learning_topic', ['learner_id', 'context_id', 'normalized_name'])
    op.create_table('topic_skill',
        sa.Column('learner_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('learner.id'), primary_key=True),
        sa.Column('concept_id', sa.Text(), sa.ForeignKey('concept.id'), primary_key=True),
        sa.Column('topic_id', sa.Text(), nullable=True), sa.Column('label', sa.Text(), nullable=False),
        sa.Column('ability', sa.Text(), nullable=False),
        sa.Column('published', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('phrases', sa.Text(), nullable=False, server_default=''),
        sa.Column('resolver_version', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['learner_id', 'topic_id'], ['learning_topic.learner_id', 'learning_topic.id']))
    op.create_index('idx_topic_skill_parent', 'topic_skill', ['learner_id', 'topic_id', 'published'])


def downgrade():
    # Membership contains interpretation, never original evidence. Rollback can
    # use legacy skill reads without destroying that interpretation.
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM topic_skill)')):
        raise RuntimeError('Export topic memberships before removing this migration; use legacy reads for rollback.')
    op.drop_table('topic_skill')
    op.drop_table('learning_topic')
