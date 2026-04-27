import asyncio

from fastapi import APIRouter, Query

from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.schemas.compare_views import ComparisonViewResponse
from china_outbound_analyzer.services.market.read_models import DatabaseMarketReadService

router = APIRouter(prefix="/compare", tags=["compare"])


def _load_comparison(requested_symbols: list[str]) -> ComparisonViewResponse:
    with get_sync_session() as session:
        return DatabaseMarketReadService(session).compare(requested_symbols)


@router.get("", response_model=ComparisonViewResponse)
async def compare_stocks(symbols: str | None = Query(default=None)) -> ComparisonViewResponse:
    requested_symbols = [item.strip() for item in (symbols or "").split(",") if item.strip()]
    return await asyncio.to_thread(_load_comparison, requested_symbols)
