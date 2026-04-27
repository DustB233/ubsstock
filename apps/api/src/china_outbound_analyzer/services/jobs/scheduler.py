from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.services.ai.live_pipeline import LiveAIAnalysisService
from china_outbound_analyzer.services.ingestion.announcements_refresh import (
    AnnouncementRefreshService,
)
from china_outbound_analyzer.services.ingestion.fundamentals_refresh import (
    FundamentalsRefreshService,
)
from china_outbound_analyzer.services.ingestion.news_refresh import NewsRefreshService
from china_outbound_analyzer.services.ingestion.price_refresh import PriceRefreshService
from china_outbound_analyzer.services.jobs.runtime import (
    coerce_utc_timestamp,
    latest_job_for_name,
)
from china_outbound_analyzer.services.recommendation.scoring import ScoringService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchedulerJobResult:
    job_name: str
    action: str
    detail: dict[str, str | int] | None = None


@dataclass(frozen=True)
class RunnableJobDefinition:
    job_name: str
    enabled: bool
    interval_minutes: int
    runner: Callable[[], dict[str, str | int]]


class SchedulerService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: Callable[[], Session] = get_sync_session,
        sleep_seconds: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.sleep_seconds = sleep_seconds

    def run_forever(self) -> None:
        logger.info(
            "Starting scheduler with poll interval %ss",
            self.settings.scheduler_poll_seconds,
        )
        while True:
            results = self.run_pending_cycle()
            if results:
                logger.info("Scheduler cycle completed with %s actions", len(results))
            self.sleep_seconds(self.settings.scheduler_poll_seconds)

    def run_pending_cycle(self) -> list[SchedulerJobResult]:
        results: list[SchedulerJobResult] = []
        for definition in self._job_definitions():
            if not definition.enabled:
                results.append(SchedulerJobResult(job_name=definition.job_name, action="disabled"))
                continue

            if not self._is_due(definition.job_name, definition.interval_minutes):
                results.append(SchedulerJobResult(job_name=definition.job_name, action="not_due"))
                continue

            logger.info("Running scheduled job %s", definition.job_name)
            detail = definition.runner()
            action = "ran"
            if detail.get("status") == "SKIPPED":
                action = "skipped"
                logger.info("Scheduled job %s skipped: %s", definition.job_name, detail)
            else:
                logger.info("Scheduled job %s finished: %s", definition.job_name, detail)
            results.append(
                SchedulerJobResult(
                    job_name=definition.job_name,
                    action=action,
                    detail=detail,
                )
            )

        return results

    def _job_definitions(self) -> list[RunnableJobDefinition]:
        return [
            RunnableJobDefinition(
                job_name="refresh-prices",
                enabled=self.settings.scheduler_prices_enabled,
                interval_minutes=self.settings.scheduler_prices_interval_minutes,
                runner=self._run_price_refresh,
            ),
            RunnableJobDefinition(
                job_name="refresh-news",
                enabled=self.settings.scheduler_news_enabled,
                interval_minutes=self.settings.scheduler_news_interval_minutes,
                runner=self._run_news_refresh,
            ),
            RunnableJobDefinition(
                job_name="refresh-announcements",
                enabled=self.settings.scheduler_announcements_enabled,
                interval_minutes=self.settings.scheduler_announcements_interval_minutes,
                runner=self._run_announcements_refresh,
            ),
            RunnableJobDefinition(
                job_name="refresh-fundamentals",
                enabled=self.settings.scheduler_fundamentals_enabled,
                interval_minutes=self.settings.scheduler_fundamentals_interval_minutes,
                runner=self._run_fundamentals_refresh,
            ),
            RunnableJobDefinition(
                job_name="analyze-live",
                enabled=self.settings.scheduler_analyze_enabled,
                interval_minutes=self.settings.scheduler_analyze_interval_minutes,
                runner=self._run_analysis,
            ),
            RunnableJobDefinition(
                job_name="score-universe",
                enabled=self.settings.scheduler_score_enabled,
                interval_minutes=self.settings.scheduler_score_interval_minutes,
                runner=self._run_scoring,
            ),
        ]

    def _is_due(self, job_name: str, interval_minutes: int) -> bool:
        with self.session_factory() as session:
            latest_job = latest_job_for_name(session, job_name)
            if latest_job is None:
                return True

            reference_time = coerce_utc_timestamp(
                latest_job.completed_at or latest_job.started_at or latest_job.created_at
            )
            if reference_time is None:
                return True

            return reference_time <= datetime.now(UTC) - timedelta(minutes=max(interval_minutes, 1))

    def _run_price_refresh(self) -> dict[str, str | int]:
        with self.session_factory() as session:
            return asyncio.run(
                PriceRefreshService(session, settings=self.settings).run(
                    lookback_days=self.settings.scheduler_prices_lookback_days,
                    trigger_source="scheduler",
                    job_name="refresh-prices",
                )
            )

    def _run_news_refresh(self) -> dict[str, str | int]:
        with self.session_factory() as session:
            return asyncio.run(
                NewsRefreshService(session, settings=self.settings).run(
                    limit_per_symbol=self.settings.scheduler_news_limit,
                    trigger_source="scheduler",
                    job_name="refresh-news",
                )
            )

    def _run_announcements_refresh(self) -> dict[str, str | int]:
        with self.session_factory() as session:
            return asyncio.run(
                AnnouncementRefreshService(session, settings=self.settings).run(
                    limit_per_symbol=self.settings.scheduler_announcements_limit,
                    lookback_days=self.settings.scheduler_announcements_lookback_days,
                    trigger_source="scheduler",
                    job_name="refresh-announcements",
                )
            )

    def _run_analysis(self) -> dict[str, str | int]:
        with self.session_factory() as session:
            return asyncio.run(
                LiveAIAnalysisService(session, settings=self.settings).run(
                    trigger_source="scheduler",
                    job_name="analyze-live",
                    stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
                )
            )

    def _run_fundamentals_refresh(self) -> dict[str, str | int]:
        with self.session_factory() as session:
            return asyncio.run(
                FundamentalsRefreshService(session, settings=self.settings).run(
                    trigger_source="scheduler",
                    job_name="refresh-fundamentals",
                )
            )

    def _run_scoring(self) -> dict[str, str | int]:
        with self.session_factory() as session:
            return ScoringService(session).run(
                trigger_source="scheduler",
                job_name="score-universe",
                stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
            )
