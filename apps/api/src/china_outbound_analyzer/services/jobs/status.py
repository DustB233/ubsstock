from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.models.enums import JobStatus
from china_outbound_analyzer.schemas.jobs import (
    AdminJobStatusItemResponse,
    AdminJobStatusResponse,
)
from china_outbound_analyzer.services.jobs.runtime import (
    SCHEDULABLE_JOB_DEFINITIONS,
    latest_job_for_name,
    latest_successful_job_for_name,
)


class AdminJobStatusService:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    def get_status(self) -> AdminJobStatusResponse:
        jobs = []
        for definition in SCHEDULABLE_JOB_DEFINITIONS:
            latest_job = latest_job_for_name(self.session, definition.job_name)
            latest_success = latest_successful_job_for_name(self.session, definition.job_name)
            jobs.append(
                AdminJobStatusItemResponse(
                    job_name=definition.job_name,
                    job_type=definition.job_type.value,
                    enabled=bool(getattr(self.settings, definition.env_enabled_key)),
                    interval_minutes=int(getattr(self.settings, definition.env_interval_key)),
                    latest_status=latest_job.status.value if latest_job else None,
                    trigger_source=latest_job.trigger_source if latest_job else None,
                    last_run_started_at=latest_job.started_at if latest_job else None,
                    last_run_completed_at=latest_job.completed_at if latest_job else None,
                    last_success_at=latest_success.completed_at if latest_success else None,
                    error_message=latest_job.error_message if latest_job else None,
                    is_running=bool(latest_job and latest_job.status == JobStatus.RUNNING),
                )
            )

        return AdminJobStatusResponse(generated_at=datetime.now(UTC), jobs=jobs)
