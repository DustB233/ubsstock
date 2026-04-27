from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class HistoricalPriceRecord:
    symbol: str
    trading_date: date
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    adjusted_close: float | None = None
    volume: int | None = None
    currency: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class LatestPriceSnapshotRecord:
    symbol: str
    trading_date: date
    as_of: datetime
    close: float
    volume: int | None = None
    currency: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ValuationRecord:
    symbol: str
    as_of_date: date
    currency: str | None = None
    pe_ttm: float | None = None
    pe_forward: float | None = None
    pb: float | None = None
    ps_ttm: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    source_name: str | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class FinancialMetricRecord:
    symbol: str
    period_type: str
    fiscal_year: int
    fiscal_period: str
    period_start: date
    period_end: date
    report_date: date
    currency: str
    revenue: float | None = None
    net_profit: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    debt_to_equity: float | None = None
    overseas_revenue_ratio: float | None = None
    revenue_growth_yoy: float | None = None
    net_profit_growth_yoy: float | None = None
    source_name: str | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class NewsRecord:
    symbol: str
    title: str
    url: str
    published_at: datetime
    summary: str | None = None
    external_id: str | None = None
    provider: str | None = None
    source_url: str | None = None
    language: str = "en"
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class AnnouncementRecord:
    symbol: str
    title: str
    url: str
    published_at: datetime
    category: str | None = None
    summary: str | None = None
    external_id: str | None = None
    provider: str | None = None
    exchange: str | None = None
    language: str = "zh"
    as_of_date: date | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any] | None = None


class MarketDataAdapter:
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> Sequence[HistoricalPriceRecord]:
        raise NotImplementedError

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord | None:
        raise NotImplementedError

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord | None:
        raise NotImplementedError

    async def fetch_financial_metrics(self, symbol: str) -> Sequence[FinancialMetricRecord]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class NewsAdapter:
    async def fetch_recent_news(self, symbol: str, limit: int = 20) -> Sequence[NewsRecord]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class AnnouncementAdapter:
    async def fetch_announcements(
        self,
        symbol: str,
        limit: int = 20,
        lookback_days: int | None = None,
    ) -> Sequence[AnnouncementRecord]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None
