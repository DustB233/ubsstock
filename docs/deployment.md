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
- The FastAPI entrypoint is `apps/api/app.py`.
- Production cron jobs are defined in `apps/api/vercel.json`.

Backend environment variables:

```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB?ssl=require
SYNC_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DB?ssl=require
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

If your Postgres provider only gives a `postgres://` or `postgresql://` URL, the backend normalizes it internally when possible, but the explicit SQLAlchemy driver URLs above are the clearest production setup.

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

The backend project is configured for Vercel Hobby limits by default:

- `maxDuration` is capped at `300` seconds in `apps/api/vercel.json`.
- Only two cron schedules are defined, which keeps the project within the Hobby cron-job limit.
- Long workflows are split into rotating/batched endpoints instead of one oversized function invocation.

The scheduled production cron jobs are:

| Path | Schedule | Purpose |
| --- | --- | --- |
| `/api/v1/cron/hobby-data-refresh` | `30 10 * * *` | Runs one stale data refresh per invocation: prices, news, announcements, or fundamentals |
| `/api/v1/cron/hobby-analysis` | `30 11 * * *` | Runs the next AI analysis batch, then scores once all 15 stocks have analysis for the latest complete data cycle; if data inputs are missing, this slot performs the next data catch-up refresh instead |

This is intentionally conservative for the free/Hobby plan. It keeps automatic refresh enabled with no post-deploy commands, but full universe refreshes may complete over multiple scheduled invocations. On a brand-new database, the two daily cron slots first catch up prices, news, announcements, and fundamentals, then progress through AI analysis batches and scoring. Increase `CRON_AI_BATCH_SIZE` only if your provider calls reliably finish below 300 seconds.

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
