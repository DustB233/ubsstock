from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from china_outbound_analyzer.core.config import Settings
from china_outbound_analyzer.core.database import Base
from china_outbound_analyzer.models.entities import (
    DataSource,
    FinancialMetric,
    RefreshJob,
    Stock,
    StockIdentifier,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import (
    DataSourceKind,
    FinancialPeriodType,
    IdentifierType,
    JobStatus,
)
from china_outbound_analyzer.services.adapters.base import (
    FinancialMetricRecord,
    HistoricalPriceRecord,
    LatestPriceSnapshotRecord,
    MarketDataAdapter,
    ValuationRecord,
)
from china_outbound_analyzer.services.ingestion.akshare_fundamentals_adapter import (
    AkshareFundamentalsAdapter,
)
from china_outbound_analyzer.services.ingestion.fundamentals_refresh import (
    AKSHARE_FUNDAMENTALS_SOURCE_KEY,
    MOCK_FUNDAMENTALS_SOURCE_KEY,
    FundamentalsRefreshService,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "CHAR(36)"


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def _call_key(function_name: str, **kwargs) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (function_name, tuple(sorted((key, str(value)) for key, value in kwargs.items())))


class StubAkshareFundamentalsAdapter(AkshareFundamentalsAdapter):
    def __init__(self, responses: dict[tuple[str, tuple[tuple[str, str], ...]], pd.DataFrame]) -> None:
        super().__init__(timeout_seconds=1, max_retries=0)
        self.responses = responses

    async def _call_akshare(self, function_name: str, **kwargs):
        return self.responses[_call_key(function_name, **kwargs)]


class StubFundamentalsProvider(MarketDataAdapter):
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        raise NotImplementedError

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        raise NotImplementedError

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        return ValuationRecord(
            symbol=symbol,
            as_of_date=date(2026, 4, 14),
            currency="CNY",
            market_cap=1_000_000_000,
            pe_ttm=15.5,
            pb=3.4,
            source_name="Real Fundamentals Provider",
            source_url="https://fundamentals.example.com",
            raw_payload={"provider": "real"},
        )

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        return [
            FinancialMetricRecord(
                symbol=symbol,
                period_type="ANNUAL",
                fiscal_year=2025,
                fiscal_period="FY",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
                report_date=date(2026, 3, 31),
                currency="CNY",
                revenue=400_000_000,
                net_profit=50_000_000,
                gross_margin=0.28,
                operating_margin=0.18,
                roe=0.21,
                roa=0.1,
                debt_to_equity=0.42,
                overseas_revenue_ratio=None,
                revenue_growth_yoy=0.16,
                net_profit_growth_yoy=0.22,
                source_name="Real Fundamentals Provider",
                source_url="https://fundamentals.example.com",
                raw_payload={"report_type": "annual"},
            ),
            FinancialMetricRecord(
                symbol=symbol,
                period_type="QUARTERLY",
                fiscal_year=2025,
                fiscal_period="Q3",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 9, 30),
                report_date=date(2025, 10, 30),
                currency="CNY",
                revenue=290_000_000,
                net_profit=33_000_000,
                gross_margin=0.27,
                operating_margin=0.17,
                roe=0.17,
                roa=0.08,
                debt_to_equity=0.44,
                overseas_revenue_ratio=None,
                revenue_growth_yoy=0.14,
                net_profit_growth_yoy=0.19,
                source_name="Real Fundamentals Provider",
                source_url="https://fundamentals.example.com",
                raw_payload={"report_type": "quarterly"},
            ),
        ]


class PartialRealFundamentalsProvider(MarketDataAdapter):
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        raise NotImplementedError

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        raise NotImplementedError

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        return ValuationRecord(
            symbol=symbol,
            as_of_date=date(2026, 4, 14),
            currency="CNY",
            market_cap=500_000_000,
            pe_ttm=12.0,
            pb=2.2,
            source_name="Partial Real Provider",
            source_url="https://fundamentals.example.com",
        )

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        raise RuntimeError("financial statements unavailable")


class DualListingFundamentalsProvider(MarketDataAdapter):
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        raise NotImplementedError

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        raise NotImplementedError

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        if symbol == "002594.SZ":
            return ValuationRecord(
                symbol=symbol,
                as_of_date=date(2026, 4, 14),
                currency="CNY",
                market_cap=900_000_000,
                pe_ttm=18.5,
                pb=3.2,
                source_name="A-share Fundamentals Feed",
                source_url="https://fundamentals.example.com/a-share",
            )
        if symbol == "1211.HK":
            return ValuationRecord(
                symbol=symbol,
                as_of_date=date(2026, 4, 14),
                currency="HKD",
                market_cap=1_100_000_000,
                pe_ttm=21.4,
                pb=4.6,
                source_name="HK Fundamentals Feed",
                source_url="https://fundamentals.example.com/hk",
            )
        return None

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        if symbol != "002594.SZ":
            return []
        return [
            FinancialMetricRecord(
                symbol=symbol,
                period_type="ANNUAL",
                fiscal_year=2025,
                fiscal_period="FY",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
                report_date=date(2026, 3, 31),
                currency="CNY",
                revenue=300_000_000,
                net_profit=40_000_000,
                gross_margin=0.22,
                operating_margin=0.11,
                roe=0.18,
                roa=0.08,
                debt_to_equity=0.55,
                overseas_revenue_ratio=None,
                revenue_growth_yoy=0.14,
                net_profit_growth_yoy=0.2,
                source_name="A-share Fundamentals Feed",
                source_url="https://fundamentals.example.com/a-share",
            )
        ]


class SymbolFailingFundamentalsProvider(MarketDataAdapter):
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        raise NotImplementedError

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        raise NotImplementedError

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        if symbol == "300750.SZ":
            raise RuntimeError("provider outage")
        return ValuationRecord(
            symbol=symbol,
            as_of_date=date(2026, 4, 14),
            currency="CNY",
            market_cap=650_000_000,
            pe_ttm=14.1,
            pb=2.9,
            source_name="Real Fundamentals Provider",
            source_url="https://fundamentals.example.com",
        )

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        if symbol == "300750.SZ":
            raise RuntimeError("provider outage")
        return [
            FinancialMetricRecord(
                symbol=symbol,
                period_type="ANNUAL",
                fiscal_year=2025,
                fiscal_period="FY",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
                report_date=date(2026, 3, 31),
                currency="CNY",
                revenue=180_000_000,
                net_profit=20_000_000,
                gross_margin=0.26,
                operating_margin=0.12,
                roe=0.16,
                roa=0.07,
                debt_to_equity=0.38,
                overseas_revenue_ratio=None,
                revenue_growth_yoy=0.09,
                net_profit_growth_yoy=0.11,
                source_name="Real Fundamentals Provider",
                source_url="https://fundamentals.example.com",
            )
        ]


async def test_akshare_adapter_normalizes_a_share_valuation_and_financials() -> None:
    adapter = StubAkshareFundamentalsAdapter(
        responses={
            _call_key("stock_individual_info_em", symbol="300750"): pd.DataFrame(
                [{"item": "总市值", "value": 1966152798420.9102}]
            ),
            _call_key(
                "stock_zh_valuation_baidu",
                symbol="300750",
                indicator="市盈率(TTM)",
                period="近一年",
            ): pd.DataFrame(
                [
                    {"date": date(2026, 4, 13), "value": 27.0},
                    {"date": date(2026, 4, 14), "value": 27.23},
                ]
            ),
            _call_key(
                "stock_zh_valuation_baidu",
                symbol="300750",
                indicator="市净率",
                period="近一年",
            ): pd.DataFrame(
                [
                    {"date": date(2026, 4, 13), "value": 5.78},
                    {"date": date(2026, 4, 14), "value": 5.83},
                ]
            ),
            _call_key(
                "stock_zh_valuation_baidu",
                symbol="300750",
                indicator="总市值",
                period="近一年",
            ): pd.DataFrame(
                [
                    {"date": date(2026, 4, 13), "value": 19494.48},
                    {"date": date(2026, 4, 14), "value": 19661.53},
                ]
            ),
            _call_key(
                "stock_financial_analysis_indicator_em",
                symbol="300750.SZ",
                indicator="按报告期",
            ): pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2025-12-31 00:00:00",
                        "NOTICE_DATE": "2026-03-10 00:00:00",
                        "CURRENCY": "CNY",
                        "TOTALOPERATEREVE": 423701834000.0,
                        "PARENTNETPROFIT": 72201282000.0,
                        "XSMLL": 26.272847570445,
                        "ROEJQ": 24.91,
                        "ZZCJLL": 8.7183575136,
                        "ZCFZL": 61.9392859503,
                        "TOTALOPERATEREVETZ": 17.040646607,
                        "PARENTNETPROFITTZ": 42.2834455835,
                        "REPORT_TYPE": "年报",
                        "REPORT_DATE_NAME": "2025年报",
                        "XSJLL": 18.1227228297,
                    }
                ]
            ),
        }
    )

    valuation = await adapter.fetch_valuation_snapshot("300750.SZ")
    financials = await adapter.fetch_financial_metrics("300750.SZ")

    assert valuation is not None
    assert valuation.market_cap == pytest.approx(1966152798420.9102)
    assert valuation.pe_ttm == pytest.approx(27.23)
    assert valuation.pb == pytest.approx(5.83)
    assert valuation.as_of_date == date(2026, 4, 14)
    assert valuation.currency == "CNY"
    assert valuation.source_name == "Baidu Valuation via AkShare"

    assert len(financials) == 1
    assert financials[0].period_type == "ANNUAL"
    assert financials[0].fiscal_period == "FY"
    assert financials[0].report_date == date(2026, 3, 10)
    assert financials[0].gross_margin == pytest.approx(0.262728, abs=1e-6)
    assert financials[0].roe == pytest.approx(0.2491, abs=1e-6)
    assert financials[0].roa == pytest.approx(0.087184, abs=1e-6)
    assert financials[0].debt_to_equity == pytest.approx(1.627382, abs=1e-6)
    assert financials[0].revenue_growth_yoy == pytest.approx(0.170406, abs=1e-6)


