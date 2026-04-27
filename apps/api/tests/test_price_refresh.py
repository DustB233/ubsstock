from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from china_outbound_analyzer.core.config import Settings
from china_outbound_analyzer.core.database import Base
from china_outbound_analyzer.models.entities import DataSource, PriceBar, Stock, StockIdentifier
from china_outbound_analyzer.models.enums import (
    DataSourceKind,
    IdentifierType,
    JobStatus,
    PriceInterval,
    coerce_price_interval,
)
from china_outbound_analyzer.services.adapters.base import (
    FinancialMetricRecord,
    HistoricalPriceRecord,
    LatestPriceSnapshotRecord,
    MarketDataAdapter,
    ValuationRecord,
)
from china_outbound_analyzer.services.ingestion.price_refresh import (
    MOCK_SOURCE_KEY,
    YAHOO_SOURCE_KEY,
    PriceRefreshService,
    build_market_data_adapter,
)
from china_outbound_analyzer.services.ingestion.yahoo_finance_adapter import (
    YahooFinanceMarketDataAdapter,
    normalize_yahoo_symbol,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "CHAR(36)"


class FailingMarketAdapter(MarketDataAdapter):
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        raise RuntimeError("primary provider failure")

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        return None

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        raise NotImplementedError

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        raise NotImplementedError


class StubMarketAdapter(MarketDataAdapter):
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        return [
            HistoricalPriceRecord(
                symbol=symbol,
                trading_date=end_date,
                open=12.0,
                high=12.8,
                low=11.9,
                close=12.5,
                adjusted_close=12.5,
                volume=123456,
                currency="CNY",
                source_name="Stub Source",
                source_url="https://stub.local/history",
            )
        ]

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        return LatestPriceSnapshotRecord(
            symbol=symbol,
            trading_date=date.today(),
            as_of=datetime.now(UTC),
            close=12.7,
            volume=222222,
            currency="CNY",
            source_name="Stub Source",
            source_url="https://stub.local/history",
        )

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        raise NotImplementedError

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        raise NotImplementedError


class SymbolFailingPriceRefreshService(PriceRefreshService):
    def __init__(self, *args, failing_symbol: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.failing_symbol = failing_symbol

    def _ingest_price_history(
        self,
        refresh_job_id,
        identifier_id,
        symbol: str,
        fetched,
        source_ids,
    ) -> int:
        if self.session is None:
            raise RuntimeError("Expected a database session for test ingestion.")

        source_id = source_ids[fetched.source_key]
        self.session.add(
            PriceBar(
                identifier_id=identifier_id,
                source_id=source_id,
                ingestion_run_id=None,
                interval=coerce_price_interval("1d"),
                trading_date=date(2026, 4, 14),
                open=Decimal("10.0"),
                high=Decimal("10.5"),
                low=Decimal("9.8"),
                close=Decimal("10.2"),
                adjusted_close=Decimal("10.2"),
                volume=12345,
                raw_payload={"symbol": symbol, "test_write": True},
            )
        )
        self.session.flush()

        if symbol == self.failing_symbol:
            raise RuntimeError("intentional symbol failure")

        return 1


def _build_chart_payload(start_date: date, end_date: date) -> dict:
    timestamps = [
        int(datetime.combine(start_date, datetime.min.time(), tzinfo=UTC).timestamp()),
        int(datetime.combine(end_date, datetime.min.time(), tzinfo=UTC).timestamp()),
    ]
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "CNY",
                        "exchangeName": "SHH",
                        "exchangeTimezoneName": "Asia/Shanghai",
                        "regularMarketPrice": 21.5,
                        "regularMarketTime": timestamps[-1],
                        "previousClose": 20.9,
                    },
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [20.2, 20.8],
                                "high": [20.7, 21.8],
                                "low": [20.0, 20.6],
                                "close": [20.5, 21.2],
                                "volume": [1000000, 1200000],
                            }
                        ],
                        "adjclose": [{"adjclose": [20.5, 21.2]}],
                    },
                }
            ],
            "error": None,
        }
    }


def _build_test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)()


def _seed_market_universe(session: Session, symbols: list[str]) -> dict[str, object]:
    market_source = DataSource(
        source_key=MOCK_SOURCE_KEY,
        display_name="Mock Market Data",
        kind=DataSourceKind.MARKET_DATA,
        is_mock=True,
        base_url="https://example.test/mock-market",
    )
    session.add(market_source)
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
            outbound_theme="Test universe for price refresh regression coverage.",
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

    return {"source": market_source, "identifiers": identifiers}


def test_coerce_price_interval_normalizes_names_and_values() -> None:
    assert coerce_price_interval(None) == PriceInterval.DAY_1
    assert coerce_price_interval("1d") == PriceInterval.DAY_1
    assert coerce_price_interval(" DAY_1 ") == PriceInterval.DAY_1
    assert coerce_price_interval(PriceInterval.DAY_1) == PriceInterval.DAY_1

    with pytest.raises(ValueError, match="Unsupported price interval"):
        coerce_price_interval("1h")


