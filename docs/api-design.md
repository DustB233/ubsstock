# API Design

## Base URL

`/api/v1`

## Principles

- Read models are page-oriented and presentation-friendly
- Business logic stays in services, not route handlers
- Endpoints remain usable even before live adapters are connected
- Placeholder responses keep frontend development unblocked

## Endpoints

### Health

- `GET /health`
  - service status check

### Metadata

- `GET /metadata/dashboard-preview`
  - returns universe cards and placeholder long/short cards
- `GET /metadata/ai-limitations`
  - returns the content sections for the AI limitations page

### Dashboard

- `GET /dashboard/overview`
  - returns dashboard rows with latest price, returns, valuation snapshot, rank, total score, and long/short cards

### Stocks

- `GET /stocks`
  - returns the 15-stock universe with identifier metadata
- `GET /stocks/{slug}`
  - returns stock detail read model
- `GET /stocks/{slug}/price-history`
  - returns chart-ready price points
- `GET /stocks/{slug}/news`
  - returns stock-linked news feed
- `GET /stocks/{slug}/announcements`
  - returns company announcement feed

### Comparison

- `GET /compare?slugs=catl&slugs=byd`
  - returns a normalized metric grid for multi-stock comparison

### Recommendations

- `GET /recommendations/latest`
  - returns the current methodology version and the two recommendation slots

### Jobs

- `POST /jobs/refresh`
  - accepts a refresh request for orchestration

## Example response shapes

### `GET /metadata/dashboard-preview`

```json
{
  "universe": [
    {
      "slug": "catl",
      "companyName": "CATL",
      "primarySymbol": "300750.SZ",
      "exchanges": ["SZSE", "HKEX"],
      "sector": "Battery Systems",
      "geographyAngle": "Global EV battery leadership and cross-border manufacturing expansion."
    }
  ],
  "recommendations": [
    {
      "side": "long",
      "title": "Long candidate placeholder",
      "explanation": "The API contract is ready; the final long idea will appear after scoring runs are implemented."
    },
    {
      "side": "short",
      "title": "Short candidate placeholder",
      "explanation": "The short idea will be backed by factor scores, source links, and traceable AI reasoning."
    }
  ]
}
```

### `GET /stocks/{slug}`

```json
{
  "slug": "byd",
  "company_name": "BYD",
  "company_name_zh": "比亚迪",
  "sector": "EV + Energy Storage",
  "outbound_theme": "China auto export scale, overseas assembly, and battery ecosystem reach.",
  "identifiers": [
    {
      "exchange_code": "SZSE",
      "composite_symbol": "002594.SZ",
      "identifier_type": "A_SHARE",
      "currency": "CNY",
      "is_primary": false
    }
  ],
  "valuation_metrics": [],
  "financial_metrics": [],
  "ai_summary": "AI summary pipeline will populate this field after Phase 3 processing.",
  "bull_case": "Bull case generation will merge valuation, momentum, and globalization evidence.",
  "bear_case": "Bear case generation will surface downside drivers and adverse sentiment clusters.",
  "key_risks": [
    "Live data ingestion is not connected yet.",
    "Recommendation engine is still pending Phase 4 scoring logic."
  ],
  "announcements": [],
  "news": []
}
```

### `POST /jobs/refresh`

```json
{
  "job_type": "DAILY_REFRESH",
  "trigger_source": "manual"
}
```

Response:

```json
{
  "job_id": "uuid",
  "status": "PENDING",
  "job_type": "DAILY_REFRESH",
  "created_at": "2026-04-13T18:00:00Z",
  "message": "Refresh job accepted. Background orchestration arrives in Phase 2."
}
```

## Planned extensions

- Auth or internal-only write endpoints for admin refresh control
- Historical score and recommendation timeline endpoints
- Filtered news cluster and AI artifact retrieval endpoints
- Read-model endpoints for stock detail, comparison, and recommendation drill-down
