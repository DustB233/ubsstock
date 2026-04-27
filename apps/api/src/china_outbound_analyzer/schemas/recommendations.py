from datetime import datetime

from pydantic import BaseModel

from china_outbound_analyzer.schemas.stock_views import (
    AnalysisEvidenceReferenceResponse,
    FactorScoreBreakdownResponse,
    FinancialSnapshotResponse,
    ReturnSnapshotResponse,
    StockAnalysisResponse,
    ValuationSnapshotResponse,
)


class RecommendationEvidenceBucketResponse(BaseModel):
    key: str
    title: str
    summary: str
    references: list[AnalysisEvidenceReferenceResponse]


class RecommendationItemResponse(BaseModel):
    side: str
    slug: str | None = None
    symbol: str | None = None
    company_name: str | None = None
    company_name_zh: str | None = None
    sector: str | None = None
    outbound_theme: str | None = None
    explanation: str
    confidence_score: float | None = None
    latest_price: float | None = None
    returns: ReturnSnapshotResponse
    factor_scores: FactorScoreBreakdownResponse
    valuation: ValuationSnapshotResponse
    financial_snapshot: FinancialSnapshotResponse
    evidence_buckets: list[RecommendationEvidenceBucketResponse]
    analysis: StockAnalysisResponse
    key_risks: list[str]
    source_links: list[str]


class RecommendationSnapshotResponse(BaseModel):
    methodology_version: str
    generated_at: datetime | None = None
    items: list[RecommendationItemResponse]
