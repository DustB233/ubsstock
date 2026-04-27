# GitHub and Vercel Deployment Guide

This repo is deployment-ready as a two-project Vercel monorepo:

- Frontend project root: `apps/web`
- Backend/API project root: `apps/api`
- Persistent database: external PostgreSQL, for example Neon, Supabase, Railway, or another managed Postgres provider
- Production refresh: Vercel Cron Jobs hitting protected FastAPI endpoints
- Local refresh: existing CLI and local scheduler remain available for development only

## 1. GitHub Readiness

Before publishing:

```bash
cd /path/to/china-outbound-stock-ai-analyzer
./scripts/preflight.sh
```

Do not commit local env files. The repo `.gitignore` excludes `.env`, `.env.*`, `.env.local`, `.vercel`, caches, virtualenvs, build outputs, and key/cert files. Only `.env.example` and `.env.local.example` should be committed.

First-time GitHub publish checklist:

```bash
git init
git add .
git status
git commit -m "Prepare China Outbound Stock AI Analyzer for deployment"
git branch -M main
git remote add origin git@github.com:<your-org-or-user>/<your-repo>.git
git push -u origin main
```

If you already have a remote, preserve it and only run:

```bash
git remote -v
git add .
git commit -m "Prepare Vercel deployment and cron refresh"
git push
```

## 2. Backend Vercel Project

Create one Vercel project for the backend.

- Import the same GitHub repo.
- Set Root Directory to `apps/api`.
- Use the included `apps/api/vercel.json`.
- The Vercel serverless entrypoint is `apps/api/api/index.py`.
- Local development still uses `china_outbound_analyzer.main:app` with Uvicorn.
- Production cron jobs are defined in `apps/api/vercel.json`.

Backend environment variables:

```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB?ssl=require
SYNC_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DB?sslmode=require
CORS_ORIGINS=https://your-web-project.vercel.app
CRON_SECRET=replace-with-a-long-random-secret
OPENAI_API_KEY=replace-with-your-openai-key

PRICE_DATA_PROVIDER=yahoo_finance
NEWS_DATA_PROVIDER=google_news_rss
ANNOUNCEMENTS_DATA_PROVIDER=cninfo
FUNDAMENTALS_DATA_PROVIDER=akshare

AI_ANALYSIS_PROVIDER=openai
AI_ANALYSIS_MODEL=gpt-5.4-mini
AI_ANALYSIS_BASE_URL=https://api.openai.com/v1
AI_ANALYSIS_REQUEST_TIMEOUT_SECONDS=45
AI_ANALYSIS_MAX_RETRIES=2
AI_ANALYSIS_REASONING_EFFORT=medium
AI_ANALYSIS_VERBOSITY=low

CRON_AUTO_MIGRATE_ENABLED=true
CRON_PRICES_LOOKBACK_DAYS=400
CRON_NEWS_LIMIT=10
CRON_ANNOUNCEMENTS_LIMIT=12
CRON_ANNOUNCEMENTS_LOOKBACK_DAYS=365
CRON_AI_BATCH_SIZE=3
SCHEDULER_RUNNING_JOB_STALE_AFTER_SECONDS=7200
```

If your Postgres provider only gives a `postgres://` or `postgresql://` URL with `sslmode=require`, the backend normalizes it internally for both asyncpg and psycopg. The explicit SQLAlchemy driver URLs above are still the clearest production setup.

Runtime smoke checks after deployment:

- `https://your-api-project.vercel.app/`
- `https://your-api-project.vercel.app/api/v1/health`

These health routes do not connect to Postgres. They should return JSON even if database-backed endpoints still need environment fixes.

## 3. Frontend Vercel Project

Create a second Vercel project for the frontend.

- Import the same GitHub repo.
- Set Root Directory to `apps/web`.
- Framework preset: Next.js.
- Use the included `apps/web/vercel.json`.
- Set the API URL to the deployed backend project URL.

Frontend environment variables:

```env
API_BASE_URL=https://your-api-project.vercel.app/api/v1
NEXT_PUBLIC_API_BASE_URL=https://your-api-project.vercel.app/api/v1
```

The production frontend intentionally does not fall back to localhost. If these values are missing, production builds will fail instead of silently rendering stale local fallback data.

## 4. Vercel Cron Jobs

The backend project is configured for Vercel Hobby deployment by default:

