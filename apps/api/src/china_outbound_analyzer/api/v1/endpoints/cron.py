import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response, status

from china_outbound_analyzer.core.config import Settings, get_settings
from china_outbound_analyzer.services.jobs.cron_runner import CronRefreshRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cron", tags=["cron"])


def _require_cron_authorization(
    authorization: str | None,
    settings: Settings,
) -> None:
    if not settings.cron_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CRON_SECRET is not configured.",
        )

    expected = f"Bearer {settings.cron_secret}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")


async def _run_cron_job(
    *,
    job_name: str,
    authorization: str | None,
    runner_fn: Callable[[CronRefreshRunner], Any],
    response: Response,
) -> dict[str, Any]:
    settings = get_settings()
    _require_cron_authorization(authorization, settings)

    logger.info("Starting Vercel cron job %s", job_name)
    runner = CronRefreshRunner(settings=settings)
    try:
        result = await asyncio.to_thread(runner_fn, runner)
    except Exception as exc:
        logger.exception("Vercel cron job %s failed: %s", job_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{job_name} failed: {exc}",
        ) from exc

    if result.get("status") == "SKIPPED":
        response.status_code = status.HTTP_202_ACCEPTED
    elif result.get("status") == "PARTIAL":
        response.status_code = status.HTTP_207_MULTI_STATUS

    logger.info("Completed Vercel cron job %s: %s", job_name, result)
    return {"job": job_name, **result}


@router.get("/bootstrap")
async def cron_bootstrap(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="bootstrap",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: runner.bootstrap(),
    )


@router.get("/prices")
async def cron_prices(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="refresh-prices",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: asyncio.run(runner.refresh_prices()),
    )


@router.get("/news")
async def cron_news(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="refresh-news",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: asyncio.run(runner.refresh_news()),
    )


@router.get("/announcements")
async def cron_announcements(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="refresh-announcements",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: asyncio.run(runner.refresh_announcements()),
    )


@router.get("/fundamentals")
async def cron_fundamentals(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="refresh-fundamentals",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: asyncio.run(runner.fundamentals_refresh()),
    )


@router.get("/daily-refresh")
async def cron_daily_refresh(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="daily-refresh",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: asyncio.run(runner.daily_refresh()),
    )


@router.get("/analyze-live")
async def cron_analyze_live(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="analyze-live",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: asyncio.run(runner.analyze_live()),
    )


@router.get("/score-universe")
async def cron_score_universe(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="score-universe",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: runner.score_universe(),
    )


@router.get("/analyze-score")
async def cron_analyze_score(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _run_cron_job(
        job_name="analyze-score",
        authorization=authorization,
        response=response,
        runner_fn=lambda runner: asyncio.run(runner.analyze_and_score()),
    )
