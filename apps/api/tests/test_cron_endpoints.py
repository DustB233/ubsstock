import asyncio
from typing import Any

from fastapi.testclient import TestClient

from china_outbound_analyzer.api.v1.endpoints import cron as cron_endpoint
from china_outbound_analyzer.core.config import Settings
from china_outbound_analyzer.main import app


class FakeCronRunner:
    def __init__(self, *, settings: Settings):
        self.settings = settings

    def bootstrap(self) -> dict[str, Any]:
        return {"status": "SUCCESS", "seed": {"stocks": 15}}

    async def daily_refresh(self) -> dict[str, Any]:
        return {
            "status": "SUCCESS",
            "jobs": {
                "refresh-prices": {"status": "SUCCESS"},
                "refresh-news": {"status": "SUCCESS"},
                "refresh-announcements": {"status": "SUCCESS"},
            },
        }

    async def fundamentals_refresh(self) -> dict[str, Any]:
        return {"status": "PARTIAL", "jobs": {"refresh-fundamentals": {"status": "PARTIAL"}}}

    async def analyze_and_score(self) -> dict[str, Any]:
        return {"status": "SKIPPED", "reason": "required_refresh_inputs_not_ready"}

    async def refresh_prices(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    async def refresh_news(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    async def refresh_announcements(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    async def analyze_live(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    def score_universe(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}


def test_cron_endpoint_rejects_missing_secret(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret=None),
    )

    response = TestClient(app).get("/api/v1/cron/bootstrap")

    assert response.status_code == 503
    assert response.json()["detail"] == "CRON_SECRET is not configured."


def test_cron_endpoint_rejects_unauthorized_request(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )

    response = TestClient(app).get("/api/v1/cron/bootstrap")

    assert response.status_code == 401


def test_cron_endpoint_runs_authorized_daily_refresh(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )
    monkeypatch.setattr(cron_endpoint, "CronRefreshRunner", FakeCronRunner)

    response = TestClient(app).get(
        "/api/v1/cron/daily-refresh",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"] == "daily-refresh"
    assert payload["status"] == "SUCCESS"
    assert payload["jobs"]["refresh-prices"]["status"] == "SUCCESS"


def test_cron_endpoint_returns_207_for_partial(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )
    monkeypatch.setattr(cron_endpoint, "CronRefreshRunner", FakeCronRunner)

    response = TestClient(app).get(
        "/api/v1/cron/fundamentals",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 207
    assert response.json()["status"] == "PARTIAL"


def test_cron_endpoint_returns_202_for_skipped(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )
    monkeypatch.setattr(cron_endpoint, "CronRefreshRunner", FakeCronRunner)

    response = TestClient(app).get(
        "/api/v1/cron/analyze-score",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "SKIPPED"


def test_fake_runner_async_methods_stay_awaitable() -> None:
    result = asyncio.run(FakeCronRunner(settings=Settings(cron_secret="x")).daily_refresh())

    assert result["status"] == "SUCCESS"
