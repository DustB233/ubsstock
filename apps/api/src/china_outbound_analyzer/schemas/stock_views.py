from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from china_outbound_analyzer.schemas.common import EmptyState, PricePoint


class ReturnSnapshotResponse(BaseModel):
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None


class FactorScoreBreakdownResponse(BaseModel):
    fundamentals_quality: float | None = None
    valuation_attractiveness: float | None = None
    price_momentum: float | None = None
    news_sentiment: float | None = None
    globalization_strength: float | None = None
    total_score: float | None = None
    rank: int | None = None


class ValuationSnapshotResponse(BaseModel):
    currency: str | None = None
    market_cap: float | None = None
    pe_ttm: float | None = None
    pe_forward: float | None = None
    pb: float | None = None
    ps_ttm: float | None = None
    enterprise_value: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    as_of_date: date | None = None
    source: str | None = None
    source_url: str | None = None


class FinancialSnapshotResponse(BaseModel):
    as_of_date: date | None = None
    report_date: date | None = None
    report_period: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    currency: str | None = None
    revenue: float | None = None
    net_income: float | None = None
    net_profit: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    debt_to_equity: float | None = None
    overseas_revenue_ratio: float | None = None
    revenue_growth_yoy: float | None = None
    net_income_growth_yoy: float | None = None
    net_profit_growth_yoy: float | None = None
    source: str | None = None
    source_url: str | None = None


class StockIdentifierViewResponse(BaseModel):
    exchange_code: str
    composite_symbol: str
    identifier_type: str
    currency: str
    is_primary: bool


class StockListViewResponse(BaseModel):
    slug: str
    company_name: str
    company_name_zh: str | None = None
    sector: str
    outbound_theme: str
    primary_symbol: str
    identifiers: list[StockIdentifierViewResponse]
    valuation: ValuationSnapshotResponse | None = None
    financial_snapshot: FinancialSnapshotResponse | None = None


class StockDetailViewResponse(BaseModel):
    slug: str
    symbol: str
    company_name: str
    company_name_zh: str | None = None
    sector: str
    outbound_theme: str
    primary_symbol: str
    latest_price: float | None = None
    returns: ReturnSnapshotResponse
    factor_scores: FactorScoreBreakdownResponse
    valuation: ValuationSnapshotResponse
    financial_snapshot: FinancialSnapshotResponse
    identifiers: list[StockIdentifierViewResponse]
    announcements: list[StockAnnouncementItemResponse] = Field(default_factory=list)


class StockTimeseriesResponse(BaseModel):
    slug: str
    symbol: str
    range: str
    points: list[PricePoint]
    empty_state: EmptyState | None = None


class StockNewsItemResponse(BaseModel):
    title: str
    url: str
    published_at: datetime
    summary: str | None = None
    provider: str | None = None
    source_url: str | None = None
    sentiment_label: str | None = None


class StockNewsFeedResponse(BaseModel):
    slug: str
    symbol: str
    items: list[StockNewsItemResponse]
    empty_state: EmptyState | None = None


class StockAnnouncementItemResponse(BaseModel):
    title: str
    url: str
    published_at: datetime
    as_of_date: date | None = None
    summary: str | None = None
    provider: str | None = None
    source_url: str | None = None
    exchange_code: str | None = None
    category: str | None = None
    language: str | None = None


class AnalysisEvidenceReferenceResponse(BaseModel):
    reference_id: str
    reference_type: Literal["news_article", "announcement", "metric"]
    label: str
    url: str | None = None
    provider: str | None = None
    published_at: datetime | None = None
    source_url: str | None = None
    metric_key: str | None = None
    metric_value: float | str | None = None
    metric_unit: str | None = None
    as_of_date: date | None = None


class AnalysisThemeResponse(BaseModel):
    theme: str
    article_count: int
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    summary: str
    evidence: list[AnalysisEvidenceReferenceResponse]


class AnalysisKeywordInsightResponse(BaseModel):
    keyword: str
    mentions: int
    evidence: list[AnalysisEvidenceReferenceResponse]


class AnalysisRiskInsightResponse(BaseModel):
    risk: str
    evidence: list[AnalysisEvidenceReferenceResponse]


class AnalysisFreshnessResponse(BaseModel):
    latest_news_at: datetime | None = None
    latest_announcement_at: datetime | None = None
    latest_price_date: date | None = None
    valuation_as_of_date: date | None = None
    fundamentals_report_date: date | None = None
    scoring_as_of_date: date | None = None


class StockAnalysisResponse(BaseModel):
    slug: str
    symbol: str
    schema_version: str
    generated_at: datetime | None = None
    analysis_mode: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    freshness: AnalysisFreshnessResponse = Field(default_factory=AnalysisFreshnessResponse)
    summary: str
    summary_evidence: list[AnalysisEvidenceReferenceResponse]
    top_news_themes: list[AnalysisThemeResponse]
    valuation_summary: str
    valuation_evidence: list[AnalysisEvidenceReferenceResponse]
    bull_case: str
    bull_case_evidence: list[AnalysisEvidenceReferenceResponse]
    bear_case: str
    bear_case_evidence: list[AnalysisEvidenceReferenceResponse]
    key_risks: list[str]
    risk_evidence: list[AnalysisRiskInsightResponse]
    keywords: list[str]
    keyword_insights: list[AnalysisKeywordInsightResponse]
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    sentiment_evidence: list[AnalysisEvidenceReferenceResponse]
    source_references: list[AnalysisEvidenceReferenceResponse]
    source_links: list[str]
