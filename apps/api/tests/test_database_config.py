import logging

from china_outbound_analyzer.core.config import get_settings
from china_outbound_analyzer.core.database import (
    _safe_database_url_metadata,
    get_async_engine,
    get_async_sessionmaker,
    get_sync_engine,
    get_sync_sessionmaker,
)


def _clear_database_caches() -> None:
    get_settings.cache_clear()
    get_async_engine.cache_clear()
    get_sync_engine.cache_clear()
    get_async_sessionmaker.cache_clear()
    get_sync_sessionmaker.cache_clear()


def test_sync_engine_accepts_supabase_ssl_variants(monkeypatch) -> None:
    variants = [
        "postgresql+psycopg://postgres:pass@db.example.supabase.co:5432/postgres?sslmode=require",
        "postgresql+psycopg://postgres:pass@db.example.supabase.co:5432/postgres?ssl=require",
        "postgresql://postgres:pass@db.example.supabase.co:5432/postgres?sslmode=require",
        "postgresql://postgres:pass@db.example.supabase.co:5432/postgres?ssl=require",
    ]

    for raw_url in variants:
        _clear_database_caches()
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:pass@db.example.supabase.co:5432/postgres?ssl=require",
        )
        monkeypatch.setenv("SYNC_DATABASE_URL", raw_url)

        engine = get_sync_engine()

        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "db.example.supabase.co"
        assert engine.url.database == "postgres"
        assert engine.url.query == {"sslmode": "require"}
        engine.dispose()

    _clear_database_caches()


def test_async_engine_accepts_supabase_sslmode_and_special_password(monkeypatch) -> None:
    _clear_database_caches()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:pa@ss/word:#@db.example.supabase.co:5432/postgres?sslmode=require",
    )

    engine = get_async_engine()

    assert engine.url.drivername == "postgresql+asyncpg"
    assert engine.url.password == "pa@ss/word:#"
    assert engine.url.query == {"ssl": "require"}
    _clear_database_caches()


def test_database_url_logging_is_masked(monkeypatch, caplog) -> None:
    _clear_database_caches()
    monkeypatch.setenv(
        "SYNC_DATABASE_URL",
        "postgresql+psycopg://postgres:secret-password@db.example.supabase.co:5432/postgres?sslmode=require",
    )
    caplog.set_level(logging.INFO, logger="china_outbound_analyzer.core.database")

    engine = get_sync_engine()

    assert "secret-password" not in caplog.text
    assert "driver=postgresql+psycopg" in caplog.text
    assert "host=db.example.supabase.co" in caplog.text
    assert "ssl=require" in caplog.text
    engine.dispose()
    _clear_database_caches()


def test_safe_database_url_metadata_never_returns_password() -> None:
    metadata = _safe_database_url_metadata(
        "postgresql+psycopg://postgres:secret-password@db.example.supabase.co:5432/postgres?sslmode=require"
    )

    assert metadata == {
        "driver": "postgresql+psycopg",
        "host": "db.example.supabase.co",
        "port": 5432,
        "database": "postgres",
        "ssl": "require",
    }
