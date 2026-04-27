import asyncio

from fastapi import APIRouter

from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.schemas.jobs import AdminJobStatusResponse
from china_outbound_analyzer.services.jobs.status import AdminJobStatusService

router = APIRouter(prefix="/admin", tags=["admin"])


def _load_admin_jobs() -> AdminJobStatusResponse:
    with get_sync_session() as session:
        return AdminJobStatusService(session).get_status()


@router.get("/jobs", response_model=AdminJobStatusResponse)
async def admin_jobs() -> AdminJobStatusResponse:
    return await asyncio.to_thread(_load_admin_jobs)
