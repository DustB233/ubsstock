# China Outbound Stock AI Analyzer API

FastAPI backend for the China Outbound Stock AI Analyzer.

## Local commands

- `uv sync`
- `uv run alembic upgrade head`
- `uv run uvicorn china_outbound_analyzer.main:app --reload`
- `uv run pytest`
- `uv run outbound-analyzer refresh-prices --lookback-days 400`
- `uv run outbound-analyzer refresh-news --limit 10`
- `uv run outbound-analyzer refresh-announcements --limit 12 --lookback-days 365`
- `uv run outbound-analyzer refresh-fundamentals`
- `uv run outbound-analyzer analyze-live`
- `uv run outbound-analyzer score-universe`

## Vercel

Deploy this directory as the backend Vercel project with Root Directory `apps/api`.

- Vercel serverless entrypoint: `api/index.py`
- Local Uvicorn app: `china_outbound_analyzer.main:app`
- Config: `vercel.json`
- Runtime dependencies: `requirements.txt`
- Production refresh: Vercel Hobby-safe Cron Jobs configured in `vercel.json` for `/api/v1/cron/daily-refresh` and `/api/v1/cron/fundamentals-analyze-score`

Required production env vars:

- `DATABASE_URL`
- `SYNC_DATABASE_URL`
- `CORS_ORIGINS`
- `CRON_SECRET`
- `OPENAI_API_KEY`
- `PRICE_DATA_PROVIDER=yahoo_finance`
- `NEWS_DATA_PROVIDER=google_news_rss`
- `ANNOUNCEMENTS_DATA_PROVIDER=cninfo`
- `FUNDAMENTALS_DATA_PROVIDER=akshare`
- `AI_ANALYSIS_PROVIDER=openai`

See the root `docs/deployment.md` for the full deployment checklist.