def test_price_bar_persists_database_interval_value() -> None:
    session = _build_test_session()
    seeded = _seed_market_universe(session, ["300750.SZ"])
    identifier = seeded["identifiers"]["300750.SZ"]
    source = seeded["source"]

    session.add(
        PriceBar(
            identifier_id=identifier.id,
            source_id=source.id,
            interval=PriceInterval.DAY_1,
            trading_date=date(2026, 4, 14),
            open=Decimal("200.0"),
            high=Decimal("205.0"),
            low=Decimal("198.0"),
            close=Decimal("203.0"),
            adjusted_close=Decimal("203.0"),
            volume=1000,
            raw_payload={"provider": "test"},
        )
    )
    session.commit()

    stored_interval = session.execute(text("select interval from price_bars")).scalar_one()
    persisted_bar = session.query(PriceBar).one()

    assert stored_interval == "1d"
    assert persisted_bar.interval == PriceInterval.DAY_1


async def test_price_refresh_service_rolls_back_failed_symbol_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_test_session()
    seeded = _seed_market_universe(session, ["FAIL.SZ", "PASS.HK"])
    identifiers = seeded["identifiers"]

    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.price_refresh.seed_universe",
        lambda _session: None,
    )

    service = SymbolFailingPriceRefreshService(
        session=session,
        settings=Settings(price_data_provider="mock"),
        primary_market_adapter=StubMarketAdapter(),
        fallback_market_adapter=StubMarketAdapter(),
        primary_source_key=MOCK_SOURCE_KEY,
        fallback_source_key=MOCK_SOURCE_KEY,
        failing_symbol="FAIL.SZ",
    )

    result = await service.run(lookback_days=10)

    persisted_bars = session.query(PriceBar).all()
    refresh_job_status = session.execute(
        text("select status from refresh_jobs where job_name = 'refresh-prices'")
    ).scalar_one()

    assert result["status"] == JobStatus.PARTIAL.value
    assert result["symbols"] == 1
    assert result["failed_symbols"] == 1
    assert len(persisted_bars) == 1
    assert persisted_bars[0].identifier_id == identifiers["PASS.HK"].id
    assert persisted_bars[0].interval == PriceInterval.DAY_1
    assert refresh_job_status == JobStatus.PARTIAL.value


async def test_build_market_data_adapter_respects_config() -> None:
    source_key, adapter = build_market_data_adapter(Settings(price_data_provider="mock"))
    assert source_key == MOCK_SOURCE_KEY
    assert adapter.__class__.__name__ == "MockMarketDataAdapter"

    source_key, adapter = build_market_data_adapter(Settings(price_data_provider="yahoo_finance"))
    assert source_key == YAHOO_SOURCE_KEY
    assert isinstance(adapter, YahooFinanceMarketDataAdapter)
    await adapter.aclose()


async def test_yahoo_adapter_normalizes_a_share_symbols_and_parses_history() -> None:
    start_date = date.today() - timedelta(days=2)
    end_date = date.today() - timedelta(days=1)
    payload = _build_chart_payload(start_date, end_date)
    seen_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = YahooFinanceMarketDataAdapter(client=client, max_retries=1)

    records = await adapter.fetch_price_history("600031.SH", start_date, end_date)
    snapshot = await adapter.fetch_latest_price_snapshot("600031.SH")

    assert normalize_yahoo_symbol("600031.SH") == "600031.SS"
    assert any("/600031.SS" in item for item in seen_urls)
    assert len(records) == 2
    assert records[0].symbol == "600031.SH"
    assert records[0].open == 20.2
    assert records[-1].close == 21.2
    assert records[-1].adjusted_close == 21.2
    assert records[-1].source_name == "Yahoo Finance"
    assert snapshot is not None
    assert snapshot.close == 21.5
    assert snapshot.currency == "CNY"
    await client.aclose()


async def test_price_refresh_service_falls_back_to_mock_when_primary_fails() -> None:
    service = PriceRefreshService(
        session=None,
        settings=Settings(price_data_provider="yahoo_finance"),
        primary_market_adapter=FailingMarketAdapter(),
        fallback_market_adapter=StubMarketAdapter(),
        primary_source_key=YAHOO_SOURCE_KEY,
    )

    result = await service._fetch_price_payload(
        symbol="300750.SZ",
        start_date=date.today() - timedelta(days=10),
        end_date=date.today(),
    )

    assert result.source_key == MOCK_SOURCE_KEY
    assert result.used_fallback is True
    assert result.records[-1].close == 12.5
    assert result.latest_snapshot is not None
    assert result.latest_snapshot.close == 12.7
