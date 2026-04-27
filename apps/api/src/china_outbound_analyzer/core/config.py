import json
from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field
from pydantic.functional_validators import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_postgres_url(value: str, *, async_driver: bool) -> str:
    normalized = value.strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized.removeprefix("postgres://")

    driver = "postgresql+asyncpg://" if async_driver else "postgresql+psycopg://"
    for prefix in (
        "postgresql://",
        "postgresql+asyncpg://",
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
    ):
        if normalized.startswith(prefix):
            return driver + normalized.removeprefix(prefix)

    return normalized


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/china_outbound",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )
    sync_database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/china_outbound",
        validation_alias=AliasChoices("SYNC_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL"),
    )
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    cron_secret: str | None = None
    cron_auto_migrate_enabled: bool = True
    cron_prices_lookback_days: int = 400
    cron_news_limit: int = 10
    cron_announcements_limit: int = 12
    cron_announcements_lookback_days: int = 365
    cron_ai_batch_size: int = 3
    price_data_provider: str = "yahoo_finance"
    price_request_timeout_seconds: float = 12.0
    price_request_max_retries: int = 3
    news_data_provider: str = "google_news_rss"
    news_request_timeout_seconds: float = 12.0
    news_request_max_retries: int = 3
    announcements_data_provider: str = "cninfo"
    announcements_request_timeout_seconds: float = 20.0
    announcements_request_max_retries: int = 2
    fundamentals_data_provider: str = "akshare"
    fundamentals_request_timeout_seconds: float = 20.0
    fundamentals_request_max_retries: int = 2
    ai_analysis_provider: str = "openai"
    ai_analysis_model: str = "gpt-5.4-mini"
    ai_analysis_base_url: str = "https://api.openai.com/v1"
    ai_analysis_request_timeout_seconds: float = 45.0
    ai_analysis_max_retries: int = 2
    ai_analysis_reasoning_effort: str = "medium"
    ai_analysis_verbosity: str = "low"
    scheduler_poll_seconds: int = 30
    scheduler_running_job_stale_after_seconds: int = 7200
    scheduler_prices_enabled: bool = True
    scheduler_prices_interval_minutes: int = 60
    scheduler_prices_lookback_days: int = 400
    scheduler_news_enabled: bool = True
    scheduler_news_interval_minutes: int = 60
    scheduler_news_limit: int = 10
    scheduler_announcements_enabled: bool = True
    scheduler_announcements_interval_minutes: int = 120
    scheduler_announcements_limit: int = 12
    scheduler_announcements_lookback_days: int = 365
    scheduler_fundamentals_enabled: bool = True
    scheduler_fundamentals_interval_minutes: int = 360
    scheduler_analyze_enabled: bool = True
    scheduler_analyze_interval_minutes: int = 60
    scheduler_score_enabled: bool = True
    scheduler_score_interval_minutes: int = 60
    openai_api_key: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def _validate_database_url(cls, value: Any) -> str:
        return _normalize_postgres_url(str(value), async_driver=True)

    @field_validator("sync_database_url", mode="before")
    @classmethod
    def _validate_sync_database_url(cls, value: Any) -> str:
        return _normalize_postgres_url(str(value), async_driver=False)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _validate_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON value must be a list.")
                return [str(item) for item in parsed]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
