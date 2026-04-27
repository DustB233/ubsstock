import type {
  AdminJobStatusResponse,
  AIMethodologyResponse,
  ComparisonResponse,
  DashboardOverview,
  RecommendationSnapshotResponse,
  StockAnalysisResponse,
  StockDetailResponse,
  StockListItemResponse,
  StockNewsFeedResponse,
  StockRange,
  StockTimeseriesResponse,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const FALLBACK_DASHBOARD: DashboardOverview = {
  as_of_date: null,
  stocks: [
    {
      slug: "catl",
      company_name: "CATL",
      primary_symbol: "300750.SZ",
      sector: "Battery Systems",
      latest_price: null,
      return_1m: null,
      return_3m: null,
      return_1y: null,
      pe_ttm: null,
      pb: null,
      ps_ttm: null,
      total_score: null,
      rank: null,
    },
    {
      slug: "byd",
      company_name: "BYD",
      primary_symbol: "1211.HK",
      sector: "EV + Energy Storage",
      latest_price: null,
      return_1m: null,
      return_3m: null,
      return_1y: null,
      pe_ttm: null,
      pb: null,
      ps_ttm: null,
      total_score: null,
      rank: null,
    },
    {
      slug: "xiaomi",
      company_name: "Xiaomi",
      primary_symbol: "1810.HK",
      sector: "Consumer Electronics",
      latest_price: null,
      return_1m: null,
      return_3m: null,
      return_1y: null,
      pe_ttm: null,
      pb: null,
      ps_ttm: null,
      total_score: null,
      rank: null,
    },
  ],
  recommendations: [
    {
      side: "LONG",
      slug: null,
      company_name: null,
      explanation: "Run the analysis and scoring pipeline to populate the current long idea.",
      total_score: null,
    },
    {
      side: "SHORT",
      slug: null,
      company_name: null,
      explanation: "Run the analysis and scoring pipeline to populate the current short idea.",
      total_score: null,
    },
  ],
};

function normalizeApiBaseUrl(value: string): string {
  const trimmed = value.replace(/\/+$/, "");
  return trimmed.endsWith("/api/v1") ? trimmed : `${trimmed}/api/v1`;
}

function getApiBaseUrl(): string {
  const configuredBaseUrl = process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configuredBaseUrl) {
    return normalizeApiBaseUrl(configuredBaseUrl);
  }

  if (process.env.NODE_ENV === "development") {
    return "http://127.0.0.1:8001/api/v1";
  }

  throw new Error(
    "API_BASE_URL or NEXT_PUBLIC_API_BASE_URL must be configured for production deployments.",
  );
}

async function fetchJson<T>(path: string, revalidate = 60): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    next: { revalidate },
  });

  if (!response.ok) {
    throw new ApiError(`${path} failed with ${response.status}`, response.status);
  }

  return (await response.json()) as T;
}

export function isApiNotFoundError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 404;
}

function shouldRenderDashboardFallback(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status >= 500;
  }
  return error instanceof TypeError;
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  try {
    return await fetchJson<DashboardOverview>("/dashboard/overview");
  } catch (error) {
    if (!shouldRenderDashboardFallback(error)) {
      throw error;
    }
    console.warn("Dashboard overview fetch failed; rendering fallback dashboard.", error);
    return FALLBACK_DASHBOARD;
  }
}

export async function getStockList(): Promise<StockListItemResponse[]> {
  return fetchJson<StockListItemResponse[]>("/stocks");
}

export async function getStockDetail(symbol: string): Promise<StockDetailResponse> {
  return fetchJson<StockDetailResponse>(`/stocks/${encodeURIComponent(symbol)}`);
}

export async function getStockTimeseries(
  symbol: string,
  range: StockRange = "1y",
): Promise<StockTimeseriesResponse> {
  return fetchJson<StockTimeseriesResponse>(
    `/stocks/${encodeURIComponent(symbol)}/timeseries?range=${range}`,
  );
}

export async function getStockNews(symbol: string): Promise<StockNewsFeedResponse> {
  return fetchJson<StockNewsFeedResponse>(`/stocks/${encodeURIComponent(symbol)}/news`);
}

export async function getStockAnalysis(symbol: string): Promise<StockAnalysisResponse> {
  return fetchJson<StockAnalysisResponse>(`/stocks/${encodeURIComponent(symbol)}/analysis`);
}

export async function getComparison(symbols: string[]): Promise<ComparisonResponse> {
  const search = new URLSearchParams();
  if (symbols.length > 0) {
    search.set("symbols", symbols.join(","));
  }

  const query = search.toString();
  return fetchJson<ComparisonResponse>(query ? `/compare?${query}` : "/compare");
}

export async function getAiMethodology(): Promise<AIMethodologyResponse> {
  return fetchJson<AIMethodologyResponse>("/metadata/ai-limitations");
}

export async function getAdminJobsStatus(): Promise<AdminJobStatusResponse> {
  return fetchJson<AdminJobStatusResponse>("/admin/jobs", 0);
}

export async function getLatestRecommendations(): Promise<RecommendationSnapshotResponse> {
  return fetchJson<RecommendationSnapshotResponse>("/recommendations");
}
