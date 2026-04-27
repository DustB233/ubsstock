import { ComparisonView } from "@/components/compare/comparison-view";
import { getComparison, getStockList } from "@/lib/api";
import type { StockListItemResponse } from "@/lib/types";

const DEFAULT_COMPARE_SYMBOLS = ["300750.SZ", "1211.HK", "1810.HK"];

type ComparePageProps = {
  searchParams: Promise<{ symbols?: string | string[] }>;
};

function pickFirstValue(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

function buildCanonicalLookup(stockList: StockListItemResponse[]): Map<string, string> {
  const lookup = new Map<string, string>();

  for (const stock of stockList) {
    lookup.set(stock.slug.toLowerCase(), stock.primary_symbol);

    for (const identifier of stock.identifiers) {
      lookup.set(identifier.composite_symbol.toLowerCase(), stock.primary_symbol);
    }
  }

  return lookup;
}

function normalizeSymbols(
  input: string | undefined,
  stockList: StockListItemResponse[],
): string[] {
  if (!input) {
    return DEFAULT_COMPARE_SYMBOLS;
  }

  const lookup = buildCanonicalLookup(stockList);
  const symbols = input
    .split(",")
    .map((symbol) => symbol.trim())
    .filter(Boolean);

  return symbols.length > 0
    ? Array.from(new Set(symbols.map((symbol) => lookup.get(symbol.toLowerCase()) ?? symbol)))
    : DEFAULT_COMPARE_SYMBOLS;
}

export default async function ComparePage({ searchParams }: ComparePageProps) {
  const [{ symbols }, stockList] = await Promise.all([searchParams, getStockList()]);
  const selectedSymbols = normalizeSymbols(pickFirstValue(symbols), stockList);
  const comparison = await getComparison(selectedSymbols);

  return (
    <ComparisonView
      stockList={stockList}
      comparison={comparison}
      selectedSymbols={selectedSymbols}
    />
  );
}
