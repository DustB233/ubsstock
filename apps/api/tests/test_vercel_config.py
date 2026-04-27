import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]


def test_vercel_config_uses_auto_detected_python_function() -> None:
    config = json.loads((API_ROOT / "vercel.json").read_text())

    assert "builds" not in config
    assert "functions" not in config
    assert "maxDuration" not in json.dumps(config)
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/api/index.py"}]
    assert (API_ROOT / "api" / "index.py").is_file()
    assert len(config.get("crons", [])) <= 2
    assert {cron["path"] for cron in config["crons"]} == {
        "/api/v1/cron/hobby-data-refresh",
        "/api/v1/cron/hobby-analysis",
    }


def test_vercel_serverless_entrypoint_exports_fastapi_app() -> None:
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))

    from api.index import app

    assert app.title == "China Outbound Stock AI Analyzer API"
