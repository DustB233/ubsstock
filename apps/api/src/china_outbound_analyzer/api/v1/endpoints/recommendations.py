import asyncio

from fastapi import APIRouter

from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.schemas.recommendations import RecommendationSnapshotResponse
from china_outbound_analyzer.services.market.read_models import DatabaseMarketReadService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _load_recommendations() -> RecommendationSnapshotResponse:
    with get_sync_session() as session:
        return DatabaseMarketReadService(session).get_recommendation_snapshot()


@router.get("", response_model=RecommendationSnapshotResponse)
async def recommendations() -> RecommendationSnapshotResponse:
    return await asyncio.to_thread(_load_recommendations)


@router.get("/latest", response_model=RecommendationSnapshotResponse)
async def latest_recommendations() -> RecommendationSnapshotResponse:
    return await asyncio.to_thread(_load_recommendations)
