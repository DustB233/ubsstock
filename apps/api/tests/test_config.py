from china_outbound_analyzer.core.config import Settings


def test_settings_normalizes_common_postgres_urls() -> None:
    settings = Settings(
        database_url="postgres://user:pass@example.com:5432/db",
        sync_database_url="postgresql://user:pass@example.com:5432/db",
    )

    assert settings.database_url == "postgresql+asyncpg://user:pass@example.com:5432/db"
    assert settings.sync_database_url == "postgresql+psycopg://user:pass@example.com:5432/db"


def test_settings_accepts_comma_separated_cors_origins() -> None:
    settings = Settings(cors_origins="https://web.example.com, https://preview.example.com")

    assert settings.cors_origins == ["https://web.example.com", "https://preview.example.com"]


def test_settings_accepts_json_cors_origins() -> None:
    settings = Settings(cors_origins='["https://web.example.com","https://preview.example.com"]')

    assert settings.cors_origins == ["https://web.example.com", "https://preview.example.com"]
