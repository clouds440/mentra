"""Transactional identity provisioning and sessions through SQLAlchemy 2.x."""
from hashlib import blake2b
from uuid import uuid4
from sqlalchemy import select, update, text, or_
from app.auth.errors import AccountExistsError, AuthenticationError
from app.auth.models import Account, AuthenticatedIdentity
from .tables import learner, mentra_account, external_identity, auth_session


class PostgresIdentityRepository:
    def __init__(self, session_factory):
        self.sessions = session_factory

    @staticmethod
    def _lock(session, identity):
        key = int.from_bytes(blake2b(('mentra:identity:' + identity).encode(), digest_size=8).digest(), 'big', signed=True)
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})

    @staticmethod
    def _principal(row):
        return AuthenticatedIdentity(**{field: row[field] for field in AuthenticatedIdentity.__dataclass_fields__})

    @staticmethod
    def _create_session(session, learner_id, digest, expires, now, *, user_id=None, provider=None):
        row = dict(session_id=str(uuid4()), learner_id=learner_id, user_id=user_id, provider=provider,
                   token_digest=digest, expires_at=expires, created_at=now)
        session.execute(auth_session.insert().values(**row))
        return PostgresIdentityRepository._principal(row)

    def get_account(self, username):
        with self.sessions.begin() as session:
            row = session.execute(select(mentra_account).where(mentra_account.c.username == username)).mappings().first()
            return Account(**{field: row[field] for field in Account.__dataclass_fields__}) if row else None

    def register(self, username, password_hash, token_digest, expires_at, now):
        with self.sessions.begin() as session:
            self._lock(session, 'account:' + username)
            if session.execute(select(mentra_account.c.user_id).where(mentra_account.c.username == username)).first():
                raise AccountExistsError()
            learner_id, user_id = str(uuid4()), str(uuid4())
            session.execute(learner.insert().values(id=learner_id, created_at=now))
            session.execute(mentra_account.insert().values(user_id=user_id, learner_id=learner_id,
                username=username, password_hash=password_hash, created_at=now))
            return self._create_session(session, learner_id, token_digest, expires_at, now, user_id=user_id)

    def create_account_session(self, account, token_digest, expires_at, now, new_hash=None):
        with self.sessions.begin() as session:
            row = session.execute(select(mentra_account).where(mentra_account.c.user_id == account.user_id).with_for_update()).mappings().first()
            if not row or row['password_hash'] != account.password_hash or row['learner_id'] != account.learner_id:
                raise AuthenticationError()
            if new_hash is not None:
                session.execute(update(mentra_account).where(mentra_account.c.user_id == account.user_id).values(password_hash=new_hash))
            return self._create_session(session, account.learner_id, token_digest, expires_at, now, user_id=account.user_id)

    def external_session(self, provider, subject, token_digest, expires_at, now):
        with self.sessions.begin() as session:
            self._lock(session, 'external:' + provider + ':' + subject)
            learner_id = session.execute(select(external_identity.c.learner_id).where(
                external_identity.c.provider == provider, external_identity.c.external_subject_id == subject)).scalar_one_or_none()
            if learner_id is None:
                learner_id = str(uuid4())
                session.execute(learner.insert().values(id=learner_id, created_at=now))
                session.execute(external_identity.insert().values(provider=provider, external_subject_id=subject,
                    learner_id=learner_id, created_at=now))
            return self._create_session(session, learner_id, token_digest, expires_at, now, provider=provider)

    def get_session(self, token_digest, now):
        with self.sessions.begin() as session:
            row = session.execute(select(auth_session).where(auth_session.c.token_digest == token_digest,
                auth_session.c.revoked_at.is_(None),
                or_(auth_session.c.expires_at.is_(None), auth_session.c.expires_at > now))).mappings().first()
            return self._principal(row) if row else None

    def revoke_session(self, token_digest, now):
        with self.sessions.begin() as session:
            session.execute(update(auth_session).where(auth_session.c.token_digest == token_digest,
                auth_session.c.revoked_at.is_(None)).values(revoked_at=now))
