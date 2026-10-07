from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.auth.config import ExternalProviderSettings


class Settings(BaseSettings):
    app_env: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = ""
    auth_session_seconds: int = Field(default=3600, ge=60, le=86400)
    auth_cookie_secure: bool = False
    auth_cookie_same_site: Literal['lax', 'strict', 'none'] = 'lax'
    auth_external_providers: dict[str, ExternalProviderSettings] = Field(default_factory=dict)
    ai_provider: str = "openai_compatible"
    ai_model: str = ""
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_temperature: float = Field(default=0.2, ge=0, le=2)
    ai_timeout: float = Field(default=30, gt=0)
    ai_max_retries: int = Field(default=2, ge=0)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = ""
    qdrant_distance: str = "Cosine"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode='after')
    def cookie_settings(self):
        development = self.app_env.lower() in {'development', 'dev', 'test'}
        if self.auth_cookie_same_site == 'none' and development and not self.auth_cookie_secure:
            raise ValueError('AUTH_COOKIE_SAME_SITE=none requires AUTH_COOKIE_SECURE=true and HTTPS')
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
