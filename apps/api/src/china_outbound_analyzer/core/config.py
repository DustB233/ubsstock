import json
from functools import lru_cache
from typing import Annotated, Any
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import AliasChoices, Field
from pydantic.functional_validators import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


def _normalize_postgres_url(value: str, *, async_driver: bool) -> str:
    normalized = value.strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized.removeprefix("postgres://")

    driver = "postgresql+asyncpg://" if async_driver else "postgresql+psycopg://"
    driver_name = driver.removesuffix("://")
    for prefix in _POSTGRES_URL_PREFIXES:
        if normalized.startswith(prefix):
            normalized = _build_postgres_url(normalized, driver_name).render_as_string(
                hide_password=False
            )
            break

    return normalized


_POSTGRES_URL_PREFIXES = (
    "postgresql://",
    "postgresql+asyncpg://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
)


def _build_postgres_url(value: str, driver_name: str) -> URL:
    _, _, remainder = value.partition("://")
    if "@" not in remainder:
        url = make_url(value)
        return url.set(
            drivername=driver_name,
            query=_normalize_ssl_query(url.query, async_driver=driver_name.endswith("asyncpg")),
        )

    auth_part, host_part = remainder.rsplit("@", 1)
    username, has_password, password = auth_part.partition(":")
    host_url = urlsplit(f"//{host_part}")

    return URL.create(
        drivername=driver_name,
        username=unquote(username) if username else None,
        password=unquote(password) if has_password else None,
        host=host_url.hostname,
        port=host_url.port,
        database=unquote(host_url.path.lstrip("/")) or None,
        query=_normalize_ssl_query(
            dict(parse_qsl(host_url.query, keep_blank_values=True)),
            async_driver=driver_name.endswith("asyncpg"),
        ),
    )


def _normalize_ssl_query(query: dict[str, Any], *, async_driver: bool) -> dict[str, Any]:
    normalized = {str(key): str(value) for key, value in dict(query).items()}
    ssl_value = normalized.get("ssl")
    sslmode_value = normalized.get("sslmode")

    if async_driver:
        if ssl_value is None and sslmode_value is not None:
            normalized["ssl"] = sslmode_value
        normalized.pop("sslmode", None)
        return normalized

    if sslmode_value is None and ssl_value is not None:
        normalized["sslmode"] = ssl_value
    normalized.pop("ssl", None)
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
    cors_origins: Annotated[list[str], NoDecode] = [
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
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    return [stripped]
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
                return [stripped]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
