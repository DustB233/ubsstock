"use client";

import type { Route } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { startTransition, useState } from "react";
import { ArrowDownUp, ArrowUpRight, Sparkles } from "lucide-react";
import clsx from "clsx";

import { DataCaveatsSection } from "@/components/market/data-caveats";
import {
  DataState,
  MetricTile,
  ScoreBar,
  SectionHeading,
  SentimentBadge,
} from "@/components/market/primitives";
import {
  formatCompactCurrency,
  formatCompactNumber,
  formatDate,
  formatPercent,
  formatScore,
} from "@/lib/formatters";
import type {
  ComparisonResponse,
  ComparisonRowResponse,
  StockListItemResponse,
} from "@/lib/types";

function inferListingCurrency(symbol: string): string {
  if (symbol.endsWith(".HK")) {
    return "HKD";
  }
  if (symbol.endsWith(".SZ") || symbol.endsWith(".SH")) {
    return "CNY";
  }
  return "USD";
}

function resolveValuationCurrency(row: ComparisonRowResponse): string {
  return (
    row.valuation.currency ??
    row.financial_snapshot.currency ??
    inferListingCurrency(row.symbol)
  );
}

type SortDirection = "asc" | "desc";
type SortKey =
  | "company"
  | "total_score"
  | "pe_ttm"
  | "pb"
  | "ps_ttm"
  | "revenue_growth"
  | "net_income_growth"
  | "gross_margin"
  | "roe"
  | "debt_to_equity"
  | "sentiment"
  | "valuation_freshness"
  | "filing_freshness";

type JudgeColumn = {
  key: SortKey;
  label: string;
  direction: SortDirection;
  better: "higher" | "lower" | "neutral";
  getSortValue: (row: ComparisonRowResponse) => number | string | null;
  render: (row: ComparisonRowResponse) => ReactNode;
};

function normalizeNullableNumber(value: number | null): number | null {
  return Number.isFinite(value) ? value : null;
}

function compareSortValues(
  left: number | string | null,
  right: number | string | null,
  direction: SortDirection,
): number {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }

  if (typeof left === "number" && typeof right === "number") {
    return direction === "asc" ? left - right : right - left;
  }

  const normalizedLeft = String(left).toLowerCase();
  const normalizedRight = String(right).toLowerCase();
  if (normalizedLeft === normalizedRight) {
    return 0;
  }

  if (direction === "asc") {
    return normalizedLeft > normalizedRight ? 1 : -1;
  }
  return normalizedLeft < normalizedRight ? 1 : -1;
}

function computeExtremes(
  rows: ComparisonRowResponse[],
  column: JudgeColumn,
): { best: number | null; worst: number | null } | null {
  if (column.better === "neutral") {
    return null;
  }

  const values = rows
    .map((row) => column.getSortValue(row))
    .filter((value): value is number => typeof value === "number");

  if (values.length < 2) {
    return null;
  }

  return column.better === "higher"
    ? { best: Math.max(...values), worst: Math.min(...values) }
    : { best: Math.min(...values), worst: Math.max(...values) };
}

function highlightTone(
  value: number | string | null,
  extremes: { best: number | null; worst: number | null } | null,
): "best" | "worst" | "neutral" {
  if (typeof value !== "number" || extremes === null) {
    return "neutral";
  }
  if (extremes.best !== null && value === extremes.best && value !== extremes.worst) {
    return "best";
  }
  if (extremes.worst !== null && value === extremes.worst && value !== extremes.best) {
    return "worst";
  }
  return "neutral";
}

function buildCompareHref(selectedSymbols: string[], symbol: string): string {
  const nextSelection = selectedSymbols.includes(symbol)
    ? selectedSymbols.filter((item) => item !== symbol)
    : [...selectedSymbols, symbol];

  const params = new URLSearchParams();
  if (nextSelection.length > 0) {
    params.set("symbols", nextSelection.join(","));
  }

  const query = params.toString();
  return query ? `/compare?${query}` : "/compare";
}

