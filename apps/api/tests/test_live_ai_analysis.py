from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from china_outbound_analyzer.core.config import Settings
from china_outbound_analyzer.core.database import Base
from china_outbound_analyzer.models.entities import (
    AIArtifact,
    Announcement,
    DataSource,
    FinancialMetric,
    NewsItem,
    PriceBar,
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
)
from china_outbound_analyzer.services.ai.live_pipeline import (
    GeneratedNarrative,
    HeuristicNarrativeGenerator,
    LiveAIAnalysisService,
    LiveAnalysisContext,
    LiveAnalysisNarrativeDraft,
    LiveAnalysisRiskDraft,
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


def _seed_stock_inputs(session: Session, *, include_financials: bool = True) -> None:
    created_at = datetime(2026, 4, 14, 9, 0, tzinfo=UTC)

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
    filing_source = DataSource(
        source_key="exchange_filings",
        display_name="Exchange Filings",
        kind=DataSourceKind.ANNOUNCEMENTS,
        is_mock=False,
        base_url="https://www.hkexnews.hk",
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
    session.add_all([market_source, news_source, filing_source, fundamentals_source])
    session.flush()

    stock = Stock(
        slug="catl",
        company_name="CATL",
        company_name_zh="宁德时代",
        sector="Battery Systems",
        outbound_theme="Global battery export leadership with expanding overseas plants.",
        primary_exchange="SZSE",
        is_active=True,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(stock)
    session.flush()

    identifier = StockIdentifier(
        stock_id=stock.id,
        identifier_type=IdentifierType.A_SHARE,
        exchange_code="SZSE",
        ticker="300750",
        composite_symbol="300750.SZ",
        currency="CNY",
        is_primary=True,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(identifier)
    session.flush()

    start_date = date(2026, 2, 20)
    for offset in range(80):
        close = Decimal("210") + Decimal("0.6") * Decimal(offset)
        session.add(
            PriceBar(
                identifier_id=identifier.id,
                source_id=market_source.id,
                interval=PriceInterval.DAY_1,
                trading_date=start_date + timedelta(days=offset),
                open=close - Decimal("1.0"),
                high=close + Decimal("1.4"),
                low=close - Decimal("1.6"),
                close=close,
                adjusted_close=close,
                volume=1_200_000 + offset * 500,
                raw_payload={"source_name": "Yahoo Finance"},
                created_at=created_at,
                updated_at=created_at,
            )
        )

    session.add(
        ValuationSnapshot(
            stock_id=stock.id,
            source_id=fundamentals_source.id,
            as_of_date=date(2026, 4, 13),
            market_cap=Decimal("1000000000000"),
            pe_ttm=Decimal("18.4"),
            pb=Decimal("4.1"),
            ps_ttm=Decimal("2.3"),
            enterprise_value=Decimal("1040000000000"),
            raw_payload={
                "source_name": "Manual Fundamentals Feed",
                "source_url": "https://data.example.com/fundamentals",
            },
            created_at=created_at,
            updated_at=created_at,
        )
    )

    if include_financials:
        session.add(
            FinancialMetric(
                stock_id=stock.id,
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
                    "source_name": "Manual Fundamentals Feed",
                    "source_url": "https://data.example.com/fundamentals",
                },
                created_at=created_at,
                updated_at=created_at,
            )
        )

    news_item = NewsItem(
        source_id=news_source.id,
        external_id="catl-1",
        provider="Reuters",
        title="CATL export orders accelerate with stronger Europe battery demand",
        url="https://news.example.com/catl/orders",
        summary="Management flagged improving overseas order books and stable battery margins.",
        language="en",
        published_at=datetime(2026, 4, 14, 6, 30, tzinfo=UTC),
        raw_payload={"source_url": "https://www.reuters.com/example/catl-orders"},
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(news_item)
    session.flush()
    session.add(
        StockNewsMention(
            stock_id=stock.id,
            news_item_id=news_item.id,
            relevance_score=Decimal("0.95"),
            created_at=created_at,
            updated_at=created_at,
        )
    )

    session.add(
        Announcement(
            stock_id=stock.id,
            source_id=filing_source.id,
            external_id="catl-announcement-1",
            title="CATL confirms new Hungary battery capacity milestone",
            url="https://filings.example.com/catl/hungary",
            category="Capacity",
            published_at=datetime(2026, 4, 14, 5, 0, tzinfo=UTC),
            summary="The filing highlights commissioning progress for CATL's overseas plant.",
            raw_payload={
                "source_name": "Exchange Filings",
                "source_url": "https://www.hkexnews.hk/example/catl-hungary",
            },
            created_at=created_at,
            updated_at=created_at,
        )
    )

    scoring_run = ScoringRun(
        run_date=date(2026, 4, 14),
        methodology_version="transparent-v1",
        weights_json={"fundamentals_quality": 0.25},
        status=JobStatus.SUCCESS,
        notes="unit-test",
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(scoring_run)
    session.flush()
    session.add(
        StockScore(
            scoring_run_id=scoring_run.id,
            stock_id=stock.id,
            fundamentals_score=Decimal("82"),
            valuation_score=Decimal("78"),
            momentum_score=Decimal("74"),
            sentiment_score=Decimal("80"),
            globalization_score=Decimal("92"),
            total_score=Decimal("82.1"),
            rank=1,
            score_details={"unit": "test"},
            created_at=created_at,
            updated_at=created_at,
        )
    )


class _StubLiveGenerator:
    async def generate(self, context: LiveAnalysisContext) -> GeneratedNarrative:
        news_reference = context.news_items[0]["id"]
        announcement_reference = context.announcements[0]["id"]
        return GeneratedNarrative(
            draft=LiveAnalysisNarrativeDraft(
                investment_takeaway="CATL's live setup remains constructive as export demand and overseas capacity evidence reinforce a strong stored score profile.",
                summary_evidence_ids=[news_reference, "metric:factor_total_score"],
                valuation_summary="Stored valuation looks acceptable relative to growth, with the latest PE and PB metrics still supported by live fundamentals.",
                valuation_evidence_ids=["metric:pe_ttm", "metric:pb"],
                bull_case="The bull case is that CATL converts overseas capacity and export demand into another year of double-digit revenue and profit growth.",
                bull_case_evidence_ids=[
                    news_reference,
                    announcement_reference,
                    "metric:revenue_growth_yoy",
                    "metric:net_profit_growth_yoy",
                ],
                bear_case="The bear case is that pricing pressure erodes margin support before the market rewards the new capacity build-out.",
                bear_case_evidence_ids=["metric:gross_margin", "metric:pb"],
                key_risks=[
                    LiveAnalysisRiskDraft(
                        risk="Overseas execution timing risk",
                        evidence_ids=[announcement_reference, news_reference],
                    ),
                    LiveAnalysisRiskDraft(
                        risk="Margin compression risk",
                        evidence_ids=["metric:gross_margin", "metric:pe_ttm"],
                    ),
                ],
                missing_inputs=[],
            ),
            analysis_mode="live_ai",
            model_provider="openai",
            model_name="gpt-5.4-mini",
            prompt_version="live-v1",
            trace_payload={"provider": "stub"},
        )

    async def aclose(self) -> None:
        return None


class _RaisingGenerator:
    async def generate(self, context: LiveAnalysisContext) -> GeneratedNarrative:
        raise RuntimeError("LLM unavailable")

    async def aclose(self) -> None:
        return None


class _SpuriousMissingInputsGenerator(_StubLiveGenerator):
    async def generate(self, context: LiveAnalysisContext) -> GeneratedNarrative:
        generated = await super().generate(context)
        return GeneratedNarrative(
            draft=generated.draft.model_copy(
                update={"missing_inputs": ["company_announcements", "recent_news"]}
            ),
            analysis_mode=generated.analysis_mode,
            model_provider=generated.model_provider,
            model_name=generated.model_name,
            prompt_version=generated.prompt_version,
            trace_payload=generated.trace_payload,
        )


def test_live_analysis_narrative_schema_is_strict_output_compatible() -> None:
    schema = LiveAnalysisNarrativeDraft.model_json_schema()

    assert set(schema["required"]) == set(schema["properties"].keys())

    risk_schema = schema["$defs"]["LiveAnalysisRiskDraft"]
    assert set(risk_schema["required"]) == {"risk", "evidence_ids"}


@pytest.mark.asyncio
async def test_live_ai_analysis_service_persists_structured_artifacts() -> None:
    engine, session_factory = _session_factory()

    with session_factory() as session:
        _seed_stock_inputs(session)
        session.commit()

        service = LiveAIAnalysisService(
            session,
            settings=Settings(ai_analysis_provider="openai"),
            analysis_generator=_StubLiveGenerator(),
            fallback_generator=HeuristicNarrativeGenerator(),
        )
        result = await service.run()

        thesis = session.scalars(
            select(AIArtifact)
            .where(AIArtifact.artifact_type == AIArtifactType.THESIS_SUMMARY)
            .order_by(AIArtifact.generated_at.desc(), AIArtifact.created_at.desc())
            .limit(1)
        ).first()
        sentiment = session.scalars(
            select(AIArtifact)
            .where(AIArtifact.artifact_type == AIArtifactType.SENTIMENT_SUMMARY)
            .order_by(AIArtifact.generated_at.desc(), AIArtifact.created_at.desc())
            .limit(1)
        ).first()

        assert result["status"] == "SUCCESS"
        assert result["live_ai_symbols"] == 1
        assert thesis is not None
        assert sentiment is not None
        assert thesis.model_provider == "openai"
        assert thesis.model_name == "gpt-5.4-mini"
        assert thesis.refresh_job_id is not None
        assert thesis.structured_payload["analysis_mode"] == "live_ai"
        assert thesis.structured_payload["summary"].startswith("CATL's live setup remains constructive")
        assert thesis.structured_payload["freshness"]["latest_news_at"].startswith(
            "2026-04-14T06:30:00"
        )
        assert "announcement:" in ",".join(
            reference["reference_id"] for reference in thesis.structured_payload["source_references"]
        )
        assert any(
            reference["reference_type"] == "announcement"
            for reference in thesis.structured_payload["source_references"]
        )
        assert sentiment.structured_payload["score"] == thesis.structured_payload["sentiment_score"]

    engine.dispose()


@pytest.mark.asyncio
async def test_live_ai_analysis_service_falls_back_to_heuristic_when_generator_fails() -> None:
    engine, session_factory = _session_factory()

    with session_factory() as session:
        _seed_stock_inputs(session, include_financials=False)
        session.commit()

        service = LiveAIAnalysisService(
            session,
            settings=Settings(ai_analysis_provider="openai"),
            analysis_generator=_RaisingGenerator(),
            fallback_generator=HeuristicNarrativeGenerator(),
        )
        result = await service.run()

        thesis = session.scalars(
            select(AIArtifact)
            .where(AIArtifact.artifact_type == AIArtifactType.THESIS_SUMMARY)
            .order_by(AIArtifact.generated_at.desc(), AIArtifact.created_at.desc())
            .limit(1)
        ).first()

        assert result["status"] == "PARTIAL"
        assert result["fallback_symbols"] == 1
        assert thesis is not None
        assert thesis.structured_payload["analysis_mode"] == "heuristic_fallback"
        assert "financial_snapshot" in thesis.structured_payload["missing_inputs"]

    engine.dispose()


@pytest.mark.asyncio
async def test_live_ai_analysis_service_can_process_stock_slug_batch() -> None:
    engine, session_factory = _session_factory()

    with session_factory() as session:
        _seed_stock_inputs(session)
        session.commit()

        service = LiveAIAnalysisService(
            session,
            settings=Settings(ai_analysis_provider="openai"),
            analysis_generator=_StubLiveGenerator(),
            fallback_generator=HeuristicNarrativeGenerator(),
        )
        result = await service.run(stock_slugs=["missing-stock", "catl"])

        thesis_count = session.scalars(
            select(AIArtifact).where(AIArtifact.artifact_type == AIArtifactType.THESIS_SUMMARY)
        ).all()

        assert result["status"] == "SUCCESS"
        assert result["requested_symbols"] == 2
        assert result["symbols"] == 1
        assert len(thesis_count) == 1

    engine.dispose()


@pytest.mark.asyncio
async def test_live_ai_analysis_service_ignores_spurious_model_missing_inputs() -> None:
    engine, session_factory = _session_factory()

    with session_factory() as session:
        _seed_stock_inputs(session)
        session.commit()

        service = LiveAIAnalysisService(
            session,
            settings=Settings(ai_analysis_provider="openai"),
            analysis_generator=_SpuriousMissingInputsGenerator(),
            fallback_generator=HeuristicNarrativeGenerator(),
        )
        result = await service.run()

        thesis = session.scalars(
            select(AIArtifact)
            .where(AIArtifact.artifact_type == AIArtifactType.THESIS_SUMMARY)
            .order_by(AIArtifact.generated_at.desc(), AIArtifact.created_at.desc())
            .limit(1)
        ).first()

        assert result["status"] == "SUCCESS"
        assert thesis is not None
        assert thesis.structured_payload["missing_inputs"] == []

    engine.dispose()
