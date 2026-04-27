import json
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]


def test_vercel_config_is_hobby_safe() -> None:
    config = json.loads((API_ROOT / "vercel.json").read_text())

    assert "builds" not in config
    assert len(config.get("crons", [])) <= 2
    assert {cron["path"] for cron in config["crons"]} == {
        "/api/v1/cron/hobby-data-refresh",
        "/api/v1/cron/hobby-analysis",
    }

    for function_config in config.get("functions", {}).values():
        assert 1 <= function_config["maxDuration"] <= 300
