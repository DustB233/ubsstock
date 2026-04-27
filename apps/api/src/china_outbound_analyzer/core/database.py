import logging
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from china_outbound_analyzer.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class DatabaseUnavailableError(RuntimeError):
    """Raised when a database session cannot be created from runtime configuration."""


@lru_cache
def get_async_engine():
    try:
        settings = get_settings()
        _log_database_url("async", settings.database_url)
        return create_async_engine(settings.database_url, pool_pre_ping=True)
    except Exception as exc:  # pragma: no cover - exact provider errors vary by runtime
        logger.exception("Async database engine configuration failed.")
        raise DatabaseUnavailableError("Async database engine could not be configured.") from exc


@lru_cache
def get_sync_engine():
    try:
        settings = get_settings()
        _log_database_url("sync", settings.sync_database_url)
        return create_engine(settings.sync_database_url, pool_pre_ping=True)
    except Exception as exc:  # pragma: no cover - exact provider errors vary by runtime
        logger.exception("Sync database engine configuration failed.")
        raise DatabaseUnavailableError("Sync database engine could not be configured.") from exc


@lru_cache
def get_async_sessionmaker():
    return async_sessionmaker(
        bind=get_async_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


@lru_cache
def get_sync_sessionmaker():
    return sessionmaker(bind=get_sync_engine(), expire_on_commit=False, class_=Session)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_sessionmaker()() as session:
        yield session


def get_sync_session() -> Session:
    return get_sync_sessionmaker()()


def _log_database_url(kind: str, value: str) -> None:
    metadata = _safe_database_url_metadata(value)
    logger.info(
        "Configuring %s database engine driver=%s host=%s port=%s database=%s ssl=%s",
        kind,
        metadata["driver"],
        metadata["host"],
        metadata["port"],
        metadata["database"],
        metadata["ssl"],
    )


def _safe_database_url_metadata(value: str) -> dict[str, Any]:
    try:
        url = make_url(value)
    except Exception:
        return {
            "driver": "unparseable",
            "host": None,
            "port": None,
            "database": None,
            "ssl": None,
        }

    return {
        "driver": url.drivername,
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "ssl": url.query.get("sslmode") or url.query.get("ssl"),
    }
