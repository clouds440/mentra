from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Account:
    user_id: str
    learner_id: str
    username: str
    password_hash: str


@dataclass(frozen=True)
class AuthenticatedIdentity:
    learner_id: str
    session_id: str
    expires_at: datetime | None
    user_id: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class VerifiedExternalIdentity:
    provider: str
    subject: str
    expires_at: datetime
