from datetime import datetime

from pydantic import BaseModel

from china_outbound_analyzer.schemas.common import EmptyState, MetricValue, PricePoint, SourceLink


class StockIdentifierResponse(BaseModel):
    exchange_code: str
    composite_symbol: str
    identifier_type: str
    currency: str
    is_primary: bool


class StockListItemResponse(BaseModel):
    slug: str
    company_name: str
    company_name_zh: str | None = None
    sector: str
    outbound_theme: str
    identifiers: list[StockIdentifierResponse]


class UniverseStockCardResponse(BaseModel):
    slug: str
    companyName: str
    primarySymbol: str
    exchanges: list[str]
    sector: str
    geographyAngle: str


class RecommendationPreviewResponse(BaseModel):
    side: str
    title: str
    explanation: str


class DashboardPreviewResponse(BaseModel):
    universe: list[UniverseStockCardResponse]
    recommendations: list[RecommendationPreviewResponse]


class StockDetailResponse(BaseModel):
    slug: str
    company_name: str
    company_name_zh: str | None = None
    sector: str
    outbound_theme: str
    identifiers: list[StockIdentifierResponse]
    valuation_metrics: list[MetricValue]
    financial_metrics: list[MetricValue]
    ai_summary: str
    bull_case: str
    bear_case: str
    key_risks: list[str]
    announcements: list[SourceLink]
    news: list[SourceLink]


class PriceHistoryResponse(BaseModel):
    slug: str
    interval: str
    points: list[PricePoint]
    empty_state: EmptyState | None = None


class StockNewsResponse(BaseModel):
    slug: str
    items: list[SourceLink]
    empty_state: EmptyState | None = None


class StockAnnouncementResponse(BaseModel):
    slug: str
    items: list[SourceLink]
    empty_state: EmptyState | None = None


class AIAnalysisResponse(BaseModel):
    slug: str
    generated_at: datetime | None = None
    summary: str
    bull_case: str
    bear_case: str
    key_risks: list[str]
