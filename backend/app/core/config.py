from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    sqlite_db_path: str = "/data/mentra.db"
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

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
