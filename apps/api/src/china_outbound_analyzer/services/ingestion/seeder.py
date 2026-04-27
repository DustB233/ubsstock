from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from china_outbound_analyzer.models.entities import DataSource, Stock, StockIdentifier
from china_outbound_analyzer.models.enums import DataSourceKind, IdentifierType
from china_outbound_analyzer.seeds.universe import UNIVERSE

DATA_SOURCES = (
    {
        "source_key": "mock_market_data",
        "display_name": "Mock Market Data",
        "kind": DataSourceKind.MARKET_DATA,
        "is_mock": True,
        "base_url": "https://demo.local/market-data",
        "metadata_json": {"phase": 2},
    },
    {
        "source_key": "mock_fundamentals",
        "display_name": "Mock Fundamentals",
        "kind": DataSourceKind.FUNDAMENTALS,
        "is_mock": True,
        "base_url": "https://demo.local/fundamentals",
        "metadata_json": {"phase": 2},
    },
    {
        "source_key": "akshare_fundamentals",
        "display_name": "AkShare Fundamentals",
        "kind": DataSourceKind.FUNDAMENTALS,
        "is_mock": False,
        "base_url": "https://www.akshare.xyz",
        "metadata_json": {"phase": 2, "provider": "akshare"},
    },
    {
        "source_key": "mock_news",
        "display_name": "Mock News",
        "kind": DataSourceKind.NEWS,
        "is_mock": True,
        "base_url": "https://demo.local/news",
        "metadata_json": {"phase": 2},
    },
    {
        "source_key": "google_news_rss",
        "display_name": "Google News RSS",
        "kind": DataSourceKind.NEWS,
        "is_mock": False,
        "base_url": "https://news.google.com/rss/search",
        "metadata_json": {"phase": 2, "provider": "google_news_rss"},
    },
    {
        "source_key": "mock_announcements",
        "display_name": "Mock Announcements",
        "kind": DataSourceKind.ANNOUNCEMENTS,
        "is_mock": True,
        "base_url": "https://demo.local/announcements",
        "metadata_json": {"phase": 2},
    },
    {
        "source_key": "cninfo_announcements",
        "display_name": "CNInfo Disclosures",
        "kind": DataSourceKind.ANNOUNCEMENTS,
        "is_mock": False,
        "base_url": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        "metadata_json": {"phase": 2, "provider": "cninfo"},
    },
    {
        "source_key": "mock_ai",
        "display_name": "Mock AI Metadata",
        "kind": DataSourceKind.AI,
        "is_mock": True,
        "base_url": "https://demo.local/ai",
        "metadata_json": {"phase": 2},
    },
    {
        "source_key": "yahoo_finance_market_data",
        "display_name": "Yahoo Finance Market Data",
        "kind": DataSourceKind.MARKET_DATA,
        "is_mock": False,
        "base_url": "https://query1.finance.yahoo.com/v8/finance/chart",
        "metadata_json": {"phase": 2, "provider": "yahoo_finance"},
    },
)


def seed_universe(session: Session) -> dict[str, int]:
    stock_ids: dict[str, Any] = {}

    for stock in UNIVERSE:
        payload = {
            "slug": stock.slug,
            "company_name": stock.company_name,
            "company_name_zh": stock.company_name_zh,
            "sector": stock.sector,
            "outbound_theme": stock.outbound_theme,
            "primary_exchange": stock.primary_exchange,
            "is_active": True,
        }
        statement = (
            insert(Stock)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=[Stock.slug],
                set_={
                    "company_name": payload["company_name"],
                    "company_name_zh": payload["company_name_zh"],
                    "sector": payload["sector"],
                    "outbound_theme": payload["outbound_theme"],
                    "primary_exchange": payload["primary_exchange"],
                    "is_active": payload["is_active"],
                },
            )
            .returning(Stock.id)
        )
        stock_ids[stock.slug] = session.execute(statement).scalar_one()

    for stock in UNIVERSE:
        stock_id = stock_ids[stock.slug]
        for identifier in stock.identifiers:
            payload = {
                "stock_id": stock_id,
                "identifier_type": IdentifierType(identifier.identifier_type),
                "exchange_code": identifier.exchange_code,
                "ticker": identifier.composite_symbol.split(".")[0],
                "composite_symbol": identifier.composite_symbol,
                "currency": identifier.currency,
                "is_primary": identifier.is_primary,
            }
            statement = (
                insert(StockIdentifier)
                .values(**payload)
                .on_conflict_do_update(
                    index_elements=[StockIdentifier.composite_symbol],
                    set_={
                        "stock_id": stock_id,
                        "identifier_type": payload["identifier_type"],
                        "exchange_code": payload["exchange_code"],
                        "ticker": payload["ticker"],
                        "currency": payload["currency"],
                        "is_primary": payload["is_primary"],
                    },
                )
            )
            session.execute(statement)

    seed_data_sources(session)
    session.commit()
    return {"stocks": len(UNIVERSE), "identifiers": sum(len(item.identifiers) for item in UNIVERSE)}


def seed_data_sources(session: Session) -> dict[str, int]:
    for source in DATA_SOURCES:
        statement = (
            insert(DataSource)
            .values(**source)
            .on_conflict_do_update(
                index_elements=[DataSource.source_key],
                set_={
                    "display_name": source["display_name"],
                    "kind": source["kind"],
                    "is_mock": source["is_mock"],
                    "base_url": source["base_url"],
                    "metadata_json": source["metadata_json"],
                },
            )
        )
        session.execute(statement)

    session.commit()
    return {"data_sources": len(DATA_SOURCES)}


def get_source_id_by_key(session: Session, source_key: str):
    return session.execute(
        select(DataSource.id).where(DataSource.source_key == source_key)
    ).scalar_one()
