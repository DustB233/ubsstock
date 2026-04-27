export type RecommendationSide = "LONG" | "SHORT";
export type StockRange = "1m" | "3m" | "6m" | "1y";

export interface DashboardStockRow {
  slug: string;
  company_name: string;
  primary_symbol: string;
  sector: string;
  latest_price: number | null;
  return_1m: number | null;
  return_3m: number | null;
  return_1y: number | null;
  pe_ttm: number | null;
  pb: number | null;
  ps_ttm: number | null;
  total_score: number | null;
  rank: number | null;
}

export interface DashboardRecommendationCard {
  side: RecommendationSide;
  slug: string | null;
  company_name: string | null;
  explanation: string;
  total_score: number | null;
}

export interface DashboardOverview {
  as_of_date: string | null;
  stocks: DashboardStockRow[];
  recommendations: DashboardRecommendationCard[];
}

export interface StockIdentifier {
  exchange_code: string;
  composite_symbol: string;
  identifier_type: string;
  currency: string;
  is_primary: boolean;
}

export interface ReturnSnapshot {
  return_1m: number | null;
  return_3m: number | null;
  return_6m: number | null;
  return_1y: number | null;
}

export interface FactorScoreBreakdown {
  fundamentals_quality: number | null;
  valuation_attractiveness: number | null;
  price_momentum: number | null;
  news_sentiment: number | null;
  globalization_strength: number | null;
  total_score: number | null;
  rank: number | null;
}

export interface ValuationSnapshot {
  currency: string | null;
  market_cap: number | null;
  pe_ttm: number | null;
  pe_forward: number | null;
  pb: number | null;
  ps_ttm: number | null;
  enterprise_value: number | null;
  ev_ebitda: number | null;
  dividend_yield: number | null;
  as_of_date: string | null;
  source: string | null;
  source_url: string | null;
}

export interface FinancialSnapshot {
  as_of_date: string | null;
  report_date: string | null;
  report_period: string | null;
  fiscal_year: number | null;
  fiscal_period: string | null;
  currency: string | null;
  revenue: number | null;
  net_income: number | null;
  net_profit: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  roe: number | null;
  roa: number | null;
  debt_to_equity: number | null;
  overseas_revenue_ratio: number | null;
  revenue_growth_yoy: number | null;
  net_income_growth_yoy: number | null;
  net_profit_growth_yoy: number | null;
  source: string | null;
  source_url: string | null;
}

export interface StockDetailResponse {
  slug: string;
  symbol: string;
  company_name: string;
  company_name_zh: string | null;
  sector: string;
  outbound_theme: string;
  primary_symbol: string;
  latest_price: number | null;
  returns: ReturnSnapshot;
  factor_scores: FactorScoreBreakdown;
  valuation: ValuationSnapshot;
  financial_snapshot: FinancialSnapshot;
  identifiers: StockIdentifier[];
  announcements: StockAnnouncementItem[];
}

export interface StockPricePoint {
  trading_date: string;
  close: number | null;
  volume: number | null;
}

export interface EmptyState {
  message: string;
}

export interface StockTimeseriesResponse {
  slug: string;
  symbol: string;
  range: StockRange;
  points: StockPricePoint[];
  empty_state: EmptyState | null;
}

export interface StockNewsItem {
  title: string;
  url: string;
  published_at: string;
  summary: string | null;
  provider: string | null;
  source_url: string | null;
  sentiment_label: string | null;
}

export interface StockNewsFeedResponse {
  slug: string;
  symbol: string;
  items: StockNewsItem[];
  empty_state: EmptyState | null;
}

export interface StockAnnouncementItem {
  title: string;
  url: string;
  published_at: string;
  as_of_date: string | null;
  summary: string | null;
  provider: string | null;
  source_url: string | null;
  exchange_code: string | null;
  category: string | null;
  language: string | null;
}

export interface AnalysisEvidenceReference {
  reference_id: string;
  reference_type: "news_article" | "announcement" | "metric";
  label: string;
  url: string | null;
  provider: string | null;
  published_at: string | null;
  source_url: string | null;
  metric_key: string | null;
  metric_value: number | string | null;
  metric_unit: string | null;
  as_of_date: string | null;
}

export interface AnalysisTheme {
  theme: string;
  article_count: number;
  sentiment_score: number | null;
  sentiment_label: string | null;
  summary: string;
  evidence: AnalysisEvidenceReference[];
}

