import hashlib
import random
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from china_outbound_analyzer.services.adapters.base import (
    AnnouncementAdapter,
    AnnouncementRecord,
    FinancialMetricRecord,
    HistoricalPriceRecord,
    LatestPriceSnapshotRecord,
    MarketDataAdapter,
    NewsAdapter,
    NewsRecord,
    ValuationRecord,
)


def _stable_rng(seed_text: str) -> random.Random:
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def _currency_for_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized.endswith(".HK"):
        return "HKD"
    if normalized.endswith(".SZ") or normalized.endswith(".SH"):
        return "CNY"
    return "USD"


class MockMarketDataAdapter(MarketDataAdapter):
    async def fetch_price_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[HistoricalPriceRecord]:
        rng = _stable_rng(f"price:{symbol}")
        days = pd.bdate_range(start=start_date, end=end_date)
        base_price = 18 + (rng.randint(0, 220) / 5)
        trend = rng.uniform(-0.03, 0.08)
        volatility = rng.uniform(0.008, 0.028)

        records: list[HistoricalPriceRecord] = []
        price = base_price

        for index, trading_day in enumerate(days):
            opening_price = max(2.0, price * (1 + rng.uniform(-0.012, 0.012)))
            cycle = 0.02 * ((index % 21) / 21)
            shock = rng.uniform(-volatility, volatility)
            price = max(2.0, price * (1 + trend / len(days) + cycle + shock))
            high = max(opening_price, price) * (1 + rng.uniform(0.001, 0.014))
            low = min(opening_price, price) * (1 - rng.uniform(0.001, 0.014))
            volume = int(rng.uniform(1_500_000, 12_000_000))
            records.append(
                HistoricalPriceRecord(
                    symbol=symbol,
                    trading_date=trading_day.date(),
                    open=round(opening_price, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(price, 4),
                    adjusted_close=round(price, 4),
                    volume=volume,
                    source_name="Mock Market Data",
                    source_url="https://demo.local/market-data",
                    raw_payload={"symbol": symbol, "mock": True},
                )
            )

        return records

    async def fetch_latest_price_snapshot(self, symbol: str) -> LatestPriceSnapshotRecord:
        records = await self.fetch_price_history(
            symbol=symbol,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today(),
        )
        latest = records[-1]
        return LatestPriceSnapshotRecord(
            symbol=symbol,
            trading_date=latest.trading_date,
            as_of=datetime.now(UTC),
            close=latest.close,
            volume=latest.volume,
            currency=latest.currency,
            source_name=latest.source_name,
            source_url=latest.source_url,
            raw_payload={"symbol": symbol, "mock": True},
        )

    async def fetch_valuation_snapshot(self, symbol: str) -> ValuationRecord:
        rng = _stable_rng(f"valuation:{symbol}")
        return ValuationRecord(
            symbol=symbol,
            as_of_date=date.today(),
            currency=_currency_for_symbol(symbol),
            market_cap=round(rng.uniform(80, 1200), 2),
            pe_ttm=round(rng.uniform(10, 42), 2),
            pe_forward=round(rng.uniform(8, 35), 2),
            pb=round(rng.uniform(1.4, 8.5), 2),
            ps_ttm=round(rng.uniform(0.9, 12), 2),
            enterprise_value=round(rng.uniform(90, 1400), 2),
            ev_ebitda=round(rng.uniform(6, 28), 2),
            dividend_yield=round(rng.uniform(0, 0.04), 4),
            source_name="Mock Fundamentals",
            source_url="https://demo.local/fundamentals",
            raw_payload={"symbol": symbol, "mock": True},
        )

    async def fetch_financial_metrics(self, symbol: str) -> list[FinancialMetricRecord]:
        rng = _stable_rng(f"financials:{symbol}")
        today = date.today()
        current_year = today.year
        current_quarter = ((today.month - 1) // 3) + 1
        records: list[FinancialMetricRecord] = []
        revenue_base = rng.uniform(8_000, 120_000)
        margin_base = rng.uniform(0.18, 0.48)
        roe_base = rng.uniform(0.08, 0.28)

        for offset in range(8):
            quarter_number = current_quarter - offset
            fiscal_year = current_year
            while quarter_number <= 0:
                quarter_number += 4
                fiscal_year -= 1

            quarter_start_month = (quarter_number - 1) * 3 + 1
            period_start = date(fiscal_year, quarter_start_month, 1)
            period_end = (pd.Timestamp(period_start) + pd.offsets.QuarterEnd()).date()
            growth_factor = 1 + rng.uniform(-0.08, 0.16) - (offset * 0.01)
            revenue = revenue_base * growth_factor
            net_margin = margin_base * rng.uniform(0.32, 0.5)
            net_profit = revenue * net_margin

            records.append(
                FinancialMetricRecord(
                    symbol=symbol,
                    period_type="QUARTERLY",
                    fiscal_year=fiscal_year,
                    fiscal_period=f"Q{quarter_number}",
                    period_start=period_start,
                    period_end=period_end,
                    report_date=period_end + timedelta(days=30),
                    currency=_currency_for_symbol(symbol),
                    revenue=round(revenue, 2),
                    net_profit=round(net_profit, 2),
                    gross_margin=round(margin_base + rng.uniform(-0.03, 0.03), 4),
                    operating_margin=round(margin_base * rng.uniform(0.35, 0.55), 4),
                    roe=round(roe_base + rng.uniform(-0.02, 0.03), 4),
                    roa=round(roe_base * rng.uniform(0.45, 0.7), 4),
                    debt_to_equity=round(rng.uniform(0.2, 1.8), 4),
                    overseas_revenue_ratio=round(rng.uniform(0.05, 0.65), 4),
                    revenue_growth_yoy=round(rng.uniform(-0.12, 0.35), 4),
                    net_profit_growth_yoy=round(rng.uniform(-0.18, 0.42), 4),
                    source_name="Mock Fundamentals",
                    source_url="https://demo.local/fundamentals",
                    raw_payload={"symbol": symbol, "mock": True},
                )
            )

        return records


class MockNewsAdapter(NewsAdapter):
    async def fetch_recent_news(self, symbol: str, limit: int = 20) -> list[NewsRecord]:
        rng = _stable_rng(f"news:{symbol}")
        today = datetime.now(UTC)
        themes = [
            ("overseas demand strengthens", "positive"),
            ("margin outlook stabilizes", "positive"),
            ("distribution expansion accelerates", "positive"),
            ("regulatory update creates caution", "negative"),
            ("export momentum improves", "positive"),
            ("industry competition intensifies", "negative"),
        ]

        items: list[NewsRecord] = []
        for index in range(limit):
            published_at = today - timedelta(hours=index * rng.randint(8, 20))
            theme, tone = themes[index % len(themes)]
            items.append(
                NewsRecord(
                    symbol=symbol,
                    title=f"{symbol} update: {theme} in focus",
                    url=f"https://demo.local/news/{symbol.lower()}/{index + 1}",
                    published_at=published_at,
                    summary=(
                        f"Mock {tone} news item for {symbol} covering {theme}, designed to "
                        "feed the Phase 3 clustering and sentiment pipeline."
                    ),
                    external_id=f"{symbol.lower()}-news-{index + 1}",
                    provider="Mock Wire",
                    source_url="https://demo.local/news",
                    language="en",
                    raw_payload={"symbol": symbol, "mock": True, "tone": tone},
                )
            )

        return items


class MockAnnouncementAdapter(AnnouncementAdapter):
    async def fetch_announcements(
        self,
        symbol: str,
        limit: int = 20,
        lookback_days: int | None = None,
    ) -> list[AnnouncementRecord]:
        rng = _stable_rng(f"announcements:{symbol}")
        today = datetime.now(UTC)
        categories = ["Results", "Investor Update", "Capacity", "International Expansion"]

        records: list[AnnouncementRecord] = []
        for index in range(limit):
            category = categories[index % len(categories)]
            published_at = today - timedelta(days=index * rng.randint(9, 24))
            records.append(
                AnnouncementRecord(
                    symbol=symbol,
                    title=f"{symbol} mock announcement: {category}",
                    url=f"https://demo.local/announcements/{symbol.lower()}/{index + 1}",
                    published_at=published_at,
                    category=category,
                    summary=(
                        f"Mock announcement for {symbol} in category {category}. "
                        "This stands in for exchange filings until a live adapter is connected."
                    ),
                    external_id=f"{symbol.lower()}-announcement-{index + 1}",
                    provider="Mock Announcements",
                    exchange=symbol.split(".")[-1] if "." in symbol else None,
                    language="en",
                    as_of_date=published_at.date(),
                    source_url="https://demo.local/announcements",
                    raw_payload={"symbol": symbol, "mock": True, "category": category},
                )
            )

        return records