function SelectionRail({
  stockList,
  selectedSymbols,
}: {
  stockList: StockListItemResponse[];
  selectedSymbols: string[];
}) {
  return (
    <div className="flex flex-wrap gap-3">
      {stockList.map((stock) => {
        const isSelected = selectedSymbols.includes(stock.primary_symbol);

        return (
          <Link
            key={stock.slug}
            href={buildCompareHref(selectedSymbols, stock.primary_symbol) as Route}
            className={clsx(
              "rounded-full border px-4 py-2 text-sm transition",
              isSelected
                ? "border-amber-300/35 bg-amber-200/10 text-amber-100"
                : "border-white/10 bg-white/6 text-slate-300 hover:border-white/20 hover:text-white",
            )}
          >
            {stock.company_name}
            <span className="ml-2 text-xs uppercase tracking-[0.18em] text-current/80">
              {stock.primary_symbol}
            </span>
          </Link>
        );
      })}
    </div>
  );
}

function HighlightPanel({
  label,
  name,
  symbol,
  tone,
}: {
  label: string;
  name: string | null;
  symbol: string | null;
  tone: "positive" | "negative";
}) {
  return (
    <div
      className={clsx(
        "rounded-[1.7rem] border p-6 shadow-[0_20px_60px_rgba(3,7,18,0.24)]",
        tone === "positive"
          ? "border-emerald-300/20 bg-emerald-300/10"
          : "border-rose-300/20 bg-rose-300/10",
      )}
    >
      <p className="text-xs uppercase tracking-[0.28em] text-white/70">{label}</p>
      <h3 className="mt-4 text-2xl font-semibold text-white">{name ?? "TBD"}</h3>
      <p className="mt-2 text-sm uppercase tracking-[0.22em] text-white/75">{symbol ?? "—"}</p>
    </div>
  );
}

function SummaryCards({ rows }: { rows: ComparisonRowResponse[] }) {
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      {rows.map((row) => (
        <Link
          key={row.symbol}
          href={`/stocks/${row.slug}`}
          className="rounded-[1.7rem] border border-white/10 bg-slate-950/45 p-5 shadow-[0_20px_60px_rgba(3,7,18,0.24)] transition hover:border-amber-200/35"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{row.symbol}</p>
              <h3 className="mt-2 text-2xl font-semibold text-white">{row.company_name}</h3>
              <p className="mt-2 text-sm text-slate-300">{row.sector}</p>
            </div>
            <ArrowUpRight className="size-5 text-slate-500" />
          </div>
          <div className="mt-6 grid grid-cols-2 gap-3">
            <MetricTile
              label="Total Score"
              value={formatScore(row.factor_scores.total_score)}
              hint={`Rank ${row.factor_scores.rank ?? "—"}`}
              tone="accent"
            />
            <MetricTile
              label="PE"
              value={formatScore(row.valuation.pe_ttm)}
              hint={
                [row.valuation.source, row.valuation.currency].filter(Boolean).join(" · ") ||
                "Stored valuation source"
              }
            />
            <MetricTile
              label="Revenue Growth"
              value={formatPercent(row.financial_snapshot.revenue_growth_yoy)}
            />
            <MetricTile
              label="Latest Report"
              value={formatDate(row.financial_snapshot.as_of_date ?? row.financial_snapshot.report_date)}
              hint={row.financial_snapshot.source ?? "Stored filing source"}
            />
          </div>
        </Link>
      ))}
    </div>
  );
}