- `apps/api/vercel.json` does not declare `builds`, `functions`, or `maxDuration`; Vercel auto-detects `apps/api/api/index.py` as the Python serverless function.
- Cron configuration lives in `apps/api/vercel.json`, because the backend Vercel project Root Directory is `apps/api`.
- Only two cron schedules are defined, which keeps the project within the Hobby cron-job limit.
- `/api/v1/cron/fundamentals-analyze-score` combines the post-data fundamentals and AI/scoring steps so the deployment stays automatic without requiring a third Hobby cron job.

The scheduled production cron jobs are:

| Path | Schedule | Purpose |
| --- | --- | --- |
| `/api/v1/cron/daily-refresh` | `30 10 * * *` | Daily price, news, and announcement refresh after China/HK market close |
| `/api/v1/cron/fundamentals-analyze-score` | `30 11 * * *` | Daily fundamentals refresh, then live AI analysis and recommendation scoring |

This is intentionally conservative for the free/Hobby plan. Vercel Hobby supports two cron jobs, so the individual `/api/v1/cron/fundamentals` and `/api/v1/cron/analyze-score` endpoints remain available for manual testing while the scheduled production path combines them. If `/api/v1/cron/fundamentals-analyze-score` exceeds Hobby function duration in production, switch the second schedule back to `/api/v1/cron/hobby-analysis` or upgrade the cron/function limits.

Additional protected endpoints are available for targeted cron/manual operations if needed:

- `/api/v1/cron/bootstrap`
- `/api/v1/cron/prices`
- `/api/v1/cron/news`
- `/api/v1/cron/announcements`
- `/api/v1/cron/fundamentals`
- `/api/v1/cron/analyze-live`
- `/api/v1/cron/analyze-live-batch`
- `/api/v1/cron/score-universe`
- `/api/v1/cron/daily-refresh`
- `/api/v1/cron/analyze-score`
- `/api/v1/cron/fundamentals-analyze-score`

All cron routes require:

```http
Authorization: Bearer <CRON_SECRET>
```

Vercel Cron Jobs sends that header automatically when `CRON_SECRET` is configured on the project. Unauthorized requests return `401`, and missing `CRON_SECRET` returns `503`.

The cron runner:

- Applies Alembic migrations when `CRON_AUTO_MIGRATE_ENABLED=true`.
- Seeds the fixed universe before refreshes.
- Reuses existing `refresh_jobs` locking to prevent overlapping runs.
- Treats refresh services as idempotent upserts.
- Runs scoring only after all active stocks have live analysis for the latest complete data cycle.
- Skips analysis if required price/news/announcement/fundamental refreshes have never completed.

Manual production cron smoke tests:

```bash
API_URL=https://ubsstock.vercel.app
curl "$API_URL/api/v1/cron/bootstrap" -H "Authorization: Bearer $CRON_SECRET"
curl "$API_URL/api/v1/cron/daily-refresh" -H "Authorization: Bearer $CRON_SECRET"
curl "$API_URL/api/v1/cron/fundamentals" -H "Authorization: Bearer $CRON_SECRET"
curl "$API_URL/api/v1/cron/analyze-score" -H "Authorization: Bearer $CRON_SECRET"
curl "$API_URL/api/v1/cron/fundamentals-analyze-score" -H "Authorization: Bearer $CRON_SECRET"
```

To verify automatic cron registration in Vercel:

1. Open the backend Vercel project, not the frontend project.
2. Confirm the project Root Directory is `apps/api`.
3. Open Settings, then Environment Variables, and confirm `CRON_SECRET` exists for Production.
4. Open the latest Production Deployment and check the Functions or Cron Jobs panel for `/api/v1/cron/daily-refresh` and `/api/v1/cron/fundamentals-analyze-score`.
5. After the scheduled UTC window passes, inspect deployment logs for `Starting Vercel cron job daily-refresh` and `Starting Vercel cron job fundamentals-analyze-score`.

## 5. Local Commands

Local one-time refresh:

```bash
cd apps/api
uv run alembic upgrade head
uv run outbound-analyzer seed-universe
uv run outbound-analyzer refresh-prices --lookback-days 400
uv run outbound-analyzer refresh-news --limit 10
uv run outbound-analyzer refresh-announcements --limit 12 --lookback-days 365
uv run outbound-analyzer refresh-fundamentals
uv run outbound-analyzer analyze-live
uv run outbound-analyzer score-universe
```

Local scheduler for development only:

```bash
cd apps/api
uv run outbound-analyzer run-scheduler
```

Production does not rely on this long-running scheduler.

## 6. Local Cron Smoke Test

With API running locally and `CRON_SECRET` set:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" \
  http://127.0.0.1:8001/api/v1/cron/bootstrap
```

Do not put real secrets into committed files. Use Vercel project environment variables for production credentials.
