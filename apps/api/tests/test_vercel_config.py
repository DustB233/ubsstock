import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]


def test_vercel_config_is_hobby_safe() -> None:
    config = json.loads((API_ROOT / "vercel.json").read_text())

    assert "builds" not in config
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/api/index.py"}]
    assert set(config.get("functions", {})) == {"api/index.py"}
    assert len(config.get("crons", [])) <= 2
    assert {cron["path"] for cron in config["crons"]} == {
        "/api/v1/cron/hobby-data-refresh",
        "/api/v1/cron/hobby-analysis",
    }

    for function_config in config.get("functions", {}).values():
        assert 1 <= function_config["maxDuration"] <= 300


def test_vercel_serverless_entrypoint_exports_fastapi_app() -> None:
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))

    from api.index import app

    assert app.title == "China Outbound Stock AI Analyzer API"
