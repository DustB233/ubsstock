from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from china_outbound_analyzer.api.v1.endpoints import admin as admin_endpoint
from china_outbound_analyzer.api.v1.endpoints import compare as compare_endpoint
from china_outbound_analyzer.api.v1.endpoints import recommendations as recommendations_endpoint
from china_outbound_analyzer.api.v1.endpoints import stocks as stocks_endpoint
from china_outbound_analyzer.core.database import Base, DatabaseUnavailableError
from china_outbound_analyzer.main import app
from china_outbound_analyzer.models.entities import (
    AIArtifact,
    Announcement,
    DataSource,
    FinancialMetric,
    NewsItem,
    PriceBar,
    RecommendationItem,
    RecommendationRun,
    RefreshJob,
    ScoringRun,
    Stock,
    StockIdentifier,
    StockNewsMention,
    StockScore,
    ValuationSnapshot,
)
from china_outbound_analyzer.models.enums import (
    AIArtifactType,
    DataSourceKind,
    FinancialPeriodType,
    IdentifierType,
    JobStatus,
    PriceInterval,
    RecommendationSide,
    RefreshJobType,
)
from china_outbound_analyzer.services.ai.competition_artifacts import build_stock_analysis_response
from china_outbound_analyzer.services.ingestion.mock_adapters import (
    MockAnnouncementAdapter,
    MockMarketDataAdapter,
    MockNewsAdapter,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "CHAR(36)"


client = TestClient(app)


def _seed_live_database(session: Session) -> None:
    created_at = datetime(2026, 4, 14, 9, 30, tzinfo=UTC)

    market_source = DataSource(
        source_key="yahoo_finance",
        display_name="Yahoo Finance",
        kind=DataSourceKind.MARKET_DATA,
        is_mock=False,
        base_url="https://finance.yahoo.com",
        created_at=created_at,
        updated_at=created_at,
    )
    news_source = DataSource(
        source_key="google_news_rss",
        display_name="Google News RSS",
        kind=DataSourceKind.NEWS,
        is_mock=False,
        base_url="https://news.google.com",
        created_at=created_at,
        updated_at=created_at,
    )
    fundamentals_source = DataSource(
        source_key="manual_fundamentals",
        display_name="Manual Fundamentals Feed",
        kind=DataSourceKind.FUNDAMENTALS,
        is_mock=False,
        base_url="https://data.example.com/fundamentals",
        created_at=created_at,
        updated_at=created_at,
    )
    announcements_source = DataSource(
        source_key="cninfo_announcements",
        display_name="CNInfo Disclosures",
        kind=DataSourceKind.ANNOUNCEMENTS,
        is_mock=False,
        base_url="https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        created_at=created_at,
        updated_at=created_at,
    )
    session.add_all([market_source, news_source, fundamentals_source, announcements_source])
    session.flush()

    catl = Stock(
        slug="catl",
        company_name="CATL",
        company_name_zh="宁德时代",
        sector="Battery Systems",
        outbound_theme="Global battery export leadership with European and Southeast Asian expansion.",
        primary_exchange="SZSE",
        is_active=True,
        created_at=created_at,
        updated_at=created_at,
    )
    byd = Stock(
        slug="byd",
        company_name="BYD",
        company_name_zh="比亚迪",
        sector="EV + Energy Storage",
        outbound_theme="Integrated EV export platform with global manufacturing footprint.",
        primary_exchange="HKEX",
        is_active=True,
        created_at=created_at,
        updated_at=created_at,
    )
    xiaomi = Stock(
        slug="xiaomi",
        company_name="Xiaomi",
        company_name_zh="小米集团",
        sector="Consumer Electronics",
        outbound_theme="Global consumer hardware brand pushing further into overseas autos and devices.",
        primary_exchange="HKEX",
        is_active=True,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add_all([catl, byd, xiaomi])
    session.flush()

    catl_primary = StockIdentifier(
        stock_id=catl.id,
        identifier_type=IdentifierType.A_SHARE,
        exchange_code="SZSE",
        ticker="300750",
        composite_symbol="300750.SZ",
        currency="CNY",
        is_primary=True,
        created_at=created_at,
        updated_at=created_at,
    )
    catl_secondary = StockIdentifier(
        stock_id=catl.id,
        identifier_type=IdentifierType.H_SHARE,
        exchange_code="HKEX",
        ticker="3750",
        composite_symbol="3750.HK",
        currency="HKD",
        is_primary=False,
        created_at=created_at,
        updated_at=created_at,
    )
    byd_primary = StockIdentifier(
        stock_id=byd.id,
        identifier_type=IdentifierType.H_SHARE,
        exchange_code="HKEX",
        ticker="1211",
        composite_symbol="1211.HK",
        currency="HKD",
        is_primary=True,
        created_at=created_at,
        updated_at=created_at,
    )
    byd_secondary = StockIdentifier(
        stock_id=byd.id,
        identifier_type=IdentifierType.A_SHARE,
        exchange_code="SZSE",
        ticker="002594",
        composite_symbol="002594.SZ",
        currency="CNY",
        is_primary=False,
        created_at=created_at,
        updated_at=created_at,
    )
    xiaomi_primary = StockIdentifier(
        stock_id=xiaomi.id,
        identifier_type=IdentifierType.H_SHARE,
        exchange_code="HKEX",
        ticker="1810",
        composite_symbol="1810.HK",
        currency="HKD",
        is_primary=True,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add_all(
        [catl_primary, catl_secondary, byd_primary, byd_secondary, xiaomi_primary]
    )
    session.flush()

    def add_price_series(
        identifier: StockIdentifier,
        *,
        base_close: Decimal,
        daily_step: Decimal,
    ) -> None:
        start_date = date(2025, 6, 1)
        for offset in range(280):
            close = base_close + (daily_step * Decimal(offset))
            session.add(
                PriceBar(
                    identifier_id=identifier.id,
                    source_id=market_source.id,
                    interval=PriceInterval.DAY_1,
                    trading_date=start_date + timedelta(days=offset),
                    open=close - Decimal("1.2"),
                    high=close + Decimal("1.8"),
                    low=close - Decimal("2.0"),
                    close=close,
                    adjusted_close=close,
                    volume=1_000_000 + (offset * 1_000),
                    turnover=close * Decimal(1000),
                    raw_payload={"provider": "yahoo_finance"},
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

    add_price_series(catl_primary, base_close=Decimal("180"), daily_step=Decimal("0.80"))
    add_price_series(byd_primary, base_close=Decimal("160"), daily_step=Decimal("0.35"))
    add_price_series(xiaomi_primary, base_close=Decimal("65"), daily_step=Decimal("-0.05"))

    catl_valuation = ValuationSnapshot(
        stock_id=catl.id,
        source_id=fundamentals_source.id,
        as_of_date=date(2026, 4, 13),
        currency="CNY",
        market_cap=Decimal("1025000000000"),
        pe_ttm=Decimal("18.4"),
        pe_forward=Decimal("16.2"),
        pb=Decimal("4.8"),
        ps_ttm=Decimal("2.6"),
        enterprise_value=Decimal("1088000000000"),
        ev_ebitda=Decimal("12.7"),
        dividend_yield=Decimal("0.008"),
        raw_payload={
            "provider": "manual_fundamentals",
            "source_name": "Manual Fundamentals Feed",
            "source_url": "https://data.example.com/fundamentals",
        },
        created_at=created_at,
        updated_at=created_at,
    )
    byd_valuation = ValuationSnapshot(
        stock_id=byd.id,
        source_id=fundamentals_source.id,
        as_of_date=date(2026, 4, 13),
        currency="CNY",
        market_cap=Decimal("880000000000"),
        pe_ttm=Decimal("23.1"),
        pe_forward=Decimal("20.4"),
        pb=Decimal("5.2"),
        ps_ttm=Decimal("1.9"),
        enterprise_value=Decimal("910000000000"),
        ev_ebitda=Decimal("13.5"),
        dividend_yield=Decimal("0.004"),
        raw_payload={
            "provider": "manual_fundamentals",
            "source_name": "Manual Fundamentals Feed",
            "source_url": "https://data.example.com/fundamentals",
        },
        created_at=created_at,
        updated_at=created_at,
    )
    session.add_all([catl_valuation, byd_valuation])

    catl_financials = FinancialMetric(
        stock_id=catl.id,
        source_id=fundamentals_source.id,
        period_type=FinancialPeriodType.ANNUAL,
        fiscal_year=2025,
        fiscal_period="FY",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        report_date=date(2026, 3, 31),
        currency="CNY",
        revenue=Decimal("405000000000"),
        net_profit=Decimal("52000000000"),
        gross_margin=Decimal("0.284"),
        operating_margin=Decimal("0.197"),
        roe=Decimal("0.212"),
        roa=Decimal("0.093"),
        debt_to_equity=Decimal("0.61"),
        revenue_growth_yoy=Decimal("0.214"),
        net_profit_growth_yoy=Decimal("0.266"),
        raw_payload={
            "provider": "manual_fundamentals",
            "source_name": "Manual Fundamentals Feed",
            "source_url": "https://data.example.com/fundamentals",
        },
        created_at=created_at,
        updated_at=created_at,
    )
    byd_financials = FinancialMetric(
        stock_id=byd.id,
        source_id=fundamentals_source.id,
        period_type=FinancialPeriodType.ANNUAL,
        fiscal_year=2025,
        fiscal_period="FY",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        report_date=date(2026, 3, 31),
        currency="CNY",
        revenue=Decimal("780000000000"),
        net_profit=Decimal("42000000000"),
        gross_margin=Decimal("0.231"),
        operating_margin=Decimal("0.115"),
        roe=Decimal("0.186"),
        roa=Decimal("0.081"),
        debt_to_equity=Decimal("0.74"),
        revenue_growth_yoy=Decimal("0.178"),
        net_profit_growth_yoy=Decimal("0.192"),
        raw_payload={
            "provider": "manual_fundamentals",
            "source_name": "Manual Fundamentals Feed",
            "source_url": "https://data.example.com/fundamentals",
        },
        created_at=created_at,
        updated_at=created_at,
    )
    session.add_all([catl_financials, byd_financials])

    catl_news_items = [
        NewsItem(
            source_id=news_source.id,
            external_id="catl-exports",
            provider="Reuters",
            title="CATL exports accelerate as European EV demand improves",
            url="https://news.example.com/catl/exports-accelerate",
            summary="CATL highlighted stronger overseas orders and expanding plant utilization.",
            language="en",
            published_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
            raw_payload={"source_url": "https://www.reuters.com/example/catl-exports"},
            created_at=created_at,
            updated_at=created_at,
        ),
        NewsItem(
            source_id=news_source.id,
            external_id="catl-capacity",
            provider="Bloomberg",
            title="CATL ramps overseas battery capacity to support global customers",
            url="https://news.example.com/catl/capacity-ramp",
            summary="New capacity and customer wins reinforced a positive export narrative.",
            language="en",
            published_at=datetime(2026, 4, 12, 8, 30, tzinfo=UTC),
            raw_payload={"source_url": "https://www.bloomberg.com/example/catl-capacity"},
            created_at=created_at,
            updated_at=created_at,
        ),
    ]
    byd_news_items = [
        NewsItem(
            source_id=news_source.id,
            external_id="byd-pricing",
            provider="Financial Times",
            title="BYD faces pricing pressure as overseas EV competition intensifies",
            url="https://news.example.com/byd/pricing-pressure",
            summary="Competitive pricing and channel expansion kept the narrative mixed.",
            language="en",
            published_at=datetime(2026, 4, 13, 6, 45, tzinfo=UTC),
            raw_payload={"source_url": "https://www.ft.com/example/byd-pricing"},
            created_at=created_at,
            updated_at=created_at,
        )
    ]
    session.add_all(catl_news_items + byd_news_items)
    session.flush()

    for news_item in catl_news_items:
        session.add(
            StockNewsMention(
                stock_id=catl.id,
                news_item_id=news_item.id,
                relevance_score=Decimal("0.94"),
                created_at=created_at,
                updated_at=created_at,
            )
        )
    for news_item in byd_news_items:
        session.add(
            StockNewsMention(
                stock_id=byd.id,
                news_item_id=news_item.id,
                relevance_score=Decimal("0.88"),
                created_at=created_at,
                updated_at=created_at,
            )
        )

    session.add_all(
        [
            Announcement(
                stock_id=catl.id,
                source_id=announcements_source.id,
                external_id="cninfo:1224899411",
                title="关于选举第四届董事会职工代表董事的公告",
                url="https://static.cninfo.com.cn/finalpage/2025-12-25/1224899411.PDF",
                provider="CNInfo Disclosures",
                exchange_code="SZSE",
                category=None,
                language="zh",
                published_at=datetime(2026, 4, 14, 2, 15, tzinfo=UTC),
                as_of_date=date(2026, 4, 14),
                summary=None,
                raw_payload={
                    "source_name": "CNInfo Disclosures",
                    "source_url": "https://www.cninfo.com.cn/new/disclosure/detail?stockCode=300750&announcementId=1224899411",
                    "exchange_code": "SZSE",
                },
                created_at=created_at,
                updated_at=created_at,
            ),
            Announcement(
                stock_id=byd.id,
                source_id=announcements_source.id,
                external_id="cninfo:1224856392",
                title="临时股东会投票表决结果",
                url="https://static.cninfo.com.cn/finalpage/2025-12-05/1224856392.PDF",
                provider="CNInfo Disclosures",
                exchange_code="HKEX",
                category=None,
                language="zh",
                published_at=datetime(2026, 4, 13, 12, 30, tzinfo=UTC),
                as_of_date=date(2026, 4, 13),
                summary=None,
                raw_payload={
                    "source_name": "CNInfo Disclosures",
                    "source_url": "https://www.cninfo.com.cn/new/disclosure/detail?stockCode=01211&announcementId=1224856392",
                    "exchange_code": "HKEX",
                },
                created_at=created_at,
                updated_at=created_at,
            ),
        ]
    )

    catl_analysis = build_stock_analysis_response(
        slug=catl.slug,
        symbol=catl_primary.composite_symbol,
        company_name=catl.company_name,
        company_name_zh=catl.company_name_zh,
        sector=catl.sector,
        outbound_theme=catl.outbound_theme,
        news_items=catl_news_items,
        valuation=catl_valuation,
        fundamentals=catl_financials,
        generated_at=datetime(2026, 4, 14, 7, 0, tzinfo=UTC),
    )
    byd_analysis = build_stock_analysis_response(
        slug=byd.slug,
        symbol=byd_primary.composite_symbol,
        company_name=byd.company_name,
        company_name_zh=byd.company_name_zh,
        sector=byd.sector,
        outbound_theme=byd.outbound_theme,
        news_items=byd_news_items,
        valuation=byd_valuation,
        fundamentals=byd_financials,
        generated_at=datetime(2026, 4, 14, 7, 5, tzinfo=UTC),
    )
    for stock, analysis in [(catl, catl_analysis), (byd, byd_analysis)]:
        analysis_payload = analysis.model_dump(mode="json")
        analysis_payload.update(
            {
                "analysis_mode": "live_ai",
                "model_provider": "openai",
                "model_name": "gpt-5.4-mini",
                "prompt_version": "live-v1",
                "missing_inputs": [],
                "freshness": {
                    "latest_news_at": analysis.generated_at.isoformat()
                    if analysis.generated_at is not None
                    else None,
                    "latest_announcement_at": (
                        "2026-04-14T02:15:00+00:00"
                        if stock.slug == "catl"
                        else "2026-04-13T12:30:00+00:00"
                    ),
                    "latest_price_date": "2026-03-07",
                    "valuation_as_of_date": "2026-04-13",
                    "fundamentals_report_date": "2026-03-31",
                    "scoring_as_of_date": "2026-04-14",
                },
            }
        )
        if stock.slug == "catl":
            older_payload = {**analysis_payload, "summary": "Older mock summary", "analysis_mode": "heuristic_fallback"}
            session.add(
                AIArtifact(
                    stock_id=stock.id,
                    artifact_type=AIArtifactType.THESIS_SUMMARY,
                    model_provider="mock",
                    model_name="deterministic-heuristic-v1",
                    prompt_version="mock-v1",
                    status=JobStatus.SUCCESS,
                    generated_at=datetime(2026, 4, 14, 6, 45, tzinfo=UTC),
                    content_markdown="Older mock summary",
                    structured_payload=older_payload,
                    source_links={
                        "references": older_payload["source_references"],
                        "urls": older_payload["source_links"],
                    },
                    trace_payload={"source": "unit-test-older"},
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        session.add(
            AIArtifact(
                stock_id=stock.id,
                artifact_type=AIArtifactType.THESIS_SUMMARY,
                model_provider="openai",
                model_name="gpt-5.4-mini",
                prompt_version="live-v1",
                status=JobStatus.SUCCESS,
                generated_at=analysis.generated_at,
                content_markdown=analysis.summary,
                structured_payload=analysis_payload,
                source_links={
                    "references": analysis_payload["source_references"],
                    "urls": analysis_payload["source_links"],
                },
                trace_payload={"source": "unit-test"},
                created_at=created_at,
                updated_at=created_at,
            )
        )

    scoring_run = ScoringRun(
        run_date=date(2026, 4, 14),
        methodology_version="transparent-db-v1",
        weights_json={
            "fundamentals_quality": 0.25,
            "valuation_attractiveness": 0.25,
            "price_momentum": 0.15,
            "news_sentiment": 0.20,
            "globalization_strength": 0.15,
        },
        status=JobStatus.SUCCESS,
        notes="DB-backed scoring test seed",
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(scoring_run)
    session.flush()

    session.add_all(
        [
            StockScore(
                scoring_run_id=scoring_run.id,
                stock_id=catl.id,
                fundamentals_score=Decimal("0.84"),
                valuation_score=Decimal("0.78"),
                momentum_score=Decimal("0.93"),
                sentiment_score=Decimal("0.81"),
                globalization_score=Decimal("0.88"),
                total_score=Decimal("0.85"),
                rank=1,
                score_details={"source": "unit-test"},
                created_at=created_at,
                updated_at=created_at,
            ),
            StockScore(
                scoring_run_id=scoring_run.id,
                stock_id=byd.id,
                fundamentals_score=Decimal("0.71"),
                valuation_score=Decimal("0.58"),
                momentum_score=Decimal("0.66"),
                sentiment_score=Decimal("0.41"),
                globalization_score=Decimal("0.75"),
                total_score=Decimal("0.62"),
                rank=2,
                score_details={"source": "unit-test"},
                created_at=created_at,
                updated_at=created_at,
            ),
            StockScore(
                scoring_run_id=scoring_run.id,
                stock_id=xiaomi.id,
                fundamentals_score=Decimal("0.35"),
                valuation_score=Decimal("0.22"),
                momentum_score=Decimal("0.18"),
                sentiment_score=Decimal("0.19"),
                globalization_score=Decimal("0.44"),
                total_score=Decimal("0.27"),
                rank=3,
                score_details={"source": "unit-test"},
                created_at=created_at,
                updated_at=created_at,
            ),
        ]
    )

    recommendation_created_at = datetime(2026, 4, 14, 8, 0, tzinfo=UTC)
    recommendation_run = RecommendationRun(
        scoring_run_id=scoring_run.id,
        status=JobStatus.SUCCESS,
        explanation_markdown="Top and bottom ranked names from the latest DB scoring run.",
        trace_payload={"source": "unit-test"},
        created_at=recommendation_created_at,
        updated_at=recommendation_created_at,
    )
    session.add(recommendation_run)
    session.flush()

    session.add_all(
        [
            RecommendationItem(
                recommendation_run_id=recommendation_run.id,
                stock_id=catl.id,
                side=RecommendationSide.LONG,
                confidence_score=Decimal("0.84"),
                rationale_markdown="CATL remains the clearest long setup from the stored DB evidence.",
                bull_case=catl_analysis.bull_case,
                bear_case=catl_analysis.bear_case,
                key_risks={"risks": catl_analysis.key_risks},
                supporting_metrics={"total_score": 0.85},
                source_links={"urls": catl_analysis.source_links},
                created_at=recommendation_created_at,
                updated_at=recommendation_created_at,
            ),
            RecommendationItem(
                recommendation_run_id=recommendation_run.id,
                stock_id=xiaomi.id,
                side=RecommendationSide.SHORT,
                confidence_score=Decimal("0.68"),
                rationale_markdown="Xiaomi screens as the weakest setup in the latest stored scores.",
                bull_case=None,
                bear_case=None,
                key_risks={"risks": ["Short squeeze risk if auto execution surprises positively"]},
                supporting_metrics={"total_score": 0.27},
                source_links={"urls": ["https://news.example.com/xiaomi/watchlist"]},
                created_at=recommendation_created_at,
                updated_at=recommendation_created_at,
            ),
        ]
    )

    session.add_all(
        [
            RefreshJob(
                job_name="refresh-prices",
                job_type=RefreshJobType.MARKET_DATA_REFRESH,
                status=JobStatus.SUCCESS,
                scheduled_for=datetime(2026, 4, 14, 7, 0, tzinfo=UTC),
                started_at=datetime(2026, 4, 14, 7, 0, tzinfo=UTC),
                completed_at=datetime(2026, 4, 14, 7, 4, tzinfo=UTC),
                trigger_source="scheduler",
                stage_status={"price_bars": 840},
                created_at=created_at,
                updated_at=created_at,
            ),
            RefreshJob(
                job_name="refresh-news",
                job_type=RefreshJobType.NEWS_REFRESH,
                status=JobStatus.FAILED,
                scheduled_for=datetime(2026, 4, 14, 7, 5, tzinfo=UTC),
                started_at=datetime(2026, 4, 14, 7, 5, tzinfo=UTC),
                completed_at=datetime(2026, 4, 14, 7, 6, tzinfo=UTC),
                trigger_source="scheduler",
                stage_status={"news_items": 0},
                error_message="Provider timeout",
                created_at=created_at,
                updated_at=created_at,
            ),
            RefreshJob(
                job_name="refresh-fundamentals",
                job_type=RefreshJobType.FUNDAMENTALS_REFRESH,
                status=JobStatus.SUCCESS,
                scheduled_for=datetime(2026, 4, 14, 7, 7, tzinfo=UTC),
                started_at=datetime(2026, 4, 14, 7, 7, tzinfo=UTC),
                completed_at=datetime(2026, 4, 14, 7, 10, tzinfo=UTC),
                trigger_source="scheduler",
                stage_status={"valuation_snapshots": 3, "financial_metrics": 12},
                created_at=created_at,
                updated_at=created_at,
            ),
            RefreshJob(
                job_name="analyze-live",
                job_type=RefreshJobType.AI_REFRESH,
                status=JobStatus.RUNNING,
                scheduled_for=datetime(2026, 4, 14, 8, 10, tzinfo=UTC),
                started_at=datetime(2026, 4, 14, 8, 10, tzinfo=UTC),
                trigger_source="scheduler",
                stage_status={"phase": "ai_analysis"},
                created_at=created_at,
                updated_at=created_at,
            ),
            RefreshJob(
                job_name="score-universe",
                job_type=RefreshJobType.SCORING_REFRESH,
                status=JobStatus.SUCCESS,
                scheduled_for=datetime(2026, 4, 14, 8, 20, tzinfo=UTC),
                started_at=datetime(2026, 4, 14, 8, 20, tzinfo=UTC),
                completed_at=datetime(2026, 4, 14, 8, 21, tzinfo=UTC),
                trigger_source="scheduler",
                stage_status={"ranked_count": 3},
                created_at=created_at,
                updated_at=created_at,
            ),
        ]
    )


@pytest.fixture
def db_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

    with session_factory() as session:
        _seed_live_database(session)
        session.commit()

    monkeypatch.setattr(stocks_endpoint, "get_sync_session", session_factory)
    monkeypatch.setattr(compare_endpoint, "get_sync_session", session_factory)
    monkeypatch.setattr(recommendations_endpoint, "get_sync_session", session_factory)
    monkeypatch.setattr(admin_endpoint, "get_sync_session", session_factory)

    with TestClient(app) as test_client:
        yield test_client

    engine.dispose()


def test_healthcheck() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "China Outbound Stock AI Analyzer API"
    assert payload["settings_loaded"] is True
    assert payload["router_loaded"] is True


def test_root_health_shell() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["service"] == "China Outbound Stock AI Analyzer API"


def test_database_unavailable_returns_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_database_error():
        raise DatabaseUnavailableError("bad database config")

    monkeypatch.setattr(stocks_endpoint, "get_sync_session", _raise_database_error)

    response = client.get("/api/v1/stocks")

    assert response.status_code == 503
    payload = response.json()
    assert payload["type"] == "database_unavailable"
    assert payload["detail"] == "Database is unavailable or misconfigured."


def test_dashboard_preview_contains_all_universe_members() -> None:
    response = client.get("/api/v1/metadata/dashboard-preview")

    assert response.status_code == 200
    payload = response.json()

    assert len(payload["universe"]) == 15
    assert {item["slug"] for item in payload["universe"]} >= {"catl", "xiaomi", "jerry-group"}


def test_stocks_endpoint_lists_database_records_not_mock_universe(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks")

    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 3
    assert {item["slug"] for item in payload} == {"catl", "byd", "xiaomi"}
    byd = next(item for item in payload if item["slug"] == "byd")
    assert byd["valuation"]["source"] == "Manual Fundamentals Feed"
    assert byd["valuation"]["currency"] == "CNY"
    assert byd["financial_snapshot"]["report_date"] == "2026-03-31"
    assert byd["financial_snapshot"]["report_period"] == "FY 2025"


def test_stock_detail_route_supports_symbol_lookup_from_database(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks/1211.HK")

    assert response.status_code == 200
    payload = response.json()

    assert payload["slug"] == "byd"
    assert payload["primary_symbol"] == "1211.HK"
    assert payload["factor_scores"]["total_score"] == pytest.approx(0.62)
    assert payload["valuation"]["pe_ttm"] == pytest.approx(23.1)
    assert payload["valuation"]["enterprise_value"] == pytest.approx(910000000000)
    assert payload["valuation"]["source"] == "Manual Fundamentals Feed"
    assert payload["valuation"]["currency"] == "CNY"
    assert payload["financial_snapshot"]["revenue_growth_yoy"] == pytest.approx(0.178)
    assert payload["financial_snapshot"]["operating_margin"] == pytest.approx(0.115)
    assert payload["financial_snapshot"]["debt_to_equity"] == pytest.approx(0.74)
    assert payload["financial_snapshot"]["source"] == "Manual Fundamentals Feed"
    assert payload["financial_snapshot"]["as_of_date"] == "2026-03-31"
    assert payload["financial_snapshot"]["report_period"] == "FY 2025"
    assert payload["announcements"][0]["provider"] == "CNInfo Disclosures"
    assert payload["announcements"][0]["exchange_code"] == "HKEX"
    assert payload["announcements"][0]["as_of_date"] == "2026-04-13"


def test_stock_detail_route_returns_nulls_for_missing_db_metrics(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks/xiaomi")

    assert response.status_code == 200
    payload = response.json()

    assert payload["slug"] == "xiaomi"
    assert payload["symbol"] == "1810.HK"
    assert payload["valuation"]["pe_ttm"] is None
    assert payload["valuation"]["source"] is None
    assert payload["valuation"]["currency"] is None
    assert payload["financial_snapshot"]["revenue"] is None
    assert payload["financial_snapshot"]["source"] is None
    assert payload["financial_snapshot"]["as_of_date"] is None
    assert payload["announcements"] == []


def test_stock_timeseries_endpoint_returns_database_points_for_requested_range(
    db_client: TestClient,
) -> None:
    response = db_client.get("/api/v1/stocks/300750.SZ/timeseries?range=3m")

    assert response.status_code == 200
    payload = response.json()

    assert payload["symbol"] == "300750.SZ"
    assert payload["range"] == "3m"
    assert len(payload["points"]) == 63
    assert payload["points"][-1]["close"] == pytest.approx(403.2)


def test_stock_news_endpoint_returns_database_articles(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks/300750.SZ/news")

    assert response.status_code == 200
    payload = response.json()

    assert payload["symbol"] == "300750.SZ"
    assert len(payload["items"]) == 2
    assert payload["items"][0]["url"] == "https://news.example.com/catl/exports-accelerate"
    assert payload["items"][0]["source_url"] == "https://www.reuters.com/example/catl-exports"


def test_stock_analysis_endpoint_reads_ai_artifact_from_database(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks/300750.SZ/analysis")

    assert response.status_code == 200
    payload = response.json()

    assert payload["symbol"] == "300750.SZ"
    assert payload["schema_version"] == "analysis-v2"
    assert payload["analysis_mode"] == "live_ai"
    assert payload["model_name"] == "gpt-5.4-mini"
    assert payload["summary"]
    assert payload["summary"] != "Older mock summary"
    assert payload["top_news_themes"]
    assert payload["freshness"]["latest_announcement_at"] == "2026-04-14T02:15:00Z"
    assert payload["source_references"]
    assert all(
        "demo.local" not in (reference.get("url") or "")
        for reference in payload["source_references"]
    )


def test_stock_analysis_endpoint_returns_empty_sections_when_ai_summary_is_missing(
    db_client: TestClient,
) -> None:
    response = db_client.get("/api/v1/stocks/1810.HK/analysis")

    assert response.status_code == 200
    payload = response.json()

    assert payload["symbol"] == "1810.HK"
    assert payload["summary"] == ""
    assert payload["top_news_themes"] == []
    assert payload["key_risks"] == []
    assert payload["sentiment_score"] is None


def test_ai_limitations_endpoint_returns_methodology_sections() -> None:
    response = client.get("/api/v1/metadata/ai-limitations")

    assert response.status_code == 200
    payload = response.json()

    assert payload["schema_version"] == "ai-methodology-v2"
    assert len(payload["sections"]) == 3


def test_admin_jobs_endpoint_returns_latest_job_statuses(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/admin/jobs")

    assert response.status_code == 200
    payload = response.json()

    assert len(payload["jobs"]) == 6
    by_name = {job["job_name"]: job for job in payload["jobs"]}
    assert by_name["refresh-prices"]["latest_status"] == "SUCCESS"
    assert by_name["refresh-news"]["latest_status"] == "FAILED"
    assert by_name["refresh-news"]["error_message"] == "Provider timeout"
    assert by_name["refresh-fundamentals"]["latest_status"] == "SUCCESS"
    assert by_name["analyze-live"]["is_running"] is True
    assert by_name["score-universe"]["last_success_at"] == "2026-04-14T08:21:00"


def test_compare_endpoint_reads_database_scores_and_highlights(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/compare?symbols=300750.SZ,1211.HK,1810.HK")

    assert response.status_code == 200
    payload = response.json()

    assert payload["requested_symbols"] == ["300750.SZ", "1211.HK", "1810.HK"]
    assert len(payload["rows"]) == 3
    assert payload["highlights"]["most_attractive_symbol"] == "300750.SZ"
    assert payload["highlights"]["least_attractive_symbol"] == "1810.HK"
    byd_row = next(row for row in payload["rows"] if row["symbol"] == "1211.HK")
    assert byd_row["valuation"]["source"] == "Manual Fundamentals Feed"
    assert byd_row["valuation"]["currency"] == "CNY"
    assert byd_row["financial_snapshot"]["operating_margin"] == pytest.approx(0.115)
    assert byd_row["financial_snapshot"]["report_period"] == "FY 2025"
    assert next(row for row in payload["rows"] if row["symbol"] == "1810.HK")["valuation"]["pe_ttm"] is None


def test_recommendations_endpoints_return_database_recommendation_items(
    db_client: TestClient,
) -> None:
    latest_response = db_client.get("/api/v1/recommendations/latest")
    root_response = db_client.get("/api/v1/recommendations")

    assert latest_response.status_code == 200
    assert root_response.status_code == 200

    payload = root_response.json()

    assert payload == latest_response.json()
    assert payload["methodology_version"] == "transparent-db-v1"
    assert len(payload["items"]) == 2
    assert {item["side"] for item in payload["items"]} == {"LONG", "SHORT"}
    assert payload["items"][0]["explanation"] == "CATL remains the clearest long setup from the stored DB evidence."
    assert payload["items"][0]["analysis"]["analysis_mode"] == "live_ai"
    assert payload["items"][1]["analysis"]["summary"] == ""
    assert payload["items"][1]["valuation"]["pe_ttm"] is None


async def test_mock_market_adapter_generates_price_history() -> None:
    adapter = MockMarketDataAdapter()

    records = await adapter.fetch_price_history(
        "1211.HK",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 2, 1),
    )

    assert records
    assert records[0].symbol == "1211.HK"
    assert records[-1].close > 0


async def test_mock_news_and_announcements_are_generated() -> None:
    news_adapter = MockNewsAdapter()
    announcement_adapter = MockAnnouncementAdapter()

    news = await news_adapter.fetch_recent_news("300750.SZ", limit=3)
    announcements = await announcement_adapter.fetch_announcements("300750.SZ", limit=2)

    assert len(news) == 3
    assert len(announcements) == 2
    assert all(item.url.startswith("https://demo.local") for item in news + announcements)
