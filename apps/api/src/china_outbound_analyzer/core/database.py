from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from china_outbound_analyzer.core.config import get_settings


class Base(DeclarativeBase):
    pass


class DatabaseUnavailableError(RuntimeError):
    """Raised when a database session cannot be created from runtime configuration."""


@lru_cache
def get_async_engine():
    try:
        settings = get_settings()
        return create_async_engine(settings.database_url, pool_pre_ping=True)
    except Exception as exc:  # pragma: no cover - exact provider errors vary by runtime
        raise DatabaseUnavailableError("Async database engine could not be configured.") from exc


@lru_cache
def get_sync_engine():
    try:
        settings = get_settings()
        return create_engine(settings.sync_database_url, pool_pre_ping=True)
    except Exception as exc:  # pragma: no cover - exact provider errors vary by runtime
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
