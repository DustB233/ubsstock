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

    async def hobby_data_refresh(self) -> dict[str, Any]:
        return {
            "status": "SUCCESS",
            "mode": "hobby_safe_rotating_data_refresh",
            "selected_job": "refresh-prices",
            "jobs": {"refresh-prices": {"status": "SUCCESS"}},
        }

    async def hobby_analysis(self) -> dict[str, Any]:
        return {
            "status": "PARTIAL",
            "mode": "hobby_safe_batched_analysis",
            "jobs": {
                "analyze-live": {
                    "status": "SUCCESS",
                    "batch_size": 3,
                    "batch_stock_slugs": ["catl", "byd", "xiaomi"],
                },
                "score-universe": {
                    "status": "SKIPPED",
                    "reason": "analysis_batches_not_complete",
                },
            },
        }

    async def analyze_and_score(self) -> dict[str, Any]:
        return {"status": "SKIPPED", "reason": "required_refresh_inputs_not_ready"}

    async def fundamentals_analyze_and_score(self) -> dict[str, Any]:
        return {
            "status": "SUCCESS",
            "jobs": {
                "refresh-fundamentals": {"status": "SUCCESS"},
                "analyze-live": {"status": "SUCCESS"},
                "score-universe": {"status": "SUCCESS"},
            },
        }

    async def refresh_prices(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    async def refresh_news(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    async def refresh_announcements(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    async def analyze_live(self) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    async def analyze_live_batch(self) -> dict[str, Any]:
        return {"status": "SUCCESS", "batch_size": 3}

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


def test_cron_endpoint_runs_authorized_hobby_data_refresh(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )
    monkeypatch.setattr(cron_endpoint, "CronRefreshRunner", FakeCronRunner)

    response = TestClient(app).get(
        "/api/v1/cron/hobby-data-refresh",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"] == "hobby-data-refresh"
    assert payload["mode"] == "hobby_safe_rotating_data_refresh"
    assert payload["selected_job"] == "refresh-prices"


def test_cron_endpoint_runs_authorized_hobby_analysis(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )
    monkeypatch.setattr(cron_endpoint, "CronRefreshRunner", FakeCronRunner)

    response = TestClient(app).get(
        "/api/v1/cron/hobby-analysis",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 207
    payload = response.json()
    assert payload["job"] == "hobby-analysis"
    assert payload["jobs"]["analyze-live"]["batch_size"] == 3


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


def test_cron_endpoint_runs_authorized_fundamentals_analyze_score(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )
    monkeypatch.setattr(cron_endpoint, "CronRefreshRunner", FakeCronRunner)

    response = TestClient(app).get(
        "/api/v1/cron/fundamentals-analyze-score",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"] == "fundamentals-analyze-score"
    assert payload["jobs"]["refresh-fundamentals"]["status"] == "SUCCESS"
    assert payload["jobs"]["analyze-live"]["status"] == "SUCCESS"
    assert payload["jobs"]["score-universe"]["status"] == "SUCCESS"


def test_cron_endpoints_are_get_only(monkeypatch) -> None:
    monkeypatch.setattr(
        cron_endpoint,
        "get_settings",
        lambda: Settings(cron_secret="test-secret"),
    )

    client = TestClient(app)
    for path in [
        "/api/v1/cron/daily-refresh",
        "/api/v1/cron/fundamentals",
        "/api/v1/cron/analyze-score",
        "/api/v1/cron/fundamentals-analyze-score",
    ]:
        response = client.post(path, headers={"Authorization": "Bearer test-secret"})
        assert response.status_code == 405


def test_fake_runner_async_methods_stay_awaitable() -> None:
    result = asyncio.run(FakeCronRunner(settings=Settings(cron_secret="x")).daily_refresh())

    assert result["status"] == "SUCCESS"
