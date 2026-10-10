from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.auth.config import ExternalProviderSettings


class Settings(BaseSettings):
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'INFO'
    log_format: Literal['console', 'json'] | None = None
    log_file_enabled: bool = True
    log_directory: str = 'logs/backend'
    log_workflow_summaries: bool = True
    log_summary_max_steps: int = Field(default=500, ge=1, le=5000)
    log_event_max_bytes: int = Field(default=32768, ge=8192, le=1048576)
    log_health_requests: bool = False
    log_poll_requests: bool = False
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
    chat_history_token_budget: int = Field(default=4096, ge=256, le=100000)
    chat_context_window_tokens: int = Field(default=16384, ge=1024)
    chat_output_token_reserve: int = Field(default=2048, ge=128)
    memory_active_limit: int = Field(default=200, ge=1, le=1000)
    memory_pending_limit: int = Field(default=50, ge=1, le=1000)
    memory_goal_days: int = Field(default=30, ge=1, le=3650)
    memory_fact_days: int = Field(default=180, ge=1, le=3650)
    memory_preference_days: int = Field(default=365, ge=1, le=3650)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = ""
    qdrant_distance: str = "Cosine"
    rag_storage_dir: str = "/var/lib/mentra/materials"
    rag_max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    rag_max_pages: int = Field(default=200, ge=1, le=1000)
    rag_max_chunks: int = Field(default=5000, ge=1)
    rag_storage_quota_bytes: int = Field(default=512 * 1024 * 1024, ge=1024)
    rag_parser_timeout: int = Field(default=120, ge=1, le=600)
    rag_job_lease_seconds: int = Field(default=300, ge=30)
    rag_hybrid_enabled: bool = True
    rag_reranker_path: str = ''
    rag_reranker_timeout: float = Field(default=5, gt=0, le=30)

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

    @model_validator(mode='after')
    def rag_limits(self):
        if self.rag_job_lease_seconds <= self.rag_parser_timeout:
            raise ValueError('RAG_JOB_LEASE_SECONDS must exceed RAG_PARSER_TIMEOUT')
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
