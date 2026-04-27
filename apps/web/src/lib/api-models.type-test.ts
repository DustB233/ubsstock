import type {
  AIMethodologyResponse,
  ComparisonResponse,
  DashboardOverview,
  RecommendationSnapshotResponse,
  StockAnalysisResponse,
  StockDetailResponse,
  StockListItemResponse,
  StockTimeseriesResponse,
} from "@/lib/types";

const dashboardFixture = {
  as_of_date: "2026-04-13",
  stocks: [
    {
      slug: "catl",
      company_name: "CATL",
      primary_symbol: "300750.SZ",
      sector: "Battery Systems",
      latest_price: 245.12,
      return_1m: 0.05,
      return_3m: 0.12,
      return_1y: 0.34,
      pe_ttm: 22.4,
      pb: 4.8,
      ps_ttm: 2.7,
      total_score: 88.2,
      rank: 1,
    },
  ],
  recommendations: [
    {
      side: "LONG",
      slug: "catl",
      company_name: "CATL",
      explanation: "Mock long case",
      total_score: 88.2,
    },
    {
      side: "SHORT",
      slug: "jerry-group",
      company_name: "Jerry Group",
      explanation: "Mock short case",
      total_score: 24.1,
    },
  ],
} satisfies DashboardOverview;

const stockDetailFixture = {
  slug: "catl",
  symbol: "300750.SZ",
  company_name: "CATL",
  company_name_zh: "宁德时代",
  sector: "Battery Systems",
  outbound_theme: "Global EV supply chain",
  primary_symbol: "300750.SZ",
  latest_price: 245.12,
  returns: {
    return_1m: 0.05,
    return_3m: 0.12,
    return_6m: 0.2,
    return_1y: 0.34,
  },
  factor_scores: {
    fundamentals_quality: 82,
    valuation_attractiveness: 78,
    price_momentum: 74,
    news_sentiment: 80,
    globalization_strength: 92,
    total_score: 82.1,
    rank: 1,
  },
  valuation: {
    currency: "CNY",
    market_cap: 1000,
    pe_ttm: 22.4,
    pe_forward: 19.1,
    pb: 4.8,
    ps_ttm: 2.7,
    enterprise_value: 1200,
    ev_ebitda: 15.2,
    dividend_yield: 0.012,
    as_of_date: "2026-04-13",
    source: "AkShare Fundamentals",
    source_url: "https://www.akshare.xyz",
  },
  financial_snapshot: {
    as_of_date: "2026-03-31",
    report_date: "2026-03-31",
    report_period: "Q1 2026",
    fiscal_year: 2026,
    fiscal_period: "Q1",
    currency: "CNY",
    revenue: 56000,
    net_income: 9200,
    net_profit: 9200,
    gross_margin: 0.32,
    operating_margin: 0.18,
    roe: 0.18,
    roa: 0.09,
    debt_to_equity: 0.45,
    overseas_revenue_ratio: null,
    revenue_growth_yoy: 0.16,
    net_income_growth_yoy: 0.21,
    net_profit_growth_yoy: 0.21,
    source: "AkShare Fundamentals",
    source_url: "https://www.akshare.xyz",
  },
  identifiers: [
    {
      exchange_code: "SZSE",
      composite_symbol: "300750.SZ",
      identifier_type: "A_SHARE",
      currency: "CNY",
      is_primary: true,
    },
  ],
  announcements: [
    {
      title: "CATL 2026 first-quarter report",
      url: "https://static.cninfo.com.cn/finalpage/2026-04-16/1224899411.PDF",
      published_at: "2026-04-16T03:42:09Z",
      as_of_date: "2026-04-16",
      summary: null,
      provider: "CNInfo Disclosures",
      source_url:
        "https://www.cninfo.com.cn/new/disclosure/detail?stockCode=300750&announcementId=1224899411",
      exchange_code: "SZSE",
      category: null,
      language: "zh",
    },
  ],
} satisfies StockDetailResponse;

const timeseriesFixture = {
  slug: "catl",
  symbol: "300750.SZ",
  range: "1y",
  points: [{ trading_date: "2026-04-13", close: 245.12, volume: 1200000 }],
  empty_state: null,
} satisfies StockTimeseriesResponse;

