"""Allow standalone browser sessions to remain valid until explicitly revoked."""
from alembic import op
import sqlalchemy as sa

revision = '20261007_0002'
down_revision = '20261007_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('auth_session', 'expires_at', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.create_check_constraint(op.f('ck_auth_session_persistent_standalone'), 'auth_session',
                               'expires_at IS NOT NULL OR user_id IS NOT NULL')


def downgrade():
    # Preserve the session history, revoke persistent access before restoring finite expiry.
    op.execute("UPDATE auth_session SET revoked_at=coalesce(revoked_at, now()), "
               "expires_at=greatest(now(), created_at + interval '1 second') WHERE expires_at IS NULL")
    op.drop_constraint(op.f('ck_auth_session_persistent_standalone'), 'auth_session', type_='check')
    op.alter_column('auth_session', 'expires_at', existing_type=sa.DateTime(timezone=True), nullable=False)
