from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration. Every value has a sane local-dev default;
    production deploys override via environment variables — never edit
    defaults here for a specific environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DataLume API"
    environment: str = "local"

    database_url: str = "postgresql+psycopg://datalume:datalume@localhost:5433/datalume"
    redis_url: str = "redis://localhost:6380/0"

    session_cookie_name: str = "datalume_session"
    session_ttl_seconds: int = 60 * 60 * 12  # 12h sliding
    secret_key: str = "dev-only-change-me"

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    cors_origins: list[str] = ["http://localhost:3100"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
