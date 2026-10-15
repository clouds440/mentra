from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator, field_validator
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
    log_retention_days: int = Field(default=14, ge=1, le=365)
    log_max_file_bytes: int = Field(default=64 * 1024 * 1024, ge=65536)
    log_queue_bytes: int = Field(default=8 * 1024 * 1024, ge=65536)
    log_shutdown_seconds: float = Field(default=2, gt=0, le=10)
    log_parameter_details: bool = True
    app_env: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = ""
    database_role: Literal['api', 'worker'] = 'api'
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_pool_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_timeout: float = Field(default=5, gt=0, le=60)
    database_connect_timeout: int = Field(default=5, ge=1, le=60)
    database_api_statement_ms: int = Field(default=30000, ge=100, le=300000)
    database_worker_statement_ms: int = Field(default=120000, ge=100, le=1800000)
    database_lock_ms: int = Field(default=5000, ge=100, le=60000)
    auth_session_seconds: int = Field(default=3600, ge=60, le=86400)
    auth_persistent_session_seconds: int = Field(default=30 * 86400, ge=86400, le=365 * 86400)
    auth_cookie_secure: bool = False
    auth_global_capacity: int = Field(default=16, ge=1, le=64)
    auth_owner_capacity: int = Field(default=8, ge=1, le=32)
    auth_account_minute_limit: int = Field(default=20, ge=1, le=100)
    auth_client_minute_limit: int = Field(default=60, ge=1, le=1000)
    work_global_capacity: int = Field(default=16, ge=1, le=100)
    work_owner_capacity: int = Field(default=2, ge=1, le=10)
    parse_global_capacity: int = Field(default=4, ge=1, le=32)
    parse_owner_capacity: int = Field(default=1, ge=1, le=4)
    auth_cookie_same_site: Literal['lax', 'strict', 'none'] = 'lax'
    auth_external_providers: dict[str, ExternalProviderSettings] = Field(default_factory=dict)
    ai_provider: str = "openai_compatible"
    ai_model: str = ""
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_temperature: float = Field(default=0.2, ge=0, le=2)
    ai_timeout: float = Field(default=30, gt=0)
    ai_max_retries: int = Field(default=2, ge=0)
    tool_read_timeout_seconds: float = Field(default=10, gt=0, le=60)
    tool_read_max_attempts: int = Field(default=3, ge=1, le=3)
    web_search_enabled: bool = False
    web_search_timezone: str = 'UTC'
    web_search_daily_limit: int = Field(default=90, ge=1, le=100)
    web_search_user_daily_limit: int = Field(default=10, ge=1, le=100)
    web_search_user_minute_limit: int = Field(default=3, ge=1, le=10)
    web_search_cache_seconds: int = Field(default=120, ge=0, le=300)
    you_web_search_api_key: str = Field(default='', repr=False)
    web_research_daily_limit: int = Field(default=20, ge=1, le=100)
    web_research_user_daily_limit: int = Field(default=5, ge=1, le=100)
    chat_history_token_budget: int = Field(default=1800, ge=256, le=100000)
    chat_input_tokens: int = Field(default=8192, ge=4096, le=16384)
    chat_recovery_input_tokens: int = Field(default=12288, ge=4096, le=16384)
    chat_summary_enabled: bool = True
    chat_context_window_tokens: int = Field(default=16384, ge=1024)
    chat_output_token_reserve: int = Field(default=2048, ge=128)
    assessment_generation_output_tokens: int = Field(default=8192, ge=512, le=32768)
    assessment_grading_output_tokens: int = Field(default=8192, ge=512, le=32768)
    assessment_vision_enabled: bool = True
    ai_vision_model: str = ''
    memory_active_limit: int = Field(default=200, ge=1, le=1000)
    memory_pending_limit: int = Field(default=50, ge=1, le=1000)
    memory_goal_days: int = Field(default=30, ge=1, le=3650)
    memory_fact_days: int = Field(default=180, ge=1, le=3650)
    memory_preference_days: int = Field(default=365, ge=1, le=3650)
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_device: str = "cpu"
    embedding_worker_timeout: float = Field(default=10, gt=0, le=60)
    embedding_initialization_timeout: float = Field(default=45, gt=0, le=120)
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
    document_cpu_seconds: int = Field(default=120, ge=1, le=600)
    document_memory_bytes: int = Field(default=1024 ** 3, ge=64 * 1024 ** 2)
    rag_job_lease_seconds: int = Field(default=300, ge=30)
    rag_hybrid_enabled: bool = True
    rag_reranker_path: str = ''
    rag_reranker_timeout: float = Field(default=5, gt=0, le=30)
    rag_inference_wait_seconds: float = Field(default=2, gt=0, le=10)
    speech_model: Literal['tiny', 'base', 'small'] = 'base'
    speech_model_path: str = ''
    speech_cpu_threads: int = Field(default=2, ge=1, le=16)
    speech_beam_size: int = Field(default=3, ge=1, le=5)
    speech_max_seconds: int = Field(default=30, ge=1, le=30)
    speech_max_upload_bytes: int = Field(default=4 * 1024 * 1024, ge=1024, le=8 * 1024 * 1024)
    speech_timeout_seconds: float = Field(default=20, gt=0, le=60)
    speech_warm_on_startup: bool = True

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

    @field_validator('web_search_timezone')
    @classmethod
    def validate_search_timezone(cls, value):
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(value)
        except (ValueError, KeyError) as error:
            raise ValueError('WEB_SEARCH_TIMEZONE must be an IANA timezone.') from error
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