const analysisFixture = {
  slug: "catl",
  symbol: "300750.SZ",
  schema_version: "analysis-v2",
  generated_at: "2026-04-13T18:00:00Z",
  analysis_mode: "live_ai",
  model_provider: "openai",
  model_name: "gpt-5.4-mini",
  prompt_version: "live-v1",
  missing_inputs: [],
  freshness: {
    latest_news_at: "2026-04-13T10:00:00Z",
    latest_announcement_at: "2026-04-16T03:42:09Z",
    latest_price_date: "2026-04-13",
    valuation_as_of_date: "2026-04-13",
    fundamentals_report_date: "2026-03-31",
    scoring_as_of_date: "2026-04-13",
  },
  summary: "Mock summary",
  summary_evidence: [
    {
      reference_id: "news-1",
      reference_type: "news_article",
      label: "CATL overseas demand strengthens",
      url: "https://demo.local/news/catl/1",
      provider: "Mock Wire",
      published_at: "2026-04-13T10:00:00Z",
      source_url: "https://demo.local/news",
      metric_key: null,
      metric_value: null,
      metric_unit: null,
      as_of_date: null,
    },
  ],
  top_news_themes: [
    {
      theme: "Global Demand & Exports",
      article_count: 3,
      sentiment_score: 0.6,
      sentiment_label: "POSITIVE",
      summary: "3 recent articles center on global demand and exports.",
      evidence: [
        {
          reference_id: "news-1",
          reference_type: "news_article",
          label: "CATL overseas demand strengthens",
          url: "https://demo.local/news/catl/1",
          provider: "Mock Wire",
          published_at: "2026-04-13T10:00:00Z",
          source_url: "https://demo.local/news",
          metric_key: null,
          metric_value: null,
          metric_unit: null,
          as_of_date: null,
        },
      ],
    },
  ],
  valuation_summary: "Mock valuation summary",
  valuation_evidence: [
    {
      reference_id: "metric:pe_ttm",
      reference_type: "metric",
      label: "PE (TTM)",
      url: null,
      provider: null,
      published_at: null,
      source_url: null,
      metric_key: "pe_ttm",
      metric_value: 22.4,
      metric_unit: "x",
      as_of_date: "2026-04-13",
    },
  ],
  bull_case: "Mock bull case",
  bull_case_evidence: [
    {
      reference_id: "metric:roe",
      reference_type: "metric",
      label: "ROE",
      url: null,
      provider: null,
      published_at: null,
      source_url: null,
      metric_key: "roe",
      metric_value: 18,
      metric_unit: "%",
      as_of_date: "2026-03-31",
    },
  ],
  bear_case: "Mock bear case",
  bear_case_evidence: [
    {
      reference_id: "metric:ps_ttm",
      reference_type: "metric",
      label: "PS (TTM)",
      url: null,
      provider: null,
      published_at: null,
      source_url: null,
      metric_key: "ps_ttm",
      metric_value: 2.7,
      metric_unit: "x",
      as_of_date: "2026-04-13",
    },
  ],
  key_risks: ["Risk 1", "Risk 2"],
  risk_evidence: [
    {
      risk: "Overseas demand execution risk",
      evidence: [
        {
          reference_id: "news-1",
          reference_type: "news_article",
          label: "CATL overseas demand strengthens",
          url: "https://demo.local/news/catl/1",
          provider: "Mock Wire",
          published_at: "2026-04-13T10:00:00Z",
          source_url: "https://demo.local/news",
          metric_key: null,
          metric_value: null,
          metric_unit: null,
          as_of_date: null,
        },
      ],
    },
  ],
  keywords: ["demand", "global"],
  keyword_insights: [
    {
      keyword: "demand",
      mentions: 3,
      evidence: [
        {
          reference_id: "news-1",
          reference_type: "news_article",
          label: "CATL overseas demand strengthens",
          url: "https://demo.local/news/catl/1",
          provider: "Mock Wire",
          published_at: "2026-04-13T10:00:00Z",
          source_url: "https://demo.local/news",
          metric_key: null,
          metric_value: null,
          metric_unit: null,
          as_of_date: null,
        },
      ],
    },
  ],
  sentiment_label: "POSITIVE",
  sentiment_score: 0.8,
  sentiment_evidence: [
    {
      reference_id: "news-1",
      reference_type: "news_article",
      label: "CATL overseas demand strengthens",
      url: "https://demo.local/news/catl/1",
      provider: "Mock Wire",
      published_at: "2026-04-13T10:00:00Z",
      source_url: "https://demo.local/news",
      metric_key: null,
      metric_value: null,
      metric_unit: null,
      as_of_date: null,
    },
  ],
  source_references: [
    {
      reference_id: "news-1",
      reference_type: "news_article",
      label: "CATL overseas demand strengthens",
      url: "https://demo.local/news/catl/1",
      provider: "Mock Wire",
      published_at: "2026-04-13T10:00:00Z",
      source_url: "https://demo.local/news",
      metric_key: null,
      metric_value: null,
      metric_unit: null,
      as_of_date: null,
    },
  ],
  source_links: ["https://demo.local/news/catl/1"],
} satisfies StockAnalysisResponse;

