from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.models.enums import JobStatus
from china_outbound_analyzer.services.ai.live_pipeline import LiveAIAnalysisService
from china_outbound_analyzer.services.ingestion.announcements_refresh import (
    AnnouncementRefreshService,
)
from china_outbound_analyzer.services.ingestion.fundamentals_refresh import (
    FundamentalsRefreshService,
)
from china_outbound_analyzer.services.ingestion.news_refresh import NewsRefreshService
from china_outbound_analyzer.services.ingestion.price_refresh import PriceRefreshService
from china_outbound_analyzer.services.ingestion.seeder import seed_universe
from china_outbound_analyzer.services.jobs.runtime import (
    latest_job_for_name,
    latest_successful_job_for_name,
)
from china_outbound_analyzer.services.recommendation.scoring import ScoringService

logger = logging.getLogger(__name__)

API_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = API_ROOT / "alembic.ini"


class CronRefreshRunner:
    """Runs production cron jobs through the same idempotent services as the CLI."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: Callable[[], Session] = get_sync_session,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory

    def bootstrap(self) -> dict[str, Any]:
        if self.settings.cron_auto_migrate_enabled:
            self._run_migrations()

        with self.session_factory() as session:
            seed_result = seed_universe(session)
            session.commit()

        return {
            "status": "SUCCESS",
            "migrations": "applied" if self.settings.cron_auto_migrate_enabled else "disabled",
            "seed": seed_result,
        }

    async def refresh_prices(self) -> dict[str, Any]:
        with self.session_factory() as session:
            return await PriceRefreshService(session, settings=self.settings).run(
                lookback_days=self.settings.cron_prices_lookback_days,
                trigger_source="vercel-cron:refresh-prices",
                job_name="refresh-prices",
            )

    async def refresh_news(self) -> dict[str, Any]:
        with self.session_factory() as session:
            return await NewsRefreshService(session, settings=self.settings).run(
                limit_per_symbol=self.settings.cron_news_limit,
                trigger_source="vercel-cron:refresh-news",
                job_name="refresh-news",
            )

    async def refresh_announcements(self) -> dict[str, Any]:
        with self.session_factory() as session:
            return await AnnouncementRefreshService(session, settings=self.settings).run(
                limit_per_symbol=self.settings.cron_announcements_limit,
                lookback_days=self.settings.cron_announcements_lookback_days,
                trigger_source="vercel-cron:refresh-announcements",
                job_name="refresh-announcements",
            )

    async def refresh_fundamentals(self) -> dict[str, Any]:
        with self.session_factory() as session:
            return await FundamentalsRefreshService(session, settings=self.settings).run(
                trigger_source="vercel-cron:refresh-fundamentals",
                job_name="refresh-fundamentals",
            )

    async def analyze_live(self) -> dict[str, Any]:
        if not self._required_inputs_ready(
            ["refresh-prices", "refresh-news", "refresh-announcements", "refresh-fundamentals"]
        ):
            return {
                "status": "SKIPPED",
                "reason": "required_refresh_inputs_not_ready",
            }

        with self.session_factory() as session:
            return await LiveAIAnalysisService(session, settings=self.settings).run(
                trigger_source="vercel-cron:analyze-live",
                job_name="analyze-live",
                stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
            )

    def score_universe(self) -> dict[str, Any]:
        if not self._required_inputs_ready(["analyze-live"]):
            return {
                "status": "SKIPPED",
                "reason": "live_analysis_not_ready",
            }

        with self.session_factory() as session:
            return ScoringService(session).run(
                trigger_source="vercel-cron:score-universe",
                job_name="score-universe",
                stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
            )

    async def daily_refresh(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        prices = await self.refresh_prices()
        news = await self.refresh_news()
        announcements = await self.refresh_announcements()

        return {
            "status": self._rollup_status([prices, news, announcements]),
            "bootstrap": bootstrap,
            "jobs": {
                "refresh-prices": prices,
                "refresh-news": news,
                "refresh-announcements": announcements,
            },
        }

    async def fundamentals_refresh(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        fundamentals = await self.refresh_fundamentals()

        return {
            "status": self._rollup_status([fundamentals]),
            "bootstrap": bootstrap,
            "jobs": {"refresh-fundamentals": fundamentals},
        }

    async def analyze_and_score(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        analysis = await self.analyze_live()
        if analysis.get("status") in {"FAILED", "SKIPPED"}:
            return {
                "status": analysis.get("status"),
                "bootstrap": bootstrap,
                "jobs": {
                    "analyze-live": analysis,
                    "score-universe": {
                        "status": "SKIPPED",
                        "reason": "analysis_did_not_complete",
                    },
                },
            }

        scoring = self.score_universe()
        return {
            "status": self._rollup_status([analysis, scoring]),
            "bootstrap": bootstrap,
            "jobs": {
                "analyze-live": analysis,
                "score-universe": scoring,
            },
        }

    def _run_migrations(self) -> None:
        logger.info("Applying Alembic migrations before cron refresh.")
        alembic_config = Config(str(ALEMBIC_INI))
        alembic_config.set_main_option("script_location", str(API_ROOT / "migrations"))
        command.upgrade(alembic_config, "head")

    def _required_inputs_ready(self, job_names: list[str]) -> bool:
        with self.session_factory() as session:
            for job_name in job_names:
                latest = latest_job_for_name(session, job_name)
                if latest is not None and latest.status == JobStatus.RUNNING:
                    return False

                latest_success = latest_successful_job_for_name(session, job_name)
                if latest_success is None:
                    return False

        return True

    @staticmethod
    def _rollup_status(results: list[dict[str, Any]]) -> str:
        statuses = {str(result.get("status", "UNKNOWN")) for result in results}
        if "FAILED" in statuses:
            return "FAILED"
        if "PARTIAL" in statuses or "SKIPPED" in statuses:
            return "PARTIAL"
        return "SUCCESS"


def run_async_job(coro) -> dict[str, Any]:
    return asyncio.run(coro)
