import asyncio

from fastapi import APIRouter

from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.schemas.dashboard import DashboardOverviewResponse
from china_outbound_analyzer.services.market.read_models import DashboardReadService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _load_dashboard_overview() -> DashboardOverviewResponse:
    with get_sync_session() as session:
        return DashboardReadService(session).get_overview()


@router.get("/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview() -> DashboardOverviewResponse:
    return await asyncio.to_thread(_load_dashboard_overview)
