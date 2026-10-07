from sqlalchemy import Table, Column, Text, Uuid, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, func

from app.db.metadata import metadata


def created():
    return Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now())


learner = Table('learner', metadata,
    Column('id', Uuid(as_uuid=False), primary_key=True), created(),
)
mentra_account = Table('mentra_account', metadata,
    Column('user_id', Uuid(as_uuid=False), primary_key=True),
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False, unique=True),
    Column('username', Text, nullable=False, unique=True),
    Column('password_hash', Text, nullable=False), created(),
    UniqueConstraint('learner_id', 'user_id', name='uq_mentra_account_owner'),
    CheckConstraint("length(username) BETWEEN 3 AND 64 AND username = lower(username)", name='username'),
)
external_identity = Table('external_identity', metadata,
    Column('provider', Text, primary_key=True), Column('external_subject_id', Text, primary_key=True),
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False), created(),
    CheckConstraint('length(provider) BETWEEN 1 AND 64 AND length(external_subject_id) BETWEEN 1 AND 300', name='identity'),
    Index('idx_external_identity_learner', 'learner_id'),
)
auth_session = Table('auth_session', metadata,
    Column('session_id', Uuid(as_uuid=False), primary_key=True),
    Column('token_digest', Text, nullable=False, unique=True),
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id'), nullable=False),
    Column('user_id', Uuid(as_uuid=False)), Column('provider', Text),
    Column('expires_at', DateTime(timezone=True)),
    Column('revoked_at', DateTime(timezone=True)), created(),
    ForeignKeyConstraint(['learner_id', 'user_id'], ['mentra_account.learner_id', 'mentra_account.user_id']),
    CheckConstraint("(user_id IS NOT NULL AND provider IS NULL) OR (user_id IS NULL AND provider IS NOT NULL)", name='origin'),
    CheckConstraint('expires_at > created_at', name='expiry'),
    CheckConstraint('expires_at IS NOT NULL OR user_id IS NOT NULL', name='persistent_standalone'),
    CheckConstraint('length(token_digest) = 64', name='digest'),
    Index('idx_auth_session_learner', 'learner_id'), Index('idx_auth_session_expiry', 'expires_at'),
)
