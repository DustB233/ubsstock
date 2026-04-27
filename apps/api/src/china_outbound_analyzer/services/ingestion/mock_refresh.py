from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from china_outbound_analyzer.models.entities import (
    Announcement,
    FinancialMetric,
    IngestionRun,
    NewsItem,
    PriceBar,
    RefreshJob,
    Stock,
    StockIdentifier,
    StockNewsMention,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import (
    FinancialPeriodType,
    JobStatus,
    PriceInterval,
    RefreshJobType,
    coerce_price_interval,
)
from china_outbound_analyzer.services.ingestion.mock_adapters import (
    MockAnnouncementAdapter,
    MockMarketDataAdapter,
    MockNewsAdapter,
)
from china_outbound_analyzer.services.ingestion.seeder import get_source_id_by_key, seed_universe


class MockRefreshService:
    def __init__(self, session: Session):
        self.session = session
        self.market_adapter = MockMarketDataAdapter()
        self.news_adapter = MockNewsAdapter()
        self.announcement_adapter = MockAnnouncementAdapter()

    async def run(self, lookback_days: int = 400) -> dict[str, int | str]:
        seed_universe(self.session)

        refresh_job = RefreshJob(
            job_name="refresh-mock",
            job_type=RefreshJobType.DAILY_REFRESH,
            status=JobStatus.RUNNING,
            scheduled_for=datetime.now(UTC),
            started_at=datetime.now(UTC),
            trigger_source="cli:mock-refresh",
            stage_status={"phase": "mock_ingestion"},
        )
        self.session.add(refresh_job)
        self.session.flush()

        source_ids = {
            "market": get_source_id_by_key(self.session, "mock_market_data"),
            "fundamentals": get_source_id_by_key(self.session, "mock_fundamentals"),
            "news": get_source_id_by_key(self.session, "mock_news"),
            "announcements": get_source_id_by_key(self.session, "mock_announcements"),
        }

        counts = {
            "price_bars": 0,
            "valuations": 0,
            "financial_metrics": 0,
            "news_items": 0,
            "announcements": 0,
        }

        universe_rows = self.session.execute(
            select(
                Stock.id,
                Stock.slug,
                Stock.company_name,
                StockIdentifier.id,
                StockIdentifier.composite_symbol,
            )
            .join(StockIdentifier, StockIdentifier.stock_id == Stock.id)
            .where(StockIdentifier.is_primary.is_(True))
        ).all()

        for stock_id, _slug, _company_name, identifier_id, primary_symbol in universe_rows:
            counts["price_bars"] += await self._ingest_price_history(
                refresh_job.id,
                source_ids["market"],
                identifier_id,
                primary_symbol,
                lookback_days,
            )
            counts["valuations"] += await self._ingest_valuation(
                refresh_job.id,
                source_ids["fundamentals"],
                stock_id,
                primary_symbol,
            )
            counts["financial_metrics"] += await self._ingest_financials(
                refresh_job.id,
                source_ids["fundamentals"],
                stock_id,
                primary_symbol,
            )
            counts["news_items"] += await self._ingest_news(
                source_ids["news"],
                stock_id,
                primary_symbol,
            )
            counts["announcements"] += await self._ingest_announcements(
                source_ids["announcements"],
                stock_id,
                primary_symbol,
            )

        refresh_job.status = JobStatus.SUCCESS
        refresh_job.completed_at = datetime.now(UTC)
        refresh_job.stage_status = counts
        self.session.commit()

        return {"job_id": str(refresh_job.id), **counts}

    async def _ingest_price_history(
        self,
        refresh_job_id,
        source_id,
        identifier_id,
        symbol: str,
        lookback_days: int,
    ) -> int:
        start_date = date.today() - timedelta(days=lookback_days)
        end_date = date.today()

        ingestion_run = self._new_ingestion_run(refresh_job_id, source_id, "price_bars")
        records = await self.market_adapter.fetch_price_history(symbol, start_date, end_date)
        ingestion_run.rows_read = len(records)

        for record in records:
            statement = (
                insert(PriceBar)
                .values(
                    identifier_id=identifier_id,
                    source_id=source_id,
                    ingestion_run_id=ingestion_run.id,
                    interval=coerce_price_interval(PriceInterval.DAY_1),
                    trading_date=record.trading_date,
                    open=Decimal(str(record.open)) if record.open is not None else None,
                    high=Decimal(str(record.high)) if record.high is not None else None,
                    low=Decimal(str(record.low)) if record.low is not None else None,
                    close=Decimal(str(record.close)),
                    adjusted_close=Decimal(str(record.adjusted_close or record.close)),
                    volume=record.volume,
                    raw_payload=record.raw_payload or {"symbol": symbol, "mock": True},
                )
                .on_conflict_do_update(
                    index_elements=[
                        PriceBar.identifier_id,
                        PriceBar.source_id,
                        PriceBar.interval,
                        PriceBar.trading_date,
                    ],
                    set_={
                        "open": Decimal(str(record.open)) if record.open is not None else None,
                        "high": Decimal(str(record.high)) if record.high is not None else None,
                        "low": Decimal(str(record.low)) if record.low is not None else None,
                        "close": Decimal(str(record.close)),
                        "adjusted_close": Decimal(str(record.adjusted_close or record.close)),
                        "volume": record.volume,
                        "raw_payload": record.raw_payload or {"symbol": symbol, "mock": True},
                    },
                )
            )
            self.session.execute(statement)

        ingestion_run.rows_written = len(records)
        ingestion_run.status = JobStatus.SUCCESS
        self.session.flush()
        return len(records)

    async def _ingest_valuation(self, refresh_job_id, source_id, stock_id, symbol: str) -> int:
        ingestion_run = self._new_ingestion_run(refresh_job_id, source_id, "valuation_snapshots")
        record = await self.market_adapter.fetch_valuation_snapshot(symbol)

        statement = (
            insert(ValuationSnapshot)
            .values(
                stock_id=stock_id,
                source_id=source_id,
                ingestion_run_id=ingestion_run.id,
                as_of_date=record.as_of_date,
                currency=record.currency,
                market_cap=Decimal(str(record.market_cap))
                if record.market_cap is not None
                else None,
                pe_ttm=Decimal(str(record.pe_ttm)) if record.pe_ttm is not None else None,
                pe_forward=Decimal(str(record.pe_forward))
                if record.pe_forward is not None
                else None,
                pb=Decimal(str(record.pb)) if record.pb is not None else None,
                ps_ttm=Decimal(str(record.ps_ttm)) if record.ps_ttm is not None else None,
                enterprise_value=Decimal(str(record.enterprise_value))
                if record.enterprise_value is not None
                else None,
                ev_ebitda=Decimal(str(record.ev_ebitda)) if record.ev_ebitda is not None else None,
                dividend_yield=Decimal(str(record.dividend_yield))
                if record.dividend_yield is not None
                else None,
                raw_payload={"symbol": symbol, "mock": True},
            )
            .on_conflict_do_update(
                index_elements=[
                    ValuationSnapshot.stock_id,
                    ValuationSnapshot.source_id,
                    ValuationSnapshot.as_of_date,
                ],
                set_={
                    "currency": record.currency,
                    "market_cap": Decimal(str(record.market_cap))
                    if record.market_cap is not None
                    else None,
                    "pe_ttm": Decimal(str(record.pe_ttm)) if record.pe_ttm is not None else None,
                    "pe_forward": Decimal(str(record.pe_forward))
                    if record.pe_forward is not None
                    else None,
                    "pb": Decimal(str(record.pb)) if record.pb is not None else None,
                    "ps_ttm": Decimal(str(record.ps_ttm)) if record.ps_ttm is not None else None,
                    "enterprise_value": Decimal(str(record.enterprise_value))
                    if record.enterprise_value is not None
                    else None,
                    "ev_ebitda": Decimal(str(record.ev_ebitda))
                    if record.ev_ebitda is not None
                    else None,
                    "dividend_yield": Decimal(str(record.dividend_yield))
                    if record.dividend_yield is not None
                    else None,
                    "raw_payload": {"symbol": symbol, "mock": True},
                },
            )
        )
        self.session.execute(statement)
        ingestion_run.rows_read = 1
        ingestion_run.rows_written = 1
        ingestion_run.status = JobStatus.SUCCESS
        self.session.flush()
        return 1

    async def _ingest_financials(self, refresh_job_id, source_id, stock_id, symbol: str) -> int:
        ingestion_run = self._new_ingestion_run(refresh_job_id, source_id, "financial_metrics")
        records = await self.market_adapter.fetch_financial_metrics(symbol)
        ingestion_run.rows_read = len(records)

        for record in records:
            statement = (
                insert(FinancialMetric)
                .values(
                    stock_id=stock_id,
                    source_id=source_id,
                    ingestion_run_id=ingestion_run.id,
                    period_type=FinancialPeriodType(record.period_type),
                    fiscal_year=record.fiscal_year,
                    fiscal_period=record.fiscal_period,
                    period_start=record.period_start,
                    period_end=record.period_end,
                    report_date=record.report_date,
                    currency=record.currency,
                    revenue=Decimal(str(record.revenue)) if record.revenue is not None else None,
                    net_profit=Decimal(str(record.net_profit))
                    if record.net_profit is not None
                    else None,
                    gross_margin=Decimal(str(record.gross_margin))
                    if record.gross_margin is not None
                    else None,
                    operating_margin=Decimal(str(record.operating_margin))
                    if record.operating_margin is not None
                    else None,
                    roe=Decimal(str(record.roe)) if record.roe is not None else None,
                    roa=Decimal(str(record.roa)) if record.roa is not None else None,
                    debt_to_equity=Decimal(str(record.debt_to_equity))
                    if record.debt_to_equity is not None
                    else None,
                    overseas_revenue_ratio=Decimal(str(record.overseas_revenue_ratio))
                    if record.overseas_revenue_ratio is not None
                    else None,
                    revenue_growth_yoy=Decimal(str(record.revenue_growth_yoy))
                    if record.revenue_growth_yoy is not None
                    else None,
                    net_profit_growth_yoy=Decimal(str(record.net_profit_growth_yoy))
                    if record.net_profit_growth_yoy is not None
                    else None,
                    raw_payload={"symbol": symbol, "mock": True},
                )
                .on_conflict_do_update(
                    index_elements=[
                        FinancialMetric.stock_id,
                        FinancialMetric.source_id,
                        FinancialMetric.period_type,
                        FinancialMetric.fiscal_year,
                        FinancialMetric.fiscal_period,
                    ],
                    set_={
                        "period_start": record.period_start,
                        "period_end": record.period_end,
                        "report_date": record.report_date,
                        "currency": record.currency,
                        "revenue": Decimal(str(record.revenue))
                        if record.revenue is not None
                        else None,
                        "net_profit": Decimal(str(record.net_profit))
                        if record.net_profit is not None
                        else None,
                        "gross_margin": Decimal(str(record.gross_margin))
                        if record.gross_margin is not None
                        else None,
                        "operating_margin": Decimal(str(record.operating_margin))
                        if record.operating_margin is not None
                        else None,
                        "roe": Decimal(str(record.roe)) if record.roe is not None else None,
                        "roa": Decimal(str(record.roa)) if record.roa is not None else None,
                        "debt_to_equity": Decimal(str(record.debt_to_equity))
                        if record.debt_to_equity is not None
                        else None,
                        "overseas_revenue_ratio": Decimal(str(record.overseas_revenue_ratio))
                        if record.overseas_revenue_ratio is not None
                        else None,
                        "revenue_growth_yoy": Decimal(str(record.revenue_growth_yoy))
                        if record.revenue_growth_yoy is not None
                        else None,
                        "net_profit_growth_yoy": Decimal(str(record.net_profit_growth_yoy))
                        if record.net_profit_growth_yoy is not None
                        else None,
                        "raw_payload": {"symbol": symbol, "mock": True},
                    },
                )
            )
            self.session.execute(statement)

        ingestion_run.rows_written = len(records)
        ingestion_run.status = JobStatus.SUCCESS
        self.session.flush()
        return len(records)

    async def _ingest_news(self, source_id, stock_id, symbol: str) -> int:
        records = await self.news_adapter.fetch_recent_news(symbol, limit=6)

        for index, record in enumerate(records, start=1):
            news_item_id = self.session.execute(
                insert(NewsItem)
                .values(
                    source_id=source_id,
                    external_id=record.external_id or f"{symbol.lower()}-news-{index}",
                    provider=record.provider or "Mock Wire",
                    title=record.title,
                    url=record.url,
                    summary=record.summary,
                    language=record.language or "en",
                    published_at=record.published_at,
                    raw_payload=record.raw_payload or {"symbol": symbol, "mock": True},
                )
                .on_conflict_do_update(
                    index_elements=[NewsItem.source_id, NewsItem.external_id],
                    set_={
                        "provider": record.provider or "Mock Wire",
                        "title": record.title,
                        "url": record.url,
                        "summary": record.summary,
                        "language": record.language or "en",
                        "published_at": record.published_at,
                        "raw_payload": record.raw_payload or {"symbol": symbol, "mock": True},
                    },
                )
                .returning(NewsItem.id)
            ).scalar_one()

            self.session.execute(
                insert(StockNewsMention)
                .values(
                    stock_id=stock_id,
                    news_item_id=news_item_id,
                    relevance_score=Decimal("0.85"),
                )
                .on_conflict_do_update(
                    index_elements=[StockNewsMention.stock_id, StockNewsMention.news_item_id],
                    set_={"relevance_score": Decimal("0.85")},
                )
            )

        self.session.flush()
        return len(records)

    async def _ingest_announcements(self, source_id, stock_id, symbol: str) -> int:
        records = await self.announcement_adapter.fetch_announcements(symbol, limit=4)

        for index, record in enumerate(records, start=1):
            self.session.execute(
                insert(Announcement)
                .values(
                    stock_id=stock_id,
                    source_id=source_id,
                    external_id=record.external_id or f"{symbol.lower()}-announcement-{index}",
                    title=record.title,
                    url=record.url,
                    provider=record.provider,
                    exchange_code=record.exchange,
                    category=record.category,
                    language=record.language or "zh",
                    published_at=record.published_at,
                    as_of_date=record.as_of_date or record.published_at.date(),
                    summary=record.summary,
                    raw_payload={
                        "symbol": symbol,
                        "source_name": record.provider,
                        "source_url": record.source_url,
                        "exchange_code": record.exchange,
                        "language": record.language,
                        "mock": True,
                        **(record.raw_payload or {}),
                    },
                )
                .on_conflict_do_update(
                    index_elements=[
                        Announcement.stock_id,
                        Announcement.source_id,
                        Announcement.external_id,
                    ],
                    set_={
                        "title": record.title,
                        "url": record.url,
                        "provider": record.provider,
                        "exchange_code": record.exchange,
                        "category": record.category,
                        "language": record.language or "zh",
                        "published_at": record.published_at,
                        "as_of_date": record.as_of_date or record.published_at.date(),
                        "summary": record.summary,
                        "raw_payload": {
                            "symbol": symbol,
                            "source_name": record.provider,
                            "source_url": record.source_url,
                            "exchange_code": record.exchange,
                            "language": record.language,
                            "mock": True,
                            **(record.raw_payload or {}),
                        },
                    },
                )
            )

        self.session.flush()
        return len(records)

    def _new_ingestion_run(self, refresh_job_id, source_id, dataset_name: str) -> IngestionRun:
        ingestion_run = IngestionRun(
            refresh_job_id=refresh_job_id,
            source_id=source_id,
            dataset_name=dataset_name,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self.session.add(ingestion_run)
        self.session.flush()
        return ingestion_run