export interface AnalysisKeywordInsight {
  keyword: string;
  mentions: number;
  evidence: AnalysisEvidenceReference[];
}

export interface AnalysisRiskInsight {
  risk: string;
  evidence: AnalysisEvidenceReference[];
}

export interface AnalysisFreshness {
  latest_news_at: string | null;
  latest_announcement_at: string | null;
  latest_price_date: string | null;
  valuation_as_of_date: string | null;
  fundamentals_report_date: string | null;
  scoring_as_of_date: string | null;
}

export interface StockAnalysisResponse {
  slug: string;
  symbol: string;
  schema_version: string;
  generated_at: string | null;
  analysis_mode: string | null;
  model_provider: string | null;
  model_name: string | null;
  prompt_version: string | null;
  missing_inputs: string[];
  freshness: AnalysisFreshness;
  summary: string;
  summary_evidence: AnalysisEvidenceReference[];
  top_news_themes: AnalysisTheme[];
  valuation_summary: string;
  valuation_evidence: AnalysisEvidenceReference[];
  bull_case: string;
  bull_case_evidence: AnalysisEvidenceReference[];
  bear_case: string;
  bear_case_evidence: AnalysisEvidenceReference[];
  key_risks: string[];
  risk_evidence: AnalysisRiskInsight[];
  keywords: string[];
  keyword_insights: AnalysisKeywordInsight[];
  sentiment_label: string | null;
  sentiment_score: number | null;
  sentiment_evidence: AnalysisEvidenceReference[];
  source_references: AnalysisEvidenceReference[];
  source_links: string[];
}

export interface AIMethodologySection {
  title: string;
  body: string;
  bullets: string[];
  tone: string;
}

export interface AIMethodologyResponse {
  schema_version: string;
  headline: string;
  sections: AIMethodologySection[];
}

export interface AdminJobStatusItem {
  job_name: string;
  job_type: string;
  enabled: boolean;
  interval_minutes: number | null;
  latest_status: string | null;
  trigger_source: string | null;
  last_run_started_at: string | null;
  last_run_completed_at: string | null;
  last_success_at: string | null;
  error_message: string | null;
  is_running: boolean;
}

export interface AdminJobStatusResponse {
  generated_at: string;
  jobs: AdminJobStatusItem[];
}

export interface RecommendationEvidenceBucket {
  key: string;
  title: string;
  summary: string;
  references: AnalysisEvidenceReference[];
}

export interface RecommendationItem {
  side: RecommendationSide;
  slug: string | null;
  symbol: string | null;
  company_name: string | null;
  company_name_zh: string | null;
  sector: string | null;
  outbound_theme: string | null;
  explanation: string;
  confidence_score: number | null;
  latest_price: number | null;
  returns: ReturnSnapshot;
  factor_scores: FactorScoreBreakdown;
  valuation: ValuationSnapshot;
  financial_snapshot: FinancialSnapshot;
  evidence_buckets: RecommendationEvidenceBucket[];
  analysis: StockAnalysisResponse;
  key_risks: string[];
  source_links: string[];
}

export interface RecommendationSnapshotResponse {
  methodology_version: string;
  generated_at: string | null;
  items: RecommendationItem[];
}

export interface StockListItemResponse {
  slug: string;
  company_name: string;
  company_name_zh: string | null;
  sector: string;
  outbound_theme: string;
  primary_symbol: string;
  identifiers: StockIdentifier[];
  valuation?: ValuationSnapshot | null;
  financial_snapshot?: FinancialSnapshot | null;
}

export interface ComparisonRowResponse {
  slug: string;
  symbol: string;
  company_name: string;
  sector: string;
  factor_scores: FactorScoreBreakdown;
  valuation: ValuationSnapshot;
  financial_snapshot: FinancialSnapshot;
  sentiment_label: string | null;
  sentiment_score: number | null;
}

export interface ComparisonHighlightsResponse {
  most_attractive_symbol: string | null;
  most_attractive_name: string | null;
  least_attractive_symbol: string | null;
  least_attractive_name: string | null;
}

export interface ComparisonResponse {
  requested_symbols: string[];
  rows: ComparisonRowResponse[];
  highlights: ComparisonHighlightsResponse;
}
