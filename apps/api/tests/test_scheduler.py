from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from china_outbound_analyzer.core.config import Settings
from china_outbound_analyzer.core.database import Base
from china_outbound_analyzer.models.entities import RefreshJob
from china_outbound_analyzer.models.enums import JobStatus, RefreshJobType
from china_outbound_analyzer.services.jobs.runtime import start_job_run
from china_outbound_analyzer.services.jobs.scheduler import SchedulerService


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "CHAR(36)"


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def test_start_job_run_prevents_overlap_for_active_job() -> None:
    engine, session_factory = _session_factory()
    now = datetime.now(UTC)

    with session_factory() as session:
        session.add(
            RefreshJob(
                job_name="refresh-prices",
                job_type=RefreshJobType.MARKET_DATA_REFRESH,
                status=JobStatus.RUNNING,
                scheduled_for=now,
                started_at=now,
                trigger_source="scheduler",
            )
        )
        session.commit()

        refresh_job = start_job_run(
            session,
            job_name="refresh-prices",
            job_type=RefreshJobType.MARKET_DATA_REFRESH,
            trigger_source="scheduler",
            stale_after_seconds=3600,
        )

        assert refresh_job is None

    engine.dispose()


def test_start_job_run_marks_stale_job_failed_before_new_run() -> None:
    engine, session_factory = _session_factory()
    stale_started_at = datetime.now(UTC) - timedelta(hours=4)

    with session_factory() as session:
        stale_job = RefreshJob(
            job_name="refresh-news",
            job_type=RefreshJobType.NEWS_REFRESH,
            status=JobStatus.RUNNING,
            scheduled_for=stale_started_at,
            started_at=stale_started_at,
            trigger_source="scheduler",
        )
        session.add(stale_job)
        session.commit()

        new_job = start_job_run(
            session,
            job_name="refresh-news",
            job_type=RefreshJobType.NEWS_REFRESH,
            trigger_source="scheduler",
            stale_after_seconds=60,
        )
        session.commit()
        session.refresh(stale_job)

        assert new_job is not None
        assert stale_job.status == JobStatus.FAILED
        assert stale_job.error_message == "Marked stale before a new run was started."
        assert new_job.status == JobStatus.RUNNING

    engine.dispose()


def test_scheduler_runs_only_due_jobs() -> None:
    engine, session_factory = _session_factory()
    now = datetime.now(UTC)

    with session_factory() as session:
        session.add(
            RefreshJob(
                job_name="refresh-prices",
                job_type=RefreshJobType.MARKET_DATA_REFRESH,
                status=JobStatus.SUCCESS,
                scheduled_for=now - timedelta(minutes=10),
                started_at=now - timedelta(minutes=10),
                completed_at=now - timedelta(minutes=9),
                trigger_source="scheduler",
            )
        )
        session.commit()

    settings = Settings(
        scheduler_prices_enabled=True,
        scheduler_prices_interval_minutes=60,
        scheduler_news_enabled=True,
        scheduler_news_interval_minutes=60,
        scheduler_announcements_enabled=True,
        scheduler_announcements_interval_minutes=90,
        scheduler_fundamentals_enabled=True,
        scheduler_fundamentals_interval_minutes=120,
        scheduler_analyze_enabled=False,
        scheduler_score_enabled=False,
    )
    scheduler = SchedulerService(settings=settings, session_factory=session_factory)
    scheduler._run_news_refresh = lambda: {"status": "SUCCESS", "news_items": 5}  # type: ignore[method-assign]
    scheduler._run_announcements_refresh = lambda: {  # type: ignore[method-assign]
        "status": "SUCCESS",
        "announcements": 6,
    }
    scheduler._run_price_refresh = lambda: {"status": "SUCCESS", "price_bars": 10}  # type: ignore[method-assign]
    scheduler._run_fundamentals_refresh = lambda: {  # type: ignore[method-assign]
        "status": "SUCCESS",
        "valuation_snapshots": 3,
        "financial_metrics": 12,
    }

    results = scheduler.run_pending_cycle()
    by_name = {result.job_name: result for result in results}

    assert by_name["refresh-prices"].action == "not_due"
    assert by_name["refresh-news"].action == "ran"
    assert by_name["refresh-news"].detail == {"status": "SUCCESS", "news_items": 5}
    assert by_name["refresh-announcements"].action == "ran"
    assert by_name["refresh-announcements"].detail == {"status": "SUCCESS", "announcements": 6}
    assert by_name["refresh-fundamentals"].action == "ran"
    assert by_name["analyze-live"].action == "disabled"
    assert by_name["score-universe"].action == "disabled"

    engine.dispose()
