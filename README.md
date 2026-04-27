# China Outbound Stock AI Analyzer

Production-quality full-stack research app for a fixed universe of 15 China outbound-related stocks. The product is designed to recommend exactly one long idea and one short idea, with transparent factor scoring, traceable AI outputs, and source-backed rationale.

## Current status

The app is feature-complete for the competition demo and prepared for GitHub + Vercel deployment:

- Monorepo scaffold with `apps/web` and `apps/api`
- Premium presentation-oriented Next.js shell and final summary routes
- FastAPI backend with route contracts and OpenAPI docs
- PostgreSQL schema modeled with SQLAlchemy and Alembic
- Universe registry for the 15-stock coverage list
- Adapter-backed real price, news, fundamentals, and announcement ingestion
- Configurable real price ingestion via Yahoo Finance with mock fallback
- Configurable real news ingestion via Google News RSS with mock fallback
- Configurable real fundamentals ingestion via AkShare / Eastmoney / Baidu with mock fallback
- Configurable real announcement ingestion via CNInfo with mock fallback
- Live AI analysis pipeline with deterministic structured artifacts and evidence references
- Vercel Hobby-safe cron endpoints for production data refresh without an always-on scheduler
- CLI commands for universe seeding and mock refresh ingestion
- Transparent weighted scoring and long/short recommendation selection
- Dashboard, stock detail, compare, methodology, recommendation, summary, and admin status pages
- Dockerfiles, `docker-compose.yml`, and env examples
- API and frontend verification checks

## Monorepo layout

```text
.
├── apps
│   ├── api
│   │   ├── migrations
│   │   ├── src/china_outbound_analyzer
│   │   │   ├── api
│   │   │   ├── core
│   │   │   ├── models
│   │   │   ├── repositories
│   │   │   ├── schemas
│   │   │   ├── seeds
│   │   │   └── services
│   │   └── tests
│   └── web
│       └── src
│           ├── app
│           ├── components
│           └── lib
├── docs
│   ├── api-design.md
│   ├── architecture.md
│   └── data-model.md
├── docker-compose.yml
└── README.md
```

## Tech stack

- Frontend: Next.js 16, TypeScript, Tailwind CSS 4
- Backend: FastAPI, SQLAlchemy 2, Alembic, pandas
- Database: PostgreSQL
- Testing: pytest for API contracts
- Packaging: npm for web, `uv` for Python

## Local setup

### 1. API

```bash
cd /Users/jjh/Desktop/123/apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run outbound-analyzer seed-universe
uv run outbound-analyzer refresh-prices --lookback-days 400
uv run outbound-analyzer refresh-news --limit 10
uv run outbound-analyzer refresh-announcements --limit 12 --lookback-days 365
uv run outbound-analyzer refresh-fundamentals
uv run outbound-analyzer analyze-live
uv run outbound-analyzer score-universe
uv run uvicorn china_outbound_analyzer.main:app --reload --host 0.0.0.0 --port 8001
```

Open API docs at [http://localhost:8001/docs](http://localhost:8001/docs).

To use live price history instead of deterministic mock prices, set `PRICE_DATA_PROVIDER=yahoo_finance` in `apps/api/.env`. The `refresh-prices` command will automatically fall back to the mock adapter if the live provider times out or fails.

To use live company news instead of deterministic mock news, set `NEWS_DATA_PROVIDER=google_news_rss` in `apps/api/.env`. The `refresh-news` command will automatically fall back to the mock news adapter if the live provider times out or fails.

### 2. Web

```bash
cd /Users/jjh/Desktop/123/apps/web
cp .env.local.example .env.local
npm install
npm run dev
```

Open the app at [http://localhost:3000](http://localhost:3000).

### 3. Optional Docker flow

```bash
cd /Users/jjh/Desktop/123
cp .env.example .env
docker compose up --build
```

## Verified commands

These commands were run successfully during Phase 1:

- `cd /Users/jjh/Desktop/123/apps/api && uv run pytest -q`
- `cd /Users/jjh/Desktop/123/apps/api && uv run ruff check`
- `cd /Users/jjh/Desktop/123/apps/api && uv run outbound-analyzer --help`
- `cd /Users/jjh/Desktop/123/apps/api && uv run pytest -q`
- `cd /Users/jjh/Desktop/123/apps/web && npm run lint`
- `cd /Users/jjh/Desktop/123/apps/web && npm run typecheck`
- `cd /Users/jjh/Desktop/123/apps/web && npm run build`

Run all release checks with:

```bash
./scripts/preflight.sh
```

## Product blueprint

- Dashboard: all 15 stocks, returns, valuation snapshot, ranking, long card, short card
- Stock detail: chart, valuation, financial trends, news, announcements, AI thesis, risks
- Comparison: PE, PB, PS, revenue growth, net profit growth, ROE, gross margin, momentum, sentiment
- AI modules: clustering, sentiment, keywords, valuation summary, final thesis summary
- Scoring engine:
  - fundamentals quality: 25%
  - valuation attractiveness: 25%
  - price and momentum: 15%
  - news and event sentiment: 20%
  - outbound and globalization strength: 15%

## Key design principles

- Data-source access must go through adapters
- UI pages should consume API contracts, not embed business logic
- AI outputs must be explainable, traceable, and source-backed
- Raw data and processed features are stored separately
- Recommendation runs must preserve supporting metrics and links
- Production refresh must use Vercel Cron Jobs, not a long-running in-process scheduler

## Deployment

This repo is designed for two Vercel projects from the same GitHub monorepo:

- Frontend project Root Directory: `apps/web`
- Backend project Root Directory: `apps/api`

Production refresh is handled by Vercel Cron Jobs against protected FastAPI cron endpoints. The default `apps/api/vercel.json` stays within Vercel Hobby constraints by capping `maxDuration` at 300 seconds and scheduling two small rotating/batched cron routes instead of one long all-in-one refresh. The local scheduler is still available for local development, but production does not depend on an always-on process.

See [docs/deployment.md](docs/deployment.md) for the full GitHub publishing checklist, Vercel environment variables, cron schedules, and deployment steps.

## Notes

- Do not commit `.env` files. Use `.env.example` and Vercel project environment variables.
- The app intentionally returns `null` for unavailable provider fields instead of fabricating metrics.
- If `pytest` crashes under a local Anaconda Python on macOS, recreate the API environment with a Homebrew Python interpreter before retrying `uv sync`.
