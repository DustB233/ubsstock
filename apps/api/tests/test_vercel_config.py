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
    assert config["crons"] == [
        {"path": "/api/v1/cron/daily-refresh", "schedule": "30 10 * * *"},
        {"path": "/api/v1/cron/fundamentals", "schedule": "30 11 * * *"},
    ]
    assert all(cron["path"] != "/api/v1/cron/analyze-score" for cron in config["crons"])


def test_vercel_cron_paths_are_get_routes() -> None:
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))

    from api.index import app

    route_methods_by_path = {
        route.path: route.methods for route in app.routes if route.path.startswith("/api/v1/cron/")
    }

    for cron in json.loads((API_ROOT / "vercel.json").read_text())["crons"]:
        methods = route_methods_by_path[cron["path"]]
        assert "GET" in methods
        assert "POST" not in methods


def test_vercel_serverless_entrypoint_exports_fastapi_app() -> None:
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))

    from api.index import app

    assert app.title == "China Outbound Stock AI Analyzer API"
