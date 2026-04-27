from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from china_outbound_analyzer.core.config import Settings
from china_outbound_analyzer.core.database import Base
from china_outbound_analyzer.models.entities import DataSource, NewsItem, Stock, StockIdentifier
from china_outbound_analyzer.models.enums import DataSourceKind, IdentifierType, JobStatus
from china_outbound_analyzer.services.adapters.base import NewsAdapter, NewsRecord
from china_outbound_analyzer.services.ingestion.google_news_rss_adapter import (
    GoogleNewsRSSAdapter,
    build_google_news_query,
    deduplicate_news_records,
    parse_google_news_feed,
    resolve_stock_for_symbol,
)
from china_outbound_analyzer.services.ingestion.news_refresh import (
    GOOGLE_NEWS_SOURCE_KEY,
    MOCK_NEWS_SOURCE_KEY,
    NewsRefreshService,
    build_news_adapter,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "CHAR(36)"


class FailingNewsAdapter(NewsAdapter):
    async def fetch_recent_news(self, symbol: str, limit: int = 20) -> list[NewsRecord]:
        raise RuntimeError("primary provider failure")


class StubNewsAdapter(NewsAdapter):
    def __init__(self, external_id_factory=None) -> None:
        self.external_id_factory = external_id_factory or (lambda symbol: f"{symbol.lower()}-stub")

    async def fetch_recent_news(self, symbol: str, limit: int = 20) -> list[NewsRecord]:
        return [
            NewsRecord(
                symbol=symbol,
                title=f"{symbol} stub article",
                url="https://stub.local/article",
                published_at=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
                summary="Stub summary",
                external_id=self.external_id_factory(symbol),
                provider="Stub Source",
                source_url="https://stub.local",
                raw_payload={"source_url": "https://stub.local"},
            )
        ]


class SymbolFailingNewsRefreshService(NewsRefreshService):
    def __init__(self, *args, failing_symbol: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.failing_symbol = failing_symbol

    def _ingest_news(
        self,
        stock_id,
        symbol: str,
        fetched,
        source_ids,
        ingestion_runs,
    ) -> int:
        rows_written = super()._ingest_news(
            stock_id=stock_id,
            symbol=symbol,
            fetched=fetched,
            source_ids=source_ids,
            ingestion_runs=ingestion_runs,
        )
        if symbol == self.failing_symbol:
            raise RuntimeError("intentional symbol failure")
        return rows_written


def _build_test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)()


def _seed_news_universe(session: Session, symbols: list[str]) -> dict[str, object]:
    news_source = DataSource(
        source_key=MOCK_NEWS_SOURCE_KEY,
        display_name="Mock News",
        kind=DataSourceKind.NEWS,
        is_mock=True,
        base_url="https://example.test/mock-news",
    )
    session.add(news_source)
    session.flush()

    identifiers: dict[str, StockIdentifier] = {}
    for index, symbol in enumerate(symbols):
        exchange = "HKEX" if symbol.endswith(".HK") else "SZSE"
        currency = "HKD" if symbol.endswith(".HK") else "CNY"
        identifier_type = IdentifierType.H_SHARE if symbol.endswith(".HK") else IdentifierType.A_SHARE

        stock = Stock(
            slug=f"stock-{index}",
            company_name=f"Stock {index}",
            company_name_zh=f"示例公司{index}",
            sector="Industrial",
            outbound_theme="Test universe for news refresh regression coverage.",
            primary_exchange=exchange,
            is_active=True,
        )
        session.add(stock)
        session.flush()

        identifier = StockIdentifier(
            stock_id=stock.id,
            identifier_type=identifier_type,
            exchange_code=exchange,
            ticker=symbol.split(".")[0],
            composite_symbol=symbol,
            currency=currency,
            is_primary=True,
        )
        session.add(identifier)
        session.flush()
        identifiers[symbol] = identifier

    return {"source": news_source, "identifiers": identifiers}


def _sample_feed_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rss version="2.0">
  <channel>
    <title>"CATL when:30d" - Google News</title>
    <link>https://news.google.com/search?q=CATL+when:30d</link>
    <item>
      <title>CATL considers possible $5 billion share sale, Bloomberg News reports - Reuters</title>
      <link>https://news.google.com/rss/articles/item-1</link>
      <guid isPermaLink="false">guid-1</guid>
      <pubDate>Mon, 13 Apr 2026 13:33:43 GMT</pubDate>
      <description>&lt;a href="https://news.google.com/rss/articles/item-1"&gt;CATL considers possible $5 billion share sale, Bloomberg News reports&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Reuters&lt;/font&gt;</description>
      <source url="https://www.reuters.com">Reuters</source>
    </item>
    <item>
      <title>CATL considers possible $5bn share sale, Bloomberg reports - Reuters</title>
      <link>https://news.google.com/rss/articles/item-2</link>
      <guid isPermaLink="false">guid-2</guid>
      <pubDate>Mon, 13 Apr 2026 14:10:00 GMT</pubDate>
      <description>&lt;a href="https://news.google.com/rss/articles/item-2"&gt;CATL considers possible $5bn share sale, Bloomberg reports&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Reuters&lt;/font&gt;</description>
      <source url="https://www.reuters.com">Reuters</source>
    </item>
    <item>
      <title>CATL sodium-ion battery systems draw investor attention - Energy-Storage.News</title>
      <link>https://news.google.com/rss/articles/item-3</link>
      <guid isPermaLink="false">guid-3</guid>
      <pubDate>Tue, 14 Apr 2026 02:06:00 GMT</pubDate>
      <description>&lt;a href="https://news.google.com/rss/articles/item-3"&gt;CATL sodium-ion battery systems draw investor attention&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Energy-Storage.News&lt;/font&gt;</description>
      <source url="https://www.energy-storage.news">Energy-Storage.News</source>
    </item>
  </channel>
</rss>
"""


async def test_build_news_adapter_respects_config() -> None:
    source_key, adapter = build_news_adapter(Settings(news_data_provider="mock"))
    assert source_key == MOCK_NEWS_SOURCE_KEY
    assert adapter.__class__.__name__ == "MockNewsAdapter"

    source_key, adapter = build_news_adapter(Settings(news_data_provider="google_news_rss"))
    assert source_key == GOOGLE_NEWS_SOURCE_KEY
    assert isinstance(adapter, GoogleNewsRSSAdapter)
    await adapter.aclose()


def test_google_news_query_uses_company_aliases() -> None:
    stock = resolve_stock_for_symbol("1211.HK")
    query = build_google_news_query(stock)

    assert '"BYD"' in query
    assert '"比亚迪"' in query
    assert "when:30d" in query


def test_google_news_feed_parser_extracts_metadata_and_deduplicates() -> None:
    records = parse_google_news_feed(
        symbol="300750.SZ",
        query='("CATL" OR "宁德时代") when:30d',
        feed_xml=_sample_feed_xml(),
    )

    assert len(records) == 3
    assert records[0].provider == "Reuters"
    assert records[0].source_url == "https://www.reuters.com"
    assert records[0].external_id == "guid-1"
    assert records[0].title == "CATL considers possible $5 billion share sale, Bloomberg News reports"

    deduped = deduplicate_news_records(records, limit=10)
    assert len(deduped) == 2
    assert {item.provider for item in deduped} == {"Reuters", "Energy-Storage.News"}


async def test_news_refresh_service_falls_back_to_mock_when_primary_fails() -> None:
    service = NewsRefreshService(
        session=None,
        settings=Settings(news_data_provider="google_news_rss"),
        primary_news_adapter=FailingNewsAdapter(),
        fallback_news_adapter=StubNewsAdapter(),
        primary_source_key=GOOGLE_NEWS_SOURCE_KEY,
    )

    result = await service._fetch_news_payload(symbol="300750.SZ", limit=5)

    assert result.source_key == MOCK_NEWS_SOURCE_KEY
    assert result.used_fallback is True
    assert len(result.records) == 1
    assert result.records[0].provider == "Stub Source"


async def test_news_refresh_service_normalizes_long_external_ids_and_persists_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_test_session()
    _seed_news_universe(session, ["300750.SZ"])
    long_external_id = "google-news-" + ("x" * 240)

    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.news_refresh.seed_universe",
        lambda _session: None,
    )

    service = NewsRefreshService(
        session=session,
        settings=Settings(news_data_provider="mock"),
        primary_news_adapter=StubNewsAdapter(
            external_id_factory=lambda _symbol: long_external_id,
        ),
        fallback_news_adapter=StubNewsAdapter(),
        primary_source_key=MOCK_NEWS_SOURCE_KEY,
        fallback_source_key=MOCK_NEWS_SOURCE_KEY,
    )

    result = await service.run(limit_per_symbol=5)

    persisted_item = session.query(NewsItem).one()
    refresh_job_status = session.execute(
        text("select status from refresh_jobs where job_name = 'refresh-news'")
    ).scalar_one()

    assert result["status"] == JobStatus.SUCCESS.value
    assert result["news_items"] == 1
    assert len(persisted_item.external_id) <= 128
    assert persisted_item.external_id != long_external_id
    assert persisted_item.raw_payload["provider_external_id"] == long_external_id
    assert refresh_job_status == JobStatus.SUCCESS.value


async def test_news_refresh_service_rolls_back_failed_symbol_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_test_session()
    seeded = _seed_news_universe(session, ["FAIL.SZ", "PASS.HK"])
    identifiers = seeded["identifiers"]

    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.news_refresh.seed_universe",
        lambda _session: None,
    )

    service = SymbolFailingNewsRefreshService(
        session=session,
        settings=Settings(news_data_provider="mock"),
        primary_news_adapter=StubNewsAdapter(),
        fallback_news_adapter=StubNewsAdapter(),
        primary_source_key=MOCK_NEWS_SOURCE_KEY,
        fallback_source_key=MOCK_NEWS_SOURCE_KEY,
        failing_symbol="FAIL.SZ",
    )

    result = await service.run(limit_per_symbol=5)

    persisted_items = session.query(NewsItem).all()
    persisted_mentions = session.execute(
        text("select stock_id from stock_news_mentions")
    ).scalars().all()
    refresh_job_status = session.execute(
        text("select status from refresh_jobs where job_name = 'refresh-news'")
    ).scalar_one()

    assert result["status"] == JobStatus.PARTIAL.value
    assert result["symbols"] == 1
    assert result["failed_symbols"] == 1
    assert len(persisted_items) == 1
    assert persisted_mentions == [str(identifiers["PASS.HK"].stock_id).replace("-", "")]
    assert refresh_job_status == JobStatus.PARTIAL.value