async def test_akshare_adapter_normalizes_hk_valuation_and_financials() -> None:
    adapter = StubAkshareFundamentalsAdapter(
        responses={
            _call_key("stock_hk_financial_indicator_em", symbol="01810"): pd.DataFrame(
                [
                    {
                        "总市值(港元)": 799739358864,
                        "市盈率": 17.345864519171,
                        "市净率": 2.713335650475,
                        "股息率TTM(%)": 0.5,
                    }
                ]
            ),
            _call_key(
                "stock_financial_hk_analysis_indicator_em",
                symbol="01810",
                indicator="报告期",
            ): pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2025-12-31 00:00:00",
                        "CURRENCY": "HKD",
                        "OPERATE_INCOME": 457286687000,
                        "OPERATE_INCOME_YOY": 24.9736953185,
                        "HOLDER_PROFIT": 41643389000,
                        "HOLDER_PROFIT_YOY": 76.0215031402,
                        "GROSS_PROFIT_RATIO": 22.263024464563,
                        "ROE_AVG": 18.306539053746,
                        "ROA": 9.139825865985,
                        "DEBT_ASSET_RATIO": 47.5840616149,
                    }
                ]
            ),
        }
    )

    valuation = await adapter.fetch_valuation_snapshot("1810.HK")
    financials = await adapter.fetch_financial_metrics("1810.HK")

    assert valuation is not None
    assert valuation.market_cap == pytest.approx(799739358864)
    assert valuation.pe_ttm == pytest.approx(17.345864519171)
    assert valuation.pb == pytest.approx(2.713335650475)
    assert valuation.dividend_yield == pytest.approx(0.005)
    assert valuation.currency == "HKD"

    assert len(financials) == 1
    assert financials[0].currency == "HKD"
    assert financials[0].gross_margin == pytest.approx(0.22263, abs=1e-6)
    assert financials[0].roe == pytest.approx(0.183065, abs=1e-6)
    assert financials[0].roa == pytest.approx(0.091398, abs=1e-6)
    assert financials[0].debt_to_equity == pytest.approx(0.907818, abs=1e-6)


