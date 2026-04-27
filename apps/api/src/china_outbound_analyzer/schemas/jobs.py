from datetime import datetime

from pydantic import BaseModel


class RefreshJobRequest(BaseModel):
    job_type: str = "DAILY_REFRESH"
    trigger_source: str = "manual"


class RefreshJobResponse(BaseModel):
    job_id: str
    status: str
    job_type: str
    created_at: datetime
    message: str


class AdminJobStatusItemResponse(BaseModel):
    job_name: str
    job_type: str
    enabled: bool
    interval_minutes: int | None = None
    latest_status: str | None = None
    trigger_source: str | None = None
    last_run_started_at: datetime | None = None
    last_run_completed_at: datetime | None = None
    last_success_at: datetime | None = None
    error_message: str | None = None
    is_running: bool = False


class AdminJobStatusResponse(BaseModel):
    generated_at: datetime
    jobs: list[AdminJobStatusItemResponse]