const aiMethodologyFixture = {
  schema_version: "ai-methodology-v2",
  headline: "AI is an accelerator for evidence synthesis.",
  sections: [
    {
      title: "Strengths of AI in stock analysis",
      body: "Mock body",
      bullets: ["Bullet 1"],
      tone: "strength",
    },
  ],
} satisfies AIMethodologyResponse;

const recommendationFixture = {
  methodology_version: "transparent-mock-v1",
  generated_at: "2026-04-14T12:00:00Z",
  items: [
    {
      side: "LONG",
      slug: "catl",
      symbol: "300750.SZ",
      company_name: "CATL",
      company_name_zh: "宁德时代",
      sector: "Battery Systems",
      outbound_theme: "Global EV battery leadership and cross-border manufacturing expansion.",
      explanation: "CATL is the long recommendation.",
      confidence_score: 0.64,
      latest_price: 245.12,
      returns: stockDetailFixture.returns,
      factor_scores: stockDetailFixture.factor_scores,
      valuation: stockDetailFixture.valuation,
      financial_snapshot: stockDetailFixture.financial_snapshot,
      evidence_buckets: [
        {
          key: "valuation",
          title: "Valuation evidence",
          summary: "Mock valuation summary",
          references: analysisFixture.valuation_evidence,
        },
      ],
      analysis: analysisFixture,
      key_risks: analysisFixture.key_risks,
      source_links: analysisFixture.source_links,
    },
  ],
} satisfies RecommendationSnapshotResponse;

const stockListFixture = {
  slug: "byd",
  company_name: "BYD",
  company_name_zh: "比亚迪",
  sector: "EV + Energy Storage",
  outbound_theme: "Global passenger EV and battery expansion",
  primary_symbol: "1211.HK",
  identifiers: [
    {
      exchange_code: "HKEX",
      composite_symbol: "1211.HK",
      identifier_type: "HK",
      currency: "HKD",
      is_primary: true,
    },
    {
      exchange_code: "SZSE",
      composite_symbol: "002594.SZ",
      identifier_type: "A_SHARE",
      currency: "CNY",
      is_primary: false,
    },
  ],
  valuation: stockDetailFixture.valuation,
  financial_snapshot: stockDetailFixture.financial_snapshot,
} satisfies StockListItemResponse;

const comparisonFixture = {
  requested_symbols: ["300750.SZ", "1211.HK"],
  rows: [
    {
      slug: "catl",
      symbol: "300750.SZ",
      company_name: "CATL",
      sector: "Battery Systems",
      factor_scores: stockDetailFixture.factor_scores,
      valuation: stockDetailFixture.valuation,
      financial_snapshot: stockDetailFixture.financial_snapshot,
      sentiment_label: "POSITIVE",
      sentiment_score: 0.8,
    },
  ],
  highlights: {
    most_attractive_symbol: "300750.SZ",
    most_attractive_name: "CATL",
    least_attractive_symbol: "1211.HK",
    least_attractive_name: "BYD",
  },
} satisfies ComparisonResponse;

void dashboardFixture;
void stockDetailFixture;
void timeseriesFixture;
void analysisFixture;
void aiMethodologyFixture;
void recommendationFixture;
void stockListFixture;
void comparisonFixture;
