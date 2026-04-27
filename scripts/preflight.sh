#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Checking backend..."
cd "$ROOT_DIR/apps/api"
uv run ruff check
uv run pytest -q

echo "Checking frontend..."
cd "$ROOT_DIR/apps/web"
npm run lint
npm run typecheck
npm run build

echo "Preflight checks passed."
