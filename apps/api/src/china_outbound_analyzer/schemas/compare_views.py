from pydantic import BaseModel

from china_outbound_analyzer.schemas.stock_views import (
    FactorScoreBreakdownResponse,
    FinancialSnapshotResponse,
    ValuationSnapshotResponse,
)


class ComparisonRowResponse(BaseModel):
    slug: str
    symbol: str
    company_name: str
    sector: str
    factor_scores: FactorScoreBreakdownResponse
    valuation: ValuationSnapshotResponse
    financial_snapshot: FinancialSnapshotResponse
    sentiment_label: str | None = None
    sentiment_score: float | None = None


class ComparisonHighlightsResponse(BaseModel):
    most_attractive_symbol: str | None = None
    most_attractive_name: str | None = None
    least_attractive_symbol: str | None = None
    least_attractive_name: str | None = None


class ComparisonViewResponse(BaseModel):
    requested_symbols: list[str]
    rows: list[ComparisonRowResponse]
    highlights: ComparisonHighlightsResponse
