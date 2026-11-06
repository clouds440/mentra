"""Bound topical source-observation retrieval without scanning lifetime history."""
from alembic import op

revision='20261106_0047'
down_revision='20261106_0046'
branch_labels=depends_on=None

def upgrade():
    op.execute("CREATE INDEX idx_learning_signal_search ON learning_signal USING gin (to_tsvector('simple'::regconfig, normalized_label || ' ' || topic))")
    op.create_index('idx_chat_capture_owner','chat_evidence_job',['learner_id','state','created_at','turn_id'])

def downgrade():
    op.drop_index('idx_chat_capture_owner',table_name='chat_evidence_job')
    op.drop_index('idx_learning_signal_search',table_name='learning_signal')