async def test_fundamentals_refresh_service_persists_real_rows_and_derives_ps_ttm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session_factory = _session_factory()
    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.fundamentals_refresh.seed_universe",
        lambda session: {"stocks": 1},
    )

    with session_factory() as session:
        real_source = DataSource(
            source_key=AKSHARE_FUNDAMENTALS_SOURCE_KEY,
            display_name="AkShare Fundamentals",
            kind=DataSourceKind.FUNDAMENTALS,
            is_mock=False,
            base_url="https://www.akshare.xyz",
        )
        mock_source = DataSource(
            source_key=MOCK_FUNDAMENTALS_SOURCE_KEY,
            display_name="Mock Fundamentals",
            kind=DataSourceKind.FUNDAMENTALS,
            is_mock=True,
            base_url="https://demo.local/fundamentals",
        )
        stock = Stock(
            slug="catl",
            company_name="CATL",
            company_name_zh="宁德时代",
            sector="Battery Systems",
            outbound_theme="Global battery export leadership.",
            primary_exchange="SZSE",
            is_active=True,
        )
        session.add_all([real_source, mock_source, stock])
        session.flush()

        session.add(
            StockIdentifier(
                stock_id=stock.id,
                identifier_type=IdentifierType.A_SHARE,
                exchange_code="SZSE",
                ticker="300750",
                composite_symbol="300750.SZ",
                currency="CNY",
                is_primary=True,
            )
        )
        session.commit()

        service = FundamentalsRefreshService(
            session,
            settings=Settings(
                fundamentals_data_provider="akshare",
                scheduler_running_job_stale_after_seconds=3600,
            ),
            primary_market_adapter=StubFundamentalsProvider(),
            fallback_market_adapter=StubFundamentalsProvider(),
            primary_source_key=AKSHARE_FUNDAMENTALS_SOURCE_KEY,
        )

        result = await service.run()

        valuation = session.scalars(select(ValuationSnapshot)).one()
        metrics = session.scalars(
            select(FinancialMetric).order_by(FinancialMetric.report_date.desc())
        ).all()
        refresh_job = session.scalars(
            select(RefreshJob).where(RefreshJob.job_name == "refresh-fundamentals")
        ).one()

        assert result["status"] == "SUCCESS"
        assert result["valuation_snapshots"] == 1
        assert result["financial_metrics"] == 2
        assert valuation.pe_ttm == Decimal("15.5")
        assert valuation.currency == "CNY"
        assert valuation.ps_ttm == Decimal("2.5")
        assert valuation.raw_payload["derived_metrics"]["ps_ttm"]["formula"] == "market_cap / revenue"
        assert len(metrics) == 2
        assert metrics[0].period_type == FinancialPeriodType.ANNUAL
        assert metrics[0].operating_margin == Decimal("0.18")
        assert metrics[0].debt_to_equity == Decimal("0.42")
        assert refresh_job.status == JobStatus.SUCCESS

    engine.dispose()


