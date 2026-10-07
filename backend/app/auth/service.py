"""Authentication orchestrates verification and repositories, never learner scoring."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
import secrets

from app.auth.errors import AuthenticationError
from app.auth.schemas import LoginRequest, RegisterRequest, ExternalLoginRequest, TokenResponse
from app.auth.passwords import Passwords
from app.auth.ports import IdentityRepository


def token_digest(token):
    return sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, repository: IdentityRepository, verifier, *, session_seconds=3600,
                 clock=lambda: datetime.now(timezone.utc), passwords=None):
        self.repository = repository
        self.verifier = verifier
        self.session_seconds = session_seconds
        self.clock = clock
        self.passwords = passwords or Passwords()

    @staticmethod
    def _response(token, identity):
        return TokenResponse(access_token=token, expires_at=identity.expires_at,
            learner_id=identity.learner_id, user_id=identity.user_id, provider=identity.provider,
            username=identity.username)

    def register(self, request: RegisterRequest, *, persistent=False):
        request = RegisterRequest.model_validate(request.model_dump())
        token, now = secrets.token_urlsafe(32), self.clock()
        identity = self.repository.register(request.username,
            self.passwords.hash(request.password.get_secret_value()), token_digest(token),
            None if persistent else now + timedelta(seconds=self.session_seconds), now)
        return self._response(token, identity)

    def login(self, request: LoginRequest, *, persistent=False):
        request = LoginRequest.model_validate(request.model_dump())
        account = self.repository.get_account(request.username)
        password = request.password.get_secret_value()
        if not self.passwords.verify(password, account.password_hash if account else None):
            raise AuthenticationError()
        new_hash = self.passwords.hash(password) if self.passwords.needs_rehash(account.password_hash) else None
        token, now = secrets.token_urlsafe(32), self.clock()
        identity = self.repository.create_account_session(account, token_digest(token),
            None if persistent else now + timedelta(seconds=self.session_seconds), now, new_hash)
        return self._response(token, identity)

    def external_login(self, request: ExternalLoginRequest, *, expected_subject: str | None = None):
        request = ExternalLoginRequest.model_validate(request.model_dump())
        assertion = self.verifier.verify(request.provider, request.token.get_secret_value())
        if expected_subject is not None and assertion.subject != expected_subject:
            raise AuthenticationError()
        token, now = secrets.token_urlsafe(32), self.clock()
        expires = min(assertion.expires_at, now + timedelta(seconds=self.session_seconds))
        if expires <= now:
            raise AuthenticationError()
        identity = self.repository.external_session(assertion.provider, assertion.subject,
            token_digest(token), expires, now)
        return self._response(token, identity)

    def authenticate(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise AuthenticationError()
        identity = self.repository.get_session(token_digest(token), self.clock())
        if identity is None:
            raise AuthenticationError()
        return identity

    def logout(self, token):
        self.authenticate(token)
        self.repository.revoke_session(token_digest(token), self.clock())
