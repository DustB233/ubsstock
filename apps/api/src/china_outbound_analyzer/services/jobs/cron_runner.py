from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.core.database import get_sync_session
from china_outbound_analyzer.models.entities import AIArtifact, Stock
from china_outbound_analyzer.models.enums import AIArtifactType, JobStatus
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
    coerce_utc_timestamp,
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

    async def analyze_live_batch(self) -> dict[str, Any]:
        if not self._required_inputs_ready(
            ["refresh-prices", "refresh-news", "refresh-announcements", "refresh-fundamentals"]
        ):
            return {
                "status": "SKIPPED",
                "reason": "required_refresh_inputs_not_ready",
            }

        batch_slugs = self._next_analysis_batch_slugs()
        if not batch_slugs:
            return {
                "status": "SKIPPED",
                "reason": "analysis_up_to_date",
                "batch_size": 0,
            }

        with self.session_factory() as session:
            result = await LiveAIAnalysisService(session, settings=self.settings).run(
                trigger_source="vercel-cron:analyze-live-batch",
                job_name="analyze-live",
                stale_after_seconds=self.settings.scheduler_running_job_stale_after_seconds,
                stock_slugs=batch_slugs,
            )
            return {
                **result,
                "batch_size": len(batch_slugs),
                "batch_stock_slugs": batch_slugs,
            }

    def score_universe(self) -> dict[str, Any]:
        if not self._required_inputs_ready(["analyze-live"]):
            return {
                "status": "SKIPPED",
                "reason": "live_analysis_not_ready",
            }

        if not self._analysis_complete_for_current_data():
            return {
                "status": "SKIPPED",
                "reason": "live_analysis_batches_not_complete",
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

    async def hobby_data_refresh(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        job_name = self._next_hobby_data_job_name()
        refresh_result = await self._run_data_refresh_by_name(job_name)

        return {
            "status": self._rollup_status([refresh_result]),
            "bootstrap": bootstrap,
            "selected_job": job_name,
            "jobs": {job_name: refresh_result},
            "mode": "hobby_safe_rotating_data_refresh",
        }

    async def hobby_analysis(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        if not self._required_inputs_ready(
            ["refresh-prices", "refresh-news", "refresh-announcements", "refresh-fundamentals"]
        ):
            job_name = self._next_hobby_data_job_name()
            refresh_result = await self._run_data_refresh_by_name(job_name)
            analysis = {
                "status": "SKIPPED",
                "reason": "required_refresh_inputs_not_ready",
            }
            scoring = {
                "status": "SKIPPED",
                "reason": "analysis_inputs_not_ready",
            }
            return {
                "status": self._rollup_status([refresh_result, analysis, scoring]),
                "bootstrap": bootstrap,
                "selected_job": job_name,
                "jobs": {
                    job_name: refresh_result,
                    "analyze-live": analysis,
                    "score-universe": scoring,
                },
                "mode": "hobby_safe_data_catch_up",
            }

        analysis = await self.analyze_live_batch()

        if analysis.get("status") == "FAILED":
            scoring = {
                "status": "SKIPPED",
                "reason": "analysis_batch_failed",
            }
        elif self._analysis_complete_for_current_data():
            scoring = self.score_universe()
        else:
            scoring = {
                "status": "SKIPPED",
                "reason": "analysis_batches_not_complete",
            }

        return {
            "status": self._rollup_status([analysis, scoring]),
            "bootstrap": bootstrap,
            "jobs": {
                "analyze-live": analysis,
                "score-universe": scoring,
            },
            "mode": "hobby_safe_batched_analysis",
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

    async def _run_data_refresh_by_name(self, job_name: str) -> dict[str, Any]:
        if job_name == "refresh-prices":
            return await self.refresh_prices()
        if job_name == "refresh-news":
            return await self.refresh_news()
        if job_name == "refresh-announcements":
            return await self.refresh_announcements()
        if job_name == "refresh-fundamentals":
            return await self.refresh_fundamentals()
        raise ValueError(f"Unsupported data refresh job: {job_name}")

    def _next_hobby_data_job_name(self) -> str:
        job_names = [
            "refresh-prices",
            "refresh-news",
            "refresh-announcements",
            "refresh-fundamentals",
        ]
        with self.session_factory() as session:
            job_freshness: list[tuple[datetime | None, int, str]] = []
            for index, job_name in enumerate(job_names):
                latest = latest_job_for_name(session, job_name)
                if latest is not None and latest.status == JobStatus.RUNNING:
                    continue

                latest_success = latest_successful_job_for_name(session, job_name)
                completed_at = coerce_utc_timestamp(
                    latest_success.completed_at if latest_success is not None else None
                )
                job_freshness.append((completed_at, index, job_name))

        if not job_freshness:
            return job_names[0]

        job_freshness.sort(key=lambda item: (item[0] is not None, item[0] or datetime.min, item[1]))
        return job_freshness[0][2]

    def _next_analysis_batch_slugs(self) -> list[str]:
        batch_size = max(int(self.settings.cron_ai_batch_size or 1), 1)
        data_cycle_cutoff_at = self._data_cycle_cutoff_time()

        with self.session_factory() as session:
            stocks = self._active_stocks(session)
            stale_or_missing: list[tuple[datetime | None, str]] = []
            for stock in stocks:
                latest_generated_at = self._latest_thesis_generated_at(session, stock)
                if latest_generated_at is None:
                    stale_or_missing.append((None, stock.slug))
                    continue

                if data_cycle_cutoff_at is not None and latest_generated_at < data_cycle_cutoff_at:
                    stale_or_missing.append((latest_generated_at, stock.slug))

        stale_or_missing.sort(key=lambda item: (item[0] is not None, item[0] or datetime.min, item[1]))
        return [slug for _, slug in stale_or_missing[:batch_size]]

    def _analysis_complete_for_current_data(self) -> bool:
        data_cycle_cutoff_at = self._data_cycle_cutoff_time()
        if data_cycle_cutoff_at is None:
            return False

        with self.session_factory() as session:
            stocks = self._active_stocks(session)
            if not stocks:
                return False

            for stock in stocks:
                latest_generated_at = self._latest_thesis_generated_at(session, stock)
                if latest_generated_at is None or latest_generated_at < data_cycle_cutoff_at:
                    return False

        return True

    def _data_cycle_cutoff_time(self) -> datetime | None:
        job_names = [
            "refresh-prices",
            "refresh-news",
            "refresh-announcements",
            "refresh-fundamentals",
        ]
        completed_times: list[datetime] = []
        with self.session_factory() as session:
            for job_name in job_names:
                latest_success = latest_successful_job_for_name(session, job_name)
                if latest_success is None:
                    return None

                completed_at = coerce_utc_timestamp(latest_success.completed_at)
                if completed_at is None:
                    return None

                completed_times.append(completed_at)

        return min(completed_times) if completed_times else None

    @staticmethod
    def _active_stocks(session: Session) -> list[Stock]:
        return list(
            session.scalars(
                select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.company_name)
            ).all()
        )

    @staticmethod
    def _latest_thesis_generated_at(session: Session, stock: Stock) -> datetime | None:
        latest_artifact = session.scalars(
            select(AIArtifact)
            .where(
                AIArtifact.stock_id == stock.id,
                AIArtifact.artifact_type == AIArtifactType.THESIS_SUMMARY,
                AIArtifact.status == JobStatus.SUCCESS,
            )
            .order_by(AIArtifact.generated_at.desc(), AIArtifact.created_at.desc())
            .limit(1)
        ).first()
        return coerce_utc_timestamp(
            latest_artifact.generated_at if latest_artifact is not None else None
        )

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