async def test_fundamentals_refresh_keeps_partial_real_data_without_mock_backfill() -> None:
    service = FundamentalsRefreshService(
        session=None,
        settings=Settings(fundamentals_data_provider="akshare"),
        primary_market_adapter=PartialRealFundamentalsProvider(),
        fallback_market_adapter=StubFundamentalsProvider(),
        primary_source_key=AKSHARE_FUNDAMENTALS_SOURCE_KEY,
    )

    fetched = await service._fetch_fundamentals_payload("300750.SZ")

    assert fetched.source_key == AKSHARE_FUNDAMENTALS_SOURCE_KEY
    assert fetched.used_fallback is False
    assert fetched.valuation is not None
    assert fetched.financials == []


async def test_fundamentals_refresh_prefers_a_share_lookup_for_dual_listed_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session_factory = _session_factory()
    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.fundamentals_refresh.seed_universe",
        lambda session: {"stocks": 1},
    )

    with session_factory() as session:
        real_source = DataSource(
            source_key=AKSHARE_FUNDAMENTALS_SOURCE_KEY,
            display_name="AkShare Fundamentals",
            kind=DataSourceKind.FUNDAMENTALS,
            is_mock=False,
            base_url="https://www.akshare.xyz",
        )
        mock_source = DataSource(
            source_key=MOCK_FUNDAMENTALS_SOURCE_KEY,
            display_name="Mock Fundamentals",
            kind=DataSourceKind.FUNDAMENTALS,
            is_mock=True,
            base_url="https://demo.local/fundamentals",
        )
        stock = Stock(
            slug="byd",
            company_name="BYD",
            company_name_zh="比亚迪",
            sector="EV + Energy Storage",
            outbound_theme="China auto export scale.",
            primary_exchange="HKEX",
            is_active=True,
        )
        session.add_all([real_source, mock_source, stock])
        session.flush()
        session.add_all(
            [
                StockIdentifier(
                    stock_id=stock.id,
                    identifier_type=IdentifierType.H_SHARE,
                    exchange_code="HKEX",
                    ticker="1211",
                    composite_symbol="1211.HK",
                    currency="HKD",
                    is_primary=True,
                ),
                StockIdentifier(
                    stock_id=stock.id,
                    identifier_type=IdentifierType.A_SHARE,
                    exchange_code="SZSE",
                    ticker="002594",
                    composite_symbol="002594.SZ",
                    currency="CNY",
                    is_primary=False,
                ),
            ]
        )
        session.commit()

        service = FundamentalsRefreshService(
            session,
            settings=Settings(
                fundamentals_data_provider="akshare",
                scheduler_running_job_stale_after_seconds=3600,
            ),
            primary_market_adapter=DualListingFundamentalsProvider(),
            fallback_market_adapter=StubFundamentalsProvider(),
            primary_source_key=AKSHARE_FUNDAMENTALS_SOURCE_KEY,
        )

        result = await service.run()

        valuation = session.scalars(select(ValuationSnapshot)).one()
        metric = session.scalars(select(FinancialMetric)).one()

        assert result["status"] == "SUCCESS"
        assert valuation.currency == "CNY"
        assert valuation.raw_payload["lookup_symbol"] == "002594.SZ"
        assert valuation.raw_payload["symbol"] == "1211.HK"
        assert metric.currency == "CNY"
        assert metric.raw_payload["lookup_symbol"] == "002594.SZ"

    engine.dispose()


