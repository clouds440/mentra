import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from app.core.identifiers import LearnerId


class AuthSchema(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LoginRequest(AuthSchema):
    username: str = Field(min_length=3, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,63}', value):
            raise ValueError('Username must contain 3-64 letters, numbers, dots, underscores, or hyphens')
        return value


class RegisterRequest(LoginRequest):
    password: SecretStr = Field(min_length=12, max_length=256)


class ExternalLoginRequest(AuthSchema):
    provider: str = Field(min_length=1, max_length=64, pattern=r'^[a-z0-9][a-z0-9_-]*$')
    token: SecretStr = Field(min_length=1, max_length=16000)


class IdentityResponse(AuthSchema):
    learner_id: LearnerId
    user_id: str | None = None
    provider: str | None = None


class TokenResponse(IdentityResponse):
    access_token: str
    token_type: str = 'bearer'
    expires_at: datetime | None
