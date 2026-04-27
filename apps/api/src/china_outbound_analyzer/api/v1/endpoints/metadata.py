from fastapi import APIRouter

from china_outbound_analyzer.schemas.common import EmptyState
from china_outbound_analyzer.schemas.metadata import AIMethodologyResponse
from china_outbound_analyzer.schemas.stocks import DashboardPreviewResponse
from china_outbound_analyzer.services.ai.competition_artifacts import build_ai_methodology
from china_outbound_analyzer.services.market.universe import UniverseService

router = APIRouter(prefix="/metadata", tags=["metadata"])
universe_service = UniverseService()


@router.get("/dashboard-preview", response_model=DashboardPreviewResponse)
async def dashboard_preview() -> DashboardPreviewResponse:
    return universe_service.get_dashboard_preview()


@router.get("/ai-limitations", response_model=AIMethodologyResponse)
async def ai_limitations() -> AIMethodologyResponse:
    return build_ai_methodology()


@router.get("/empty-state", response_model=EmptyState)
async def empty_state() -> EmptyState:
    return EmptyState()
