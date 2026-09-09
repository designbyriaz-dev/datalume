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

    # Ask DataLume — architecture/06-intelligence-layer.md §1-2. See
    # app/integrations/llm_provider.py: unset means NullLLMProvider,
    # same "deferred adapter, not a fake implementation" pattern as
    # stripe_secret_key above.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # Local-disk document storage — see app/integrations/storage.py. Swap
    # for a real cloud adapter (S3/Azure Blob) behind the same Protocol
    # for production; architecture 00 §5 / 02 §4.
    local_storage_dir: str = "./storage"

    # Sprint 24 hardening — architecture/09-security-testing-ops.md §1's
    # threat table lists "file type/size allow-list" as the mitigation
    # for malicious file upload; before this, every upload endpoint read
    # an unbounded request body into memory with no cap, a genuine DoS
    # gap found during this sprint's own threat-model pass. 25MB covers
    # every real use case here (CSV imports, PDF/certificate evidence
    # documents) with headroom.
    max_upload_size_bytes: int = 25 * 1024 * 1024

    cors_origins: list[str] = ["http://localhost:3100"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