async def test_fundamentals_refresh_rolls_back_failed_symbol_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session_factory = _session_factory()
    monkeypatch.setattr(
        "china_outbound_analyzer.services.ingestion.fundamentals_refresh.seed_universe",
        lambda session: {"stocks": 2},
    )

    with session_factory() as session:
        session.add_all(
            [
                DataSource(
                    source_key=AKSHARE_FUNDAMENTALS_SOURCE_KEY,
                    display_name="AkShare Fundamentals",
                    kind=DataSourceKind.FUNDAMENTALS,
                    is_mock=False,
                    base_url="https://www.akshare.xyz",
                ),
                DataSource(
                    source_key=MOCK_FUNDAMENTALS_SOURCE_KEY,
                    display_name="Mock Fundamentals",
                    kind=DataSourceKind.FUNDAMENTALS,
                    is_mock=True,
                    base_url="https://demo.local/fundamentals",
                ),
            ]
        )
        session.flush()
        first = Stock(
            slug="catl",
            company_name="CATL",
            company_name_zh="宁德时代",
            sector="Battery",
            outbound_theme="Battery export leadership.",
            primary_exchange="SZSE",
            is_active=True,
        )
        second = Stock(
            slug="siyuan-electric",
            company_name="Siyuan Electric",
            company_name_zh="思源电气",
            sector="Grid Equipment",
            outbound_theme="International grid orders.",
            primary_exchange="SZSE",
            is_active=True,
        )
        session.add_all([first, second])
        session.flush()
        session.add_all(
            [
                StockIdentifier(
                    stock_id=first.id,
                    identifier_type=IdentifierType.A_SHARE,
                    exchange_code="SZSE",
                    ticker="300750",
                    composite_symbol="300750.SZ",
                    currency="CNY",
                    is_primary=True,
                ),
                StockIdentifier(
                    stock_id=second.id,
                    identifier_type=IdentifierType.A_SHARE,
                    exchange_code="SZSE",
                    ticker="002028",
                    composite_symbol="002028.SZ",
                    currency="CNY",
                    is_primary=True,
                ),
            ]
        )
        session.commit()

        service = FundamentalsRefreshService(
            session,
            settings=Settings(
                fundamentals_data_provider="akshare",
                scheduler_running_job_stale_after_seconds=3600,
            ),
            primary_market_adapter=SymbolFailingFundamentalsProvider(),
            fallback_market_adapter=SymbolFailingFundamentalsProvider(),
            primary_source_key=AKSHARE_FUNDAMENTALS_SOURCE_KEY,
        )

        result = await service.run()

        valuations = session.scalars(select(ValuationSnapshot)).all()
        metrics = session.scalars(select(FinancialMetric)).all()
        refresh_job = session.scalars(
            select(RefreshJob).where(RefreshJob.job_name == "refresh-fundamentals")
        ).one()

        assert result["status"] == "PARTIAL"
        assert result["symbols"] == 1
        assert result["failed_symbols"] == 1
        assert len(valuations) == 1
        assert len(metrics) == 1
        assert valuations[0].raw_payload["symbol"] == "002028.SZ"
        assert refresh_job.status == JobStatus.PARTIAL

    engine.dispose()
