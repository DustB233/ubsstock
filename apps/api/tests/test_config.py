from sqlalchemy.engine import make_url

from china_outbound_analyzer.core.config import Settings


def test_settings_normalizes_common_postgres_urls() -> None:
    settings = Settings(
        database_url="postgres://user:pass@example.com:5432/db",
        sync_database_url="postgresql://user:pass@example.com:5432/db",
    )

    assert settings.database_url == "postgresql+asyncpg://user:pass@example.com:5432/db"
    assert settings.sync_database_url == "postgresql+psycopg://user:pass@example.com:5432/db"


def test_settings_normalizes_asyncpg_sslmode_query() -> None:
    settings = Settings(
        database_url="postgresql://user:pass@example.com:5432/db?sslmode=require",
        sync_database_url="postgresql://user:pass@example.com:5432/db?sslmode=require",
    )

    assert settings.database_url == "postgresql+asyncpg://user:pass@example.com:5432/db?ssl=require"
    assert (
        settings.sync_database_url
        == "postgresql+psycopg://user:pass@example.com:5432/db?sslmode=require"
    )


def test_settings_normalizes_supabase_async_and_sync_urls() -> None:
    async_password = "pa@ss/word:#"
    sync_password = "sync@pass/word:#"
    settings = Settings(
        database_url=(
            "postgresql+asyncpg://postgres:"
            f"{async_password}@db.zcxhfxcmbqbnrisevsaw.supabase.co:5432/postgres?ssl=require"
        ),
        sync_database_url=(
            "postgresql+psycopg://postgres:"
            f"{sync_password}@db.zcxhfxcmbqbnrisevsaw.supabase.co:5432/postgres?sslmode=require"
        ),
    )

    async_url = make_url(settings.database_url)
    sync_url = make_url(settings.sync_database_url)

    assert async_url.drivername == "postgresql+asyncpg"
    assert async_url.password == async_password
    assert async_url.host == "db.zcxhfxcmbqbnrisevsaw.supabase.co"
    assert async_url.query == {"ssl": "require"}
    assert sync_url.drivername == "postgresql+psycopg"
    assert sync_url.password == sync_password
    assert sync_url.host == "db.zcxhfxcmbqbnrisevsaw.supabase.co"
    assert sync_url.query == {"sslmode": "require"}


def test_settings_accepts_supabase_sync_ssl_variants() -> None:
    variants = [
        "postgresql+psycopg://postgres:pass@db.example.supabase.co:5432/postgres?sslmode=require",
        "postgresql+psycopg://postgres:pass@db.example.supabase.co:5432/postgres?ssl=require",
        "postgresql://postgres:pass@db.example.supabase.co:5432/postgres?sslmode=require",
        "postgresql://postgres:pass@db.example.supabase.co:5432/postgres?ssl=require",
    ]

    for raw_url in variants:
        settings = Settings(sync_database_url=raw_url)
        parsed = make_url(settings.sync_database_url)
        assert parsed.drivername == "postgresql+psycopg"
        assert parsed.host == "db.example.supabase.co"
        assert parsed.database == "postgres"
        assert parsed.query == {"sslmode": "require"}


def test_settings_accepts_comma_separated_cors_origins() -> None:
    settings = Settings(cors_origins="https://web.example.com, https://preview.example.com")

    assert settings.cors_origins == ["https://web.example.com", "https://preview.example.com"]


def test_settings_accepts_json_cors_origins() -> None:
    settings = Settings(cors_origins='["https://web.example.com","https://preview.example.com"]')

    assert settings.cors_origins == ["https://web.example.com", "https://preview.example.com"]


def test_settings_tolerates_malformed_json_cors_origins() -> None:
    settings = Settings(cors_origins='["https://web.example.com"')

    assert settings.cors_origins == ['["https://web.example.com"']


def test_settings_accepts_cors_origins_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://web.example.com,https://preview.example.com")

    settings = Settings()

    assert settings.cors_origins == ["https://web.example.com", "https://preview.example.com"]
