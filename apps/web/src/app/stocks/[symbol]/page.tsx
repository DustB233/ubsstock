import { notFound } from "next/navigation";

import { StockDetailView } from "@/components/stocks/stock-detail-view";
import {
  getStockAnalysis,
  getStockDetail,
  getStockNews,
  getStockTimeseries,
  isApiNotFoundError,
} from "@/lib/api";
import type { StockRange } from "@/lib/types";

type StockDetailPageProps = {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ range?: string | string[] }>;
};

function normalizeRange(range: string | string[] | undefined): StockRange {
  const normalizedRange = Array.isArray(range) ? range[0] : range;

  if (
    normalizedRange === "1m" ||
    normalizedRange === "3m" ||
    normalizedRange === "6m" ||
    normalizedRange === "1y"
  ) {
    return normalizedRange;
  }

  return "1y";
}

function normalizeRouteSymbol(symbol: string | string[] | undefined): string {
  return Array.isArray(symbol) ? symbol[0] ?? "" : symbol ?? "";
}

export default async function StockDetailPage({
  params,
  searchParams,
}: StockDetailPageProps) {
  const [{ symbol }, { range }] = await Promise.all([params, searchParams]);
  const routeSymbol = normalizeRouteSymbol(symbol);
  const selectedRange = normalizeRange(range);
  let payload;

  try {
    payload = await Promise.all([
      getStockDetail(routeSymbol),
      getStockTimeseries(routeSymbol, selectedRange),
      getStockNews(routeSymbol),
      getStockAnalysis(routeSymbol),
    ]);
  } catch (error) {
    if (isApiNotFoundError(error)) {
      notFound();
    }

    throw error;
  }

  const [detail, timeseries, news, analysis] = payload;

  return (
    <StockDetailView
      detail={detail}
      timeseries={timeseries}
      news={news}
      analysis={analysis}
      selectedRange={selectedRange}
    />
  );
}
