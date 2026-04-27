from datetime import date

from pydantic import BaseModel


class DashboardStockRowResponse(BaseModel):
    slug: str
    company_name: str
    primary_symbol: str
    sector: str
    latest_price: float | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_1y: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    ps_ttm: float | None = None
    total_score: float | None = None
    rank: int | None = None


class DashboardRecommendationCardResponse(BaseModel):
    side: str
    slug: str | None = None
    company_name: str | None = None
    explanation: str
    total_score: float | None = None


class DashboardOverviewResponse(BaseModel):
    as_of_date: date | None = None
    stocks: list[DashboardStockRowResponse]
    recommendations: list[DashboardRecommendationCardResponse]
