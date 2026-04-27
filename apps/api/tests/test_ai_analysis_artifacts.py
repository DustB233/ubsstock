from datetime import UTC, datetime

from china_outbound_analyzer.services.ai.competition_artifacts import (
    build_ai_methodology,
    build_stock_analysis_response,
)


def test_competition_analysis_response_is_deterministic() -> None:
    generated_at = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    news_items = [
        {
            "id": "news-1",
            "title": "CATL overseas demand strengthens as export orders improve",
            "summary": "Export momentum improves and management points to stable margins.",
            "url": "https://example.com/news/1",
            "provider": "Example Wire",
            "published_at": "2026-04-14T08:00:00Z",
        },
        {
            "id": "news-2",
            "title": "CATL margin outlook stabilizes after battery expansion update",
            "summary": "Capacity expansion supports supply while profit expectations stay constructive.",
            "url": "https://example.com/news/2",
            "provider": "Example Wire",
            "published_at": "2026-04-13T08:00:00Z",
        },
        {
            "id": "news-3",
            "title": "Industry competition intensifies in battery supply chain",
            "summary": "Competition and pricing pressure create caution around near-term profitability.",
            "url": "https://example.com/news/3",
            "provider": "Example Wire",
            "published_at": "2026-04-12T08:00:00Z",
        },
    ]
    valuation = {
        "as_of_date": "2026-04-14",
        "pe_ttm": 22.4,
        "pb": 4.6,
        "ps_ttm": 2.8,
        "market_cap": 1120.0,
        "ev_ebitda": 14.2,
    }
    fundamentals = {
        "report_date": "2026-03-31",
        "revenue_growth_yoy": 0.18,
        "net_profit_growth_yoy": 0.22,
        "gross_margin": 0.29,
        "roe": 0.17,
    }

    first = build_stock_analysis_response(
        slug="catl",
        symbol="300750.SZ",
        company_name="CATL",
        company_name_zh="宁德时代",
        sector="Battery Systems",
        outbound_theme="Global EV battery leadership and cross-border manufacturing expansion.",
        news_items=news_items,
        valuation=valuation,
        fundamentals=fundamentals,
        generated_at=generated_at,
    )
    second = build_stock_analysis_response(
        slug="catl",
        symbol="300750.SZ",
        company_name="CATL",
        company_name_zh="宁德时代",
        sector="Battery Systems",
        outbound_theme="Global EV battery leadership and cross-border manufacturing expansion.",
        news_items=news_items,
        valuation=valuation,
        fundamentals=fundamentals,
        generated_at=generated_at,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.schema_version == "analysis-v2"
    assert len(first.top_news_themes) == 3
    assert first.sentiment_score is not None
    assert -1 <= first.sentiment_score <= 1
    assert first.summary_evidence
    assert first.valuation_evidence
    assert len(first.risk_evidence) == 3
    assert first.source_links == [
        "https://example.com/news/1",
        "https://example.com/news/2",
        "https://example.com/news/3",
    ]


def test_ai_methodology_sections_include_strengths_and_limitations() -> None:
    methodology = build_ai_methodology()

    assert methodology.schema_version == "ai-methodology-v2"
    assert len(methodology.sections) == 3
    assert {section.tone for section in methodology.sections} == {
        "strength",
        "limitation",
        "human_review",
    }
