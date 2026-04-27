from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from china_outbound_analyzer.models.entities import RefreshJob
from china_outbound_analyzer.models.enums import JobStatus, RefreshJobType


@dataclass(frozen=True)
class SchedulableJobDefinition:
    job_name: str
    job_type: RefreshJobType
    env_enabled_key: str
    env_interval_key: str


SCHEDULABLE_JOB_DEFINITIONS: tuple[SchedulableJobDefinition, ...] = (
    SchedulableJobDefinition(
        job_name="refresh-prices",
        job_type=RefreshJobType.MARKET_DATA_REFRESH,
        env_enabled_key="scheduler_prices_enabled",
        env_interval_key="scheduler_prices_interval_minutes",
    ),
    SchedulableJobDefinition(
        job_name="refresh-news",
        job_type=RefreshJobType.NEWS_REFRESH,
        env_enabled_key="scheduler_news_enabled",
        env_interval_key="scheduler_news_interval_minutes",
    ),
    SchedulableJobDefinition(
        job_name="refresh-announcements",
        job_type=RefreshJobType.ANNOUNCEMENTS_REFRESH,
        env_enabled_key="scheduler_announcements_enabled",
        env_interval_key="scheduler_announcements_interval_minutes",
    ),
    SchedulableJobDefinition(
        job_name="refresh-fundamentals",
        job_type=RefreshJobType.FUNDAMENTALS_REFRESH,
        env_enabled_key="scheduler_fundamentals_enabled",
        env_interval_key="scheduler_fundamentals_interval_minutes",
    ),
    SchedulableJobDefinition(
        job_name="analyze-live",
        job_type=RefreshJobType.AI_REFRESH,
        env_enabled_key="scheduler_analyze_enabled",
        env_interval_key="scheduler_analyze_interval_minutes",
    ),
    SchedulableJobDefinition(
        job_name="score-universe",
        job_type=RefreshJobType.SCORING_REFRESH,
        env_enabled_key="scheduler_score_enabled",
        env_interval_key="scheduler_score_interval_minutes",
    ),
)


def coerce_utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def start_job_run(
    session: Session,
    *,
    job_name: str,
    job_type: RefreshJobType,
    trigger_source: str,
    stale_after_seconds: int,
    scheduled_for: datetime | None = None,
    stage_status: dict | None = None,
) -> RefreshJob | None:
    now = datetime.now(UTC)
    active_cutoff = now - timedelta(seconds=max(stale_after_seconds, 1))
    running_jobs = session.scalars(
        select(RefreshJob)
        .where(
            RefreshJob.job_name == job_name,
            RefreshJob.status == JobStatus.RUNNING,
        )
        .order_by(RefreshJob.started_at.desc(), RefreshJob.created_at.desc())
    ).all()

    active_jobs: list[RefreshJob] = []
    for running_job in running_jobs:
        started_at = coerce_utc_timestamp(running_job.started_at or running_job.created_at) or now
        if started_at >= active_cutoff:
            active_jobs.append(running_job)
            continue

        running_job.status = JobStatus.FAILED
        running_job.completed_at = now
        running_job.error_message = (
            running_job.error_message or "Marked stale before a new run was started."
        )

    if active_jobs:
        session.commit()
        return None

    refresh_job = RefreshJob(
        job_name=job_name,
        job_type=job_type,
        status=JobStatus.RUNNING,
        scheduled_for=scheduled_for or now,
        started_at=now,
        trigger_source=trigger_source,
        stage_status=stage_status,
    )
    session.add(refresh_job)
    session.flush()
    return refresh_job


def complete_job_success(
    session: Session,
    refresh_job: RefreshJob,
    *,
    stage_status: dict | None = None,
    status: JobStatus = JobStatus.SUCCESS,
    error_message: str | None = None,
) -> None:
    refresh_job.status = status
    refresh_job.completed_at = datetime.now(UTC)
    if stage_status is not None:
        refresh_job.stage_status = stage_status
    refresh_job.error_message = error_message
    session.flush()


def complete_job_failure(
    session: Session,
    refresh_job: RefreshJob,
    *,
    error_message: str,
    stage_status: dict | None = None,
) -> None:
    refresh_job.status = JobStatus.FAILED
    refresh_job.completed_at = datetime.now(UTC)
    refresh_job.error_message = error_message
    if stage_status is not None:
        refresh_job.stage_status = stage_status
    session.flush()


def latest_job_for_name(session: Session, job_name: str) -> RefreshJob | None:
    return session.scalars(
        select(RefreshJob)
        .where(RefreshJob.job_name == job_name)
        .order_by(RefreshJob.started_at.desc(), RefreshJob.created_at.desc())
        .limit(1)
    ).first()


def latest_successful_job_for_name(session: Session, job_name: str) -> RefreshJob | None:
    return session.scalars(
        select(RefreshJob)
        .where(
            RefreshJob.job_name == job_name,
            RefreshJob.status.in_([JobStatus.SUCCESS, JobStatus.PARTIAL]),
        )
        .order_by(RefreshJob.completed_at.desc(), RefreshJob.created_at.desc())
        .limit(1)
    ).first()