function JudgeTable({ rows }: { rows: ComparisonRowResponse[] }) {
  const columns: JudgeColumn[] = [
    {
      key: "company",
      label: "Company",
      direction: "asc",
      better: "neutral",
      getSortValue: (row) => row.company_name,
      render: (row) => (
        <div>
          <p className="font-medium text-white">{row.company_name}</p>
          <p className="mt-1 text-[11px] uppercase tracking-[0.22em] text-slate-500">
            {row.symbol}
          </p>
        </div>
      ),
    },
    {
      key: "total_score",
      label: "Total Score",
      direction: "desc",
      better: "higher",
      getSortValue: (row) => normalizeNullableNumber(row.factor_scores.total_score),
      render: (row) => formatScore(row.factor_scores.total_score),
    },
    {
      key: "pe_ttm",
      label: "PE",
      direction: "asc",
      better: "lower",
      getSortValue: (row) => normalizeNullableNumber(row.valuation.pe_ttm),
      render: (row) => formatScore(row.valuation.pe_ttm),
    },
    {
      key: "pb",
      label: "PB",
      direction: "asc",
      better: "lower",
      getSortValue: (row) => normalizeNullableNumber(row.valuation.pb),
      render: (row) => formatScore(row.valuation.pb),
    },
    {
      key: "ps_ttm",
      label: "PS",
      direction: "asc",
      better: "lower",
      getSortValue: (row) => normalizeNullableNumber(row.valuation.ps_ttm),
      render: (row) => formatScore(row.valuation.ps_ttm),
    },
    {
      key: "revenue_growth",
      label: "Revenue Growth",
      direction: "desc",
      better: "higher",
      getSortValue: (row) => normalizeNullableNumber(row.financial_snapshot.revenue_growth_yoy),
      render: (row) => formatPercent(row.financial_snapshot.revenue_growth_yoy),
    },
    {
      key: "net_income_growth",
      label: "Net Income Growth",
      direction: "desc",
      better: "higher",
      getSortValue: (row) =>
        normalizeNullableNumber(
          row.financial_snapshot.net_income_growth_yoy ??
            row.financial_snapshot.net_profit_growth_yoy,
        ),
      render: (row) =>
        formatPercent(
          row.financial_snapshot.net_income_growth_yoy ??
            row.financial_snapshot.net_profit_growth_yoy,
        ),
    },
    {
      key: "gross_margin",
      label: "Gross Margin",
      direction: "desc",
      better: "higher",
      getSortValue: (row) => normalizeNullableNumber(row.financial_snapshot.gross_margin),
      render: (row) => formatPercent(row.financial_snapshot.gross_margin),
    },
    {
      key: "roe",
      label: "ROE",
      direction: "desc",
      better: "higher",
      getSortValue: (row) => normalizeNullableNumber(row.financial_snapshot.roe),
      render: (row) => formatPercent(row.financial_snapshot.roe),
    },
    {
      key: "debt_to_equity",
      label: "Debt / Equity",
      direction: "asc",
      better: "lower",
      getSortValue: (row) => normalizeNullableNumber(row.financial_snapshot.debt_to_equity),
      render: (row) =>
        row.financial_snapshot.debt_to_equity === null
          ? "—"
          : `${row.financial_snapshot.debt_to_equity.toFixed(2)}x`,
    },
    {
      key: "sentiment",
      label: "Sentiment",
      direction: "desc",
      better: "higher",
      getSortValue: (row) => normalizeNullableNumber(row.sentiment_score),
      render: (row) => (
        <SentimentBadge label={row.sentiment_label} score={row.sentiment_score} />
      ),
    },
    {
      key: "valuation_freshness",
      label: "Valuation Source",
      direction: "desc",
      better: "neutral",
      getSortValue: (row) =>
        row.valuation.as_of_date ? Date.parse(row.valuation.as_of_date) : null,
      render: (row) => (
        <div>
          <p className="text-white">{formatDate(row.valuation.as_of_date)}</p>
          <p className="mt-1 text-xs text-slate-400">
            {[row.valuation.source, row.valuation.currency].filter(Boolean).join(" · ") || "—"}
          </p>
        </div>
      ),
    },
    {
      key: "filing_freshness",
      label: "Latest Filing",
      direction: "desc",
      better: "neutral",
      getSortValue: (row) =>
        row.financial_snapshot.as_of_date
          ? Date.parse(row.financial_snapshot.as_of_date)
          : row.financial_snapshot.report_date
            ? Date.parse(row.financial_snapshot.report_date)
            : null,
      render: (row) => (
        <div>
          <p className="text-white">
            {formatDate(
              row.financial_snapshot.as_of_date ?? row.financial_snapshot.report_date,
            )}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {[row.financial_snapshot.report_period, row.financial_snapshot.source]
              .filter(Boolean)
              .join(" · ") || "—"}
          </p>
        </div>
      ),
    },
  ];

  const [sortConfig, setSortConfig] = useState<{
    key: SortKey;
    direction: SortDirection;
  }>({
    key: "total_score",
    direction: "desc",
  });

  const activeColumn =
    columns.find((column) => column.key === sortConfig.key) ?? columns[1] ?? columns[0];
  const sortedRows = [...rows].sort((left, right) =>
    compareSortValues(
      activeColumn.getSortValue(left),
      activeColumn.getSortValue(right),
      sortConfig.direction,
    ),
  );

  const extremes = Object.fromEntries(
    columns.map((column) => [column.key, computeExtremes(sortedRows, column)]),
  ) as Record<SortKey, { best: number | null; worst: number | null } | null>;

  function handleSort(column: JudgeColumn) {
    startTransition(() => {
      setSortConfig((current) => ({
        key: column.key,
        direction:
          current.key === column.key
            ? current.direction === "asc"
              ? "desc"
              : "asc"
            : column.direction,
      }));
    });
  }

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
      <SectionHeading
        eyebrow="Judge Table"
        title="Sortable competition snapshot"
        description="Sort the selected stocks by score, valuation, growth, margins, leverage, sentiment, or data freshness to quickly explain the long and short verdict."
      />
      <div className="mt-6 flex flex-wrap gap-3 text-xs uppercase tracking-[0.22em] text-slate-400">
        <span className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-emerald-100">
          Best-in-view cells
        </span>
        <span className="rounded-full border border-rose-300/20 bg-rose-300/10 px-3 py-1 text-rose-100">
          Weakest-in-view cells
        </span>
        <span className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-slate-300">
          Nulls stay neutral
        </span>
      </div>
      <div className="mt-6 overflow-x-auto">
        <table className="min-w-[1120px] border-separate border-spacing-y-3">
          <thead>
            <tr>
              {columns.map((column) => {
                const isActive = sortConfig.key === column.key;
                return (
                  <th key={column.key} className="px-3 text-left">
                    <button
                      type="button"
                      onClick={() => handleSort(column)}
                      className={clsx(
                        "inline-flex items-center gap-2 rounded-full border px-3 py-2 text-[11px] uppercase tracking-[0.24em] transition",
                        isActive
                          ? "border-amber-300/35 bg-amber-200/10 text-amber-100"
                          : "border-white/10 bg-white/6 text-slate-400 hover:border-white/20 hover:text-white",
                      )}
                    >
                      {column.label}
                      <ArrowDownUp className="size-3.5" />
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr key={row.symbol}>
                {columns.map((column, index) => {
                  const value = column.getSortValue(row);
                  const tone = highlightTone(value, extremes[column.key]);
                  return (
                    <td
                      key={`${row.symbol}-${column.key}`}
                      className={clsx(
                        "border-y border-white/8 px-3 py-4 align-top text-sm",
                        index === 0 && "rounded-l-[1.2rem] border-l",
                        index === columns.length - 1 && "rounded-r-[1.2rem] border-r",
                        tone === "best" && "bg-emerald-300/10 text-emerald-50",
                        tone === "worst" && "bg-rose-300/10 text-rose-50",
                        tone === "neutral" && "bg-white/[0.03] text-slate-200",
                      )}
                    >
                      {column.render(row)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ComparisonTable({
  title,
  description,
  rows,
  metrics,
}: {
  title: string;
  description: string;
  rows: ComparisonRowResponse[];
  metrics: Array<{
    key: string;
    label: string;
    render: (row: ComparisonRowResponse) => ReactNode;
  }>;
}) {
  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
      <SectionHeading eyebrow="Comparison Lens" title={title} description={description} />
      <div className="mt-6 overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-y-3">
          <thead>
            <tr>
              <th className="w-52 px-4 text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                Metric
              </th>
              {rows.map((row) => (
                <th
                  key={row.symbol}
                  className="min-w-[180px] px-4 text-left text-xs uppercase tracking-[0.24em] text-slate-400"
                >
                  {row.company_name}
                  <span className="ml-2 text-slate-600">{row.symbol}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((metric) => (
              <tr key={metric.key}>
                <td className="rounded-l-[1.2rem] border border-white/8 bg-white/[0.03] px-4 py-4 text-sm font-medium text-white">
                  {metric.label}
                </td>
                {rows.map((row, index) => (
                  <td
                    key={`${metric.key}-${row.symbol}`}
                    className={clsx(
                      "border-y border-white/8 bg-white/[0.03] px-4 py-4 text-sm text-slate-200",
                      index === rows.length - 1 && "rounded-r-[1.2rem] border-r",
                    )}
                  >
                    {metric.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function ComparisonView({
  comparison,
  stockList,
  selectedSymbols,
}: {
  comparison: ComparisonResponse;
  stockList: StockListItemResponse[];
  selectedSymbols: string[];
}) {
  if (comparison.rows.length === 0) {
    return (
      <DataState
        eyebrow="Comparison Engine"
        title="No matching stocks were found"
        description="Try selecting tickers from the universe below to populate the comparison grid."
        action={{ href: "/compare", label: "Reset comparison" }}
      />
    );
  }

  const factorMetrics = [
    {
      key: "total_score",
      label: "Total score",
      render: (row: ComparisonRowResponse) => (
        <ScoreBar label="Universe score" value={row.factor_scores.total_score} />
      ),
    },
    {
      key: "fundamentals",
      label: "Fundamentals quality",
      render: (row: ComparisonRowResponse) => (
        <ScoreBar label="Quality" value={row.factor_scores.fundamentals_quality} />
      ),
    },
    {
      key: "valuation",
      label: "Valuation attractiveness",
      render: (row: ComparisonRowResponse) => (
        <ScoreBar label="Value" value={row.factor_scores.valuation_attractiveness} />
      ),
    },
    {
      key: "momentum",
      label: "Price momentum",
      render: (row: ComparisonRowResponse) => (
        <ScoreBar label="Momentum" value={row.factor_scores.price_momentum} />
      ),
    },
    {
      key: "news",
      label: "News sentiment",
      render: (row: ComparisonRowResponse) => (
        <ScoreBar label="Event tone" value={row.factor_scores.news_sentiment} />
      ),
    },
    {
      key: "global",
      label: "Globalization strength",
      render: (row: ComparisonRowResponse) => (
        <ScoreBar label="Outbound footprint" value={row.factor_scores.globalization_strength} />
      ),
    },
  ];

  const valuationMetrics = [
    {
      key: "valuation_snapshot",
      label: "Valuation snapshot",
      render: (row: ComparisonRowResponse) =>
        [formatDate(row.valuation.as_of_date), row.valuation.currency, row.valuation.source]
          .filter(Boolean)
          .join(" · ") || "—",
    },
    {
      key: "pe",
      label: "PE (TTM)",
      render: (row: ComparisonRowResponse) => formatScore(row.valuation.pe_ttm),
    },
    {
      key: "pb",
      label: "PB",
      render: (row: ComparisonRowResponse) => formatScore(row.valuation.pb),
    },
    {
      key: "ps",
      label: "PS (TTM)",
      render: (row: ComparisonRowResponse) => formatScore(row.valuation.ps_ttm),
    },
    {
      key: "enterprise_value",
      label: "Enterprise value",
      render: (row: ComparisonRowResponse) =>
        formatCompactCurrency(row.valuation.enterprise_value, resolveValuationCurrency(row)),
    },
    {
      key: "ev_ebitda",
      label: "EV / EBITDA",
      render: (row: ComparisonRowResponse) => formatScore(row.valuation.ev_ebitda),
    },
    {
      key: "dividend",
      label: "Dividend yield",
      render: (row: ComparisonRowResponse) => formatPercent(row.valuation.dividend_yield),
    },
    {
      key: "market_cap",
      label: "Market cap",
      render: (row: ComparisonRowResponse) =>
        formatCompactCurrency(row.valuation.market_cap, resolveValuationCurrency(row)),
    },
  ];

  const growthMetrics = [
    {
      key: "reporting_snapshot",
      label: "Latest filing",
      render: (row: ComparisonRowResponse) =>
        [
          formatDate(row.financial_snapshot.as_of_date ?? row.financial_snapshot.report_date),
          row.financial_snapshot.report_period ?? row.financial_snapshot.fiscal_period,
          row.financial_snapshot.source,
        ]
          .filter(Boolean)
          .join(" · ") || "—",
    },
    {
      key: "revenue_growth",
      label: "Revenue growth",
      render: (row: ComparisonRowResponse) =>
        formatPercent(row.financial_snapshot.revenue_growth_yoy),
    },
    {
      key: "net_income_growth",
      label: "Net income growth",
      render: (row: ComparisonRowResponse) =>
        formatPercent(
          row.financial_snapshot.net_income_growth_yoy ??
            row.financial_snapshot.net_profit_growth_yoy,
        ),
    },
    {
      key: "roe",
      label: "ROE",
      render: (row: ComparisonRowResponse) => formatPercent(row.financial_snapshot.roe),
    },
    {
      key: "roa",
      label: "ROA",
      render: (row: ComparisonRowResponse) => formatPercent(row.financial_snapshot.roa),
    },
    {
      key: "gross_margin",
      label: "Gross margin",
      render: (row: ComparisonRowResponse) =>
        formatPercent(row.financial_snapshot.gross_margin),
    },
    {
      key: "operating_margin",
      label: "Operating margin",
      render: (row: ComparisonRowResponse) =>
        formatPercent(row.financial_snapshot.operating_margin),
    },
    {
      key: "debt_to_equity",
      label: "Debt / equity",
      render: (row: ComparisonRowResponse) =>
        row.financial_snapshot.debt_to_equity === null
          ? "—"
          : `${row.financial_snapshot.debt_to_equity.toFixed(2)}x`,
    },
    {
      key: "revenue",
      label: "Revenue",
      render: (row: ComparisonRowResponse) =>
        formatCompactNumber(row.financial_snapshot.revenue),
    },
    {
      key: "net_income",
      label: "Net income",
      render: (row: ComparisonRowResponse) =>
        formatCompactNumber(
          row.financial_snapshot.net_income ?? row.financial_snapshot.net_profit,
        ),
    },
    {
      key: "overseas_revenue",
      label: "Overseas revenue",
      render: (row: ComparisonRowResponse) =>
        formatPercent(row.financial_snapshot.overseas_revenue_ratio),
    },
  ];

  const sentimentMetrics = [
    {
      key: "sentiment",
      label: "Sentiment label",
      render: (row: ComparisonRowResponse) => (
        <SentimentBadge label={row.sentiment_label} score={row.sentiment_score} />
      ),
    },
    {
      key: "sentiment_score",
      label: "Sentiment score",
      render: (row: ComparisonRowResponse) =>
        row.sentiment_score === null ? "—" : row.sentiment_score.toFixed(2),
    },
    {
      key: "rank",
      label: "Universe rank",
      render: (row: ComparisonRowResponse) => row.factor_scores.rank ?? "—",
    },
  ];

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.35)]">
        <SectionHeading
          eyebrow="Comparison Engine"
          title="Cross-stock lens for long and short selection"
          description="Compare stored valuation snapshots, reported fundamentals, factor scores, and sentiment side by side using the same live database-backed engine that powers the recommendations."
        />
        <div className="mt-8">
          <SelectionRail stockList={stockList} selectedSymbols={selectedSymbols} />
        </div>
        <div className="mt-6 flex flex-wrap gap-3 text-sm text-slate-300">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-4 py-2">
            <Sparkles className="size-4 text-amber-200" />
            <span>{comparison.rows.length} stocks in view</span>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-4 py-2">
            <span className="text-slate-400">Request</span>
            <span className="font-mono text-xs uppercase tracking-[0.18em] text-slate-200">
              {comparison.requested_symbols.join(", ")}
            </span>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <HighlightPanel
          label="Most attractive"
          name={comparison.highlights.most_attractive_name}
          symbol={comparison.highlights.most_attractive_symbol}
          tone="positive"
        />
        <HighlightPanel
          label="Least attractive"
          name={comparison.highlights.least_attractive_name}
          symbol={comparison.highlights.least_attractive_symbol}
          tone="negative"
        />
      </div>

      <SummaryCards rows={comparison.rows} />

      <JudgeTable rows={comparison.rows} />

      <ComparisonTable
        title="Factor score comparison"
        description="The weighted engine determines which names surface as the current long and short candidates."
        rows={comparison.rows}
        metrics={factorMetrics}
      />
      <ComparisonTable
        title="Valuation comparison"
        description="Valuation metrics give a quick read on which stocks screen cheaper or richer in the current snapshot."
        rows={comparison.rows}
        metrics={valuationMetrics}
      />
      <ComparisonTable
        title="Growth comparison"
        description="Growth and profitability metrics highlight which names have stronger operating momentum."
        rows={comparison.rows}
        metrics={growthMetrics}
      />
      <ComparisonTable
        title="Sentiment comparison"
        description="Sentiment is sourced from the same explainable AI and mock-news pipeline used in the recommendation engine."
        rows={comparison.rows}
        metrics={sentimentMetrics}
      />

      <DataCaveatsSection className="mt-2" />
    </div>
  );
}
