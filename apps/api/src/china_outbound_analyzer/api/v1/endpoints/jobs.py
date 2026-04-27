import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, status

from china_outbound_analyzer.schemas.jobs import RefreshJobRequest, RefreshJobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/refresh", response_model=RefreshJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_refresh(job: RefreshJobRequest) -> RefreshJobResponse:
    return RefreshJobResponse(
        job_id=str(uuid.uuid4()),
        status="PENDING",
        job_type=job.job_type,
        created_at=datetime.now(UTC),
        message="Refresh job accepted. Background orchestration arrives in Phase 2.",
    )
