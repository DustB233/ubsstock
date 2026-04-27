"""Vercel Python serverless entrypoint for the FastAPI backend."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from china_outbound_analyzer.main import app  # noqa: E402

__all__ = ["app"]
