import Link from "next/link";
import {
  ArrowUpRight,
  BrainCircuit,
  Building2,
  ChartNoAxesCombined,
  FileText,
  Newspaper,
  ShieldAlert,
} from "lucide-react";

import { DataCaveatsSection } from "@/components/market/data-caveats";
import { AnalysisMetadataStrip } from "@/components/market/analysis-metadata";
import {
  DataState,
  MetricTile,
  ScoreBar,
  SectionHeading,
  SentimentBadge,
} from "@/components/market/primitives";
import { StockPriceChart } from "@/components/stocks/stock-price-chart";
import {
  formatCompactCurrency,
  formatCompactNumber,
  formatCurrency,
  formatDate,
  formatPercent,
  formatScore,
} from "@/lib/formatters";
import type {
  StockAnalysisResponse,
  StockDetailResponse,
  StockNewsFeedResponse,
  StockRange,
  StockTimeseriesResponse,
} from "@/lib/types";

const RANGE_OPTIONS: StockRange[] = ["1m", "3m", "6m", "1y"];

const FACTOR_WEIGHTS: Record<string, string> = {
  fundamentals_quality: "25% weight",
  valuation_attractiveness: "25% weight",
  price_momentum: "15% weight",
  news_sentiment: "20% weight",
  globalization_strength: "15% weight",
};

function formatEvidenceMetric(
  value: number | string | null,
  unit: string | null,
): string {
  if (value === null) {
    return "n/a";
  }
  if (typeof value === "string") {
    return value;
  }
  if (unit === "%") {
    return `${value.toFixed(1)}%`;
  }
  if (unit) {
    return `${value.toFixed(1)}${unit}`;
  }
  return formatCompactNumber(value);
}

function sourceDetail(source: string | null, asOfDate: string | null): string {
  return [source, asOfDate ? formatDate(asOfDate) : null].filter(Boolean).join(" · ") || "Stored snapshot";
}

function EvidenceReferencePill({
  reference,
}: {
  reference: StockAnalysisResponse["source_references"][number];
}) {
  const meta =
    reference.reference_type === "metric"
      ? formatEvidenceMetric(reference.metric_value, reference.metric_unit)
      : [reference.provider, reference.published_at ? formatDate(reference.published_at) : null]
          .filter(Boolean)
          .join(" · ");

  const content = (
    <>
      <span className="truncate">{reference.label}</span>
      {meta ? <span className="text-slate-500">{meta}</span> : null}
    </>
  );

  if (reference.url) {
    return (
      <a
        href={reference.url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex max-w-full items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-2 text-sm text-slate-200 transition hover:border-amber-200/40 hover:text-white"
      >
        {content}
        <ArrowUpRight className="size-4 shrink-0" />
      </a>
    );
  }

  return (
    <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-2 text-sm text-slate-200">
      {content}
    </div>
  );
}

function MetricGrid({
  detail,
  currency,
}: {
  detail: StockDetailResponse;
  currency: string;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricTile
        label="Latest Price"
        value={formatCurrency(detail.latest_price, currency)}
        hint={`Primary listing ${detail.primary_symbol}`}
        tone="accent"
      />
      <MetricTile label="1M Return" value={formatPercent(detail.returns.return_1m)} />
      <MetricTile label="3M Return" value={formatPercent(detail.returns.return_3m)} />
      <MetricTile
        label="1Y Return"
        value={formatPercent(detail.returns.return_1y)}
        hint={`Rank ${detail.factor_scores.rank ?? "—"} of 15`}
      />
    </div>
  );
}

function RangeLink({
  slug,
  range,
  selectedRange,
}: {
  slug: string;
  range: StockRange;
  selectedRange: StockRange;
}) {
  const isActive = range === selectedRange;

  return (
    <Link
      href={`/stocks/${slug}?range=${range}`}
      className={`rounded-full border px-4 py-2 text-xs uppercase tracking-[0.24em] transition ${
        isActive
          ? "border-amber-300/35 bg-amber-200/10 text-amber-100"
          : "border-white/10 bg-white/6 text-slate-300 hover:border-white/20 hover:text-white"
      }`}
    >
      {range}
    </Link>
  );
}

function IdentifierList({ detail }: { detail: StockDetailResponse }) {
  return (
    <div className="flex flex-wrap gap-2">
      {detail.identifiers.map((identifier) => (
        <span
          key={identifier.composite_symbol}
          className={`rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.22em] ${
            identifier.is_primary
              ? "border-amber-300/25 bg-amber-200/10 text-amber-100"
              : "border-white/10 bg-white/6 text-slate-300"
          }`}
        >
          {identifier.composite_symbol} · {identifier.currency}
        </span>
      ))}
    </div>
  );
}

function ValuationPanel({
  detail,
  currency,
  analysis,
}: {
  detail: StockDetailResponse;
  currency: string;
  analysis: StockAnalysisResponse;
}) {
  const valuationCurrency =
    detail.valuation.currency ?? detail.financial_snapshot.currency ?? currency;

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
      <SectionHeading
        eyebrow="Valuation"
        title="Current market framing"
        description={analysis.valuation_summary}
      />
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <MetricTile
          label="Market Cap"
          value={formatCompactCurrency(detail.valuation.market_cap, valuationCurrency)}
          hint={sourceDetail(detail.valuation.source, detail.valuation.as_of_date)}
        />
        <MetricTile label="PE (TTM)" value={formatScore(detail.valuation.pe_ttm)} />
        <MetricTile label="PE (Forward)" value={formatScore(detail.valuation.pe_forward)} />
        <MetricTile label="PB" value={formatScore(detail.valuation.pb)} />
        <MetricTile label="PS (TTM)" value={formatScore(detail.valuation.ps_ttm)} />
        <MetricTile
          label="Enterprise Value"
          value={formatCompactCurrency(detail.valuation.enterprise_value, valuationCurrency)}
        />
        <MetricTile label="EV / EBITDA" value={formatScore(detail.valuation.ev_ebitda)} />
        <MetricTile
          label="Dividend Yield"
          value={formatPercent(detail.valuation.dividend_yield)}
        />
        <MetricTile
          label="Snapshot Currency"
          value={detail.valuation.currency ?? "—"}
          hint={detail.valuation.source ?? "Stored valuation source"}
        />
        <MetricTile
          label="Snapshot Date"
          value={formatDate(detail.valuation.as_of_date)}
          hint={
            [detail.valuation.source, detail.valuation.currency].filter(Boolean).join(" · ") ||
            "Stored valuation source"
          }
        />
      </div>
    </section>
  );
}

function FinancialPanel({ detail }: { detail: StockDetailResponse }) {
  const netIncome = detail.financial_snapshot.net_income ?? detail.financial_snapshot.net_profit;
  const netIncomeGrowth =
    detail.financial_snapshot.net_income_growth_yoy ??
    detail.financial_snapshot.net_profit_growth_yoy;
  const asOfDate = detail.financial_snapshot.as_of_date ?? detail.financial_snapshot.report_date;

  const reportingMetrics = [
    {
      label: "As Of",
      value: formatDate(asOfDate),
      hint:
        detail.financial_snapshot.report_period ?? detail.financial_snapshot.fiscal_period ?? "—",
    },
    {
      label: "Source",
      value: detail.financial_snapshot.source ?? "—",
      hint: detail.financial_snapshot.currency ?? "Reported currency unavailable",
    },
    {
      label: "Report Period",
      value: detail.financial_snapshot.report_period ?? "—",
      hint: `${detail.financial_snapshot.fiscal_year ?? "—"} · ${detail.financial_snapshot.fiscal_period ?? "—"}`,
    },
  ] as const;

  const profitabilityMetrics = [
    {
      label: "Net Income",
      value: formatCompactNumber(netIncome),
      hint: "Latest stored reported profit line",
    },
    {
      label: "Gross Margin",
      value: formatPercent(detail.financial_snapshot.gross_margin),
      hint: "Profitability after cost of goods sold",
    },
    {
      label: "Operating Margin",
      value: formatPercent(detail.financial_snapshot.operating_margin),
      hint: "Operating leverage from reported filings",
    },
    {
      label: "ROE",
      value: formatPercent(detail.financial_snapshot.roe),
      hint: "Return on equity",
    },
    {
      label: "ROA",
      value: formatPercent(detail.financial_snapshot.roa),
      hint: "Return on assets",
    },
  ] as const;

  const growthMetrics = [
    {
      label: "Revenue",
      value: formatCompactNumber(detail.financial_snapshot.revenue),
      hint: detail.financial_snapshot.currency ?? "Reported currency",
    },
    {
      label: "Revenue Growth",
      value: formatPercent(detail.financial_snapshot.revenue_growth_yoy),
      hint: "Year-over-year growth from latest filing",
    },
    {
      label: "Net Income Growth",
      value: formatPercent(netIncomeGrowth),
      hint: "Year-over-year bottom-line growth",
    },
  ] as const;

  const leverageMetrics = [
    {
      label: "Debt / Equity",
      value:
        detail.financial_snapshot.debt_to_equity === null
          ? "—"
          : `${detail.financial_snapshot.debt_to_equity.toFixed(2)}x`,
      hint: "Lower values generally imply less balance-sheet leverage",
    },
  ] as const;

  const globalizationMetrics = [
    {
      label: "Overseas Revenue Ratio",
      value: formatPercent(detail.financial_snapshot.overseas_revenue_ratio),
      hint:
        detail.financial_snapshot.overseas_revenue_ratio === null
          ? "Provider did not expose a machine-readable overseas mix field"
          : "Share of revenue tied to overseas operations where disclosed",
    },
  ] as const;

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
      <SectionHeading
        eyebrow="Financial Snapshot"
        title="Latest reported operating momentum"
        description="Stored company filings are broken into profitability, growth, leverage, and globalization lenses so the judge can read the operating picture quickly."
      />
      <div className="mt-6 space-y-5">
        <MetricGroup
          title="Reporting Context"
          description="Source attribution and filing freshness for the stored snapshot."
          metrics={reportingMetrics}
          columns="md:grid-cols-3"
        />
        <MetricGroup
          title="Profitability Metrics"
          description="Margins and returns that frame how efficiently the company turns revenue into earnings."
          metrics={profitabilityMetrics}
          columns="md:grid-cols-2 xl:grid-cols-5"
        />
        <MetricGroup
          title="Growth Metrics"
          description="Top-line and bottom-line trend indicators from the latest filing."
          metrics={growthMetrics}
          columns="md:grid-cols-3"
        />
        <MetricGroup
          title="Leverage Metrics"
          description="Balance-sheet risk indicators that can change the durability of the thesis."
          metrics={leverageMetrics}
          columns="md:grid-cols-1"
        />
        <MetricGroup
          title="Globalization / Overseas Metrics"
          description="International revenue mix is shown only when the provider exposes it clearly."
          metrics={globalizationMetrics}
          columns="md:grid-cols-1"
        />
      </div>
    </section>
  );
}

function MetricGroup({
  title,
  description,
  metrics,
  columns,
}: {
  title: string;
  description: string;
  metrics: ReadonlyArray<{
    label: string;
    value: string;
    hint: string;
  }>;
  columns: string;
}) {
  return (
    <div className="rounded-[1.5rem] border border-white/8 bg-white/[0.03] p-5">
      <div className="max-w-3xl">
        <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{title}</p>
        <p className="mt-2 text-sm leading-6 text-slate-300">{description}</p>
      </div>
      <div className={`mt-4 grid gap-4 ${columns}`}>
        {metrics.map((metric) => (
          <MetricTile
            key={metric.label}
            label={metric.label}
            value={metric.value}
            hint={metric.hint}
          />
        ))}
      </div>
    </div>
  );
}

function FactorPanel({ detail }: { detail: StockDetailResponse }) {
  const factors = [
    ["Fundamentals quality", detail.factor_scores.fundamentals_quality, FACTOR_WEIGHTS.fundamentals_quality],
    ["Valuation attractiveness", detail.factor_scores.valuation_attractiveness, FACTOR_WEIGHTS.valuation_attractiveness],
    ["Price momentum", detail.factor_scores.price_momentum, FACTOR_WEIGHTS.price_momentum],
    ["News sentiment", detail.factor_scores.news_sentiment, FACTOR_WEIGHTS.news_sentiment],
    ["Globalization strength", detail.factor_scores.globalization_strength, FACTOR_WEIGHTS.globalization_strength],
  ] as const;

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
      <SectionHeading
        eyebrow="Scoring Engine"
        title="Transparent factor breakdown"
        description="Each component score is percentile-based inside the 15-stock universe and rolled into the total ranking."
      />
      <div className="mt-6 space-y-5">
        {factors.map(([label, value, detailText]) => (
          <ScoreBar key={label} label={label} value={value} detail={detailText} />
        ))}
      </div>
      <div className="mt-6 rounded-[1.4rem] border border-amber-200/20 bg-amber-100/8 p-4">
        <p className="text-[11px] uppercase tracking-[0.24em] text-amber-100">Total score</p>
        <div className="mt-3 flex items-end justify-between gap-4">
          <p className="text-4xl font-semibold text-white">
            {formatScore(detail.factor_scores.total_score)}
          </p>
          <p className="text-sm text-amber-50/85">Universe rank {detail.factor_scores.rank ?? "—"}</p>
        </div>
      </div>
    </section>
  );
}

function AIThesisPanel({ analysis }: { analysis: StockAnalysisResponse }) {
  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-[linear-gradient(160deg,_rgba(251,191,36,0.16),_rgba(15,23,42,0.88)_42%)] p-6 shadow-[0_24px_80px_rgba(3,7,18,0.28)]">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-amber-100/80">AI Thesis</p>
          <h3 className="mt-2 text-3xl font-semibold text-white">Explainable summary</h3>
        </div>
        <SentimentBadge label={analysis.sentiment_label} score={analysis.sentiment_score} />
      </div>
      <div className="mt-5">
        <AnalysisMetadataStrip analysis={analysis} />
      </div>
      <p className="mt-5 text-sm leading-7 text-slate-100/92">{analysis.summary}</p>
      <div className="mt-6 grid gap-3 md:grid-cols-3">
        {analysis.top_news_themes.map((theme) => (
          <article
            key={theme.theme}
            className="rounded-[1.3rem] border border-white/10 bg-slate-950/45 p-4"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-white">{theme.theme}</p>
              <SentimentBadge label={theme.sentiment_label} score={theme.sentiment_score} />
            </div>
            <p className="mt-3 text-xs uppercase tracking-[0.24em] text-slate-400">
              {theme.article_count} supporting sources
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-200">{theme.summary}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {theme.evidence.slice(0, 2).map((reference) => (
                <EvidenceReferencePill key={reference.reference_id} reference={reference} />
              ))}
            </div>
          </article>
        ))}
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        {analysis.keyword_insights.map((keyword) => (
          <span
            key={keyword.keyword}
            className="rounded-full border border-white/12 bg-white/8 px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-100"
          >
            {keyword.keyword} · {keyword.mentions}
          </span>
        ))}
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <div className="rounded-[1.4rem] border border-emerald-300/20 bg-emerald-300/8 p-4">
          <div className="flex items-center gap-2 text-emerald-100">
            <BrainCircuit className="size-4" />
            <p className="text-xs uppercase tracking-[0.24em]">Bull case</p>
          </div>
          <p className="mt-3 text-sm leading-7 text-emerald-50/95">{analysis.bull_case}</p>
        </div>
        <div className="rounded-[1.4rem] border border-rose-300/20 bg-rose-300/8 p-4">
          <div className="flex items-center gap-2 text-rose-100">
            <ShieldAlert className="size-4" />
            <p className="text-xs uppercase tracking-[0.24em]">Bear case</p>
          </div>
          <p className="mt-3 text-sm leading-7 text-rose-50/95">{analysis.bear_case}</p>
        </div>
      </div>
      <div className="mt-6 rounded-[1.4rem] border border-white/10 bg-slate-950/45 p-4">
        <div className="flex items-center gap-2 text-slate-100">
          <ShieldAlert className="size-4 text-amber-200" />
          <p className="text-xs uppercase tracking-[0.24em] text-slate-300">Key risks</p>
        </div>
        <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-200">
          {analysis.risk_evidence.map((risk) => (
            <li key={risk.risk} className="rounded-[1.1rem] border border-white/8 bg-white/[0.03] px-4 py-3">
              <p>{risk.risk}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {risk.evidence.map((reference) => (
                  <EvidenceReferencePill key={reference.reference_id} reference={reference} />
                ))}
              </div>
            </li>
          ))}
        </ul>
      </div>
      <div className="mt-6 rounded-[1.4rem] border border-white/10 bg-slate-950/45 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Evidence references</p>
        <div className="mt-4 flex flex-wrap gap-3">
          {analysis.source_references.length > 0 ? (
            analysis.source_references.slice(0, 6).map((reference) => (
              <EvidenceReferencePill key={reference.reference_id} reference={reference} />
            ))
          ) : (
            <p className="text-sm text-slate-400">No traceable links are available yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}

function AnnouncementsPanel({ detail }: { detail: StockDetailResponse }) {
  if (detail.announcements.length === 0) {
    return (
      <DataState
        eyebrow="Company Announcements"
        title="No recent filings yet"
        description="The live announcement adapter has not stored recent disclosure items for this stock yet."
      />
    );
  }

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
      <SectionHeading
        eyebrow="Company Announcements"
        title="Direct disclosure trail"
        description="Exchange-backed company filings are separated from news so judges can distinguish primary company evidence from third-party coverage."
      />
      <div className="mt-6 space-y-4">
        {detail.announcements.map((item) => (
          <a
            key={`${item.url}-${item.published_at}`}
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="block rounded-[1.45rem] border border-white/8 bg-white/[0.03] p-5 transition hover:border-amber-200/30 hover:bg-white/[0.05]"
          >
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="max-w-3xl">
                <div className="flex flex-wrap gap-2">
                  {item.exchange_code ? (
                    <span className="rounded-full border border-white/10 bg-white/6 px-2 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-300">
                      {item.exchange_code}
                    </span>
                  ) : null}
                  {item.category ? (
                    <span className="rounded-full border border-amber-300/20 bg-amber-200/10 px-2 py-1 text-[10px] uppercase tracking-[0.22em] text-amber-100">
                      {item.category}
                    </span>
                  ) : null}
                  {item.language ? (
                    <span className="rounded-full border border-white/10 bg-white/6 px-2 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-400">
                      {item.language}
                    </span>
                  ) : null}
                </div>
                <h3 className="mt-3 text-lg font-medium text-white">{item.title}</h3>
                <p className="mt-2 text-xs uppercase tracking-[0.22em] text-slate-500">
                  {[item.provider, item.as_of_date ? formatDate(item.as_of_date) : null]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="mt-3 text-sm leading-7 text-slate-300">
                  {item.summary ??
                    "No machine-readable summary snippet was provided for this filing."}
                </p>
              </div>
              <div className="flex flex-col items-start gap-3 md:items-end">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-slate-300">
                  <FileText className="size-3.5 text-amber-200" />
                  Filing
                </div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  {formatDate(item.as_of_date ?? item.published_at)}
                </p>
              </div>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

function NewsPanel({ news }: { news: StockNewsFeedResponse }) {
  if (news.items.length === 0) {
    return (
      <DataState
        eyebrow="Recent News"
        title="No recent coverage yet"
        description={news.empty_state?.message ?? "The news adapter has not produced recent items for this stock."}
      />
    );
  }

  return (
    <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
      <SectionHeading
        eyebrow="Recent News"
        title="Source-backed event tape"
        description="Recent articles are shown with publication time, summary, and sentiment tag so the recommendation stays explainable."
      />
      <div className="mt-6 space-y-4">
        {news.items.map((item) => (
          <a
            key={item.url}
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="block rounded-[1.45rem] border border-white/8 bg-white/[0.03] p-5 transition hover:border-amber-200/30 hover:bg-white/[0.05]"
          >
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="max-w-3xl">
                <h3 className="text-lg font-medium text-white">{item.title}</h3>
                {item.provider ? (
                  <p className="mt-2 text-xs uppercase tracking-[0.22em] text-slate-500">
                    {item.provider}
                  </p>
                ) : null}
                <p className="mt-3 text-sm leading-7 text-slate-300">
                  {item.summary ?? "No summary was provided for this item."}
                </p>
              </div>
              <div className="flex flex-col items-start gap-3 md:items-end">
                <SentimentBadge label={item.sentiment_label} />
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  {formatDate(item.published_at)}
                </p>
              </div>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

export function StockDetailView({
  detail,
  analysis,
  timeseries,
  news,
  selectedRange,
}: {
  detail: StockDetailResponse;
  analysis: StockAnalysisResponse;
  timeseries: StockTimeseriesResponse;
  news: StockNewsFeedResponse;
  selectedRange: StockRange;
}) {
  const primaryIdentifier =
    detail.identifiers.find((identifier) => identifier.is_primary) ?? detail.identifiers[0];
  const currency = primaryIdentifier?.currency ?? "CNY";

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.35)]">
        <SectionHeading
          eyebrow="Stock Detail"
          title={detail.company_name}
          description={`${detail.sector} · ${detail.outbound_theme}`}
          action={
            <Link
              href={`/compare?symbols=${detail.primary_symbol},1211.HK,1810.HK`}
              className="inline-flex rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm text-slate-200 transition hover:border-amber-200/40 hover:text-white"
            >
              Compare with peers
            </Link>
          }
        />
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <span className="rounded-full border border-amber-300/25 bg-amber-200/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-amber-100">
            {detail.primary_symbol}
          </span>
          {detail.company_name_zh ? (
            <span className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.24em] text-slate-200">
              {detail.company_name_zh}
            </span>
          ) : null}
          <span className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.24em] text-slate-200">
            Rank {detail.factor_scores.rank ?? "—"}
          </span>
          <SentimentBadge label={analysis.sentiment_label} score={analysis.sentiment_score} />
        </div>
        <div className="mt-6">
          <IdentifierList detail={detail} />
        </div>
        <div className="mt-8">
          <MetricGrid detail={detail} currency={currency} />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
          <SectionHeading
            eyebrow="Price Action"
            title="Range-aware price history"
            description="Historical pricing is rendered from the stored daily price bars for the selected listing and timeframe."
            action={
              <div className="flex flex-wrap gap-2">
                {RANGE_OPTIONS.map((range) => (
                  <RangeLink
                    key={range}
                    slug={detail.slug}
                    range={range}
                    selectedRange={selectedRange}
                  />
                ))}
              </div>
            }
          />
          <div className="mt-6">
            <StockPriceChart points={timeseries.points} currency={currency} />
          </div>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400">
            <div className="inline-flex items-center gap-2">
              <ChartNoAxesCombined className="size-4 text-amber-200" />
              <span>{timeseries.points.length} plotted sessions</span>
            </div>
            <span>
              Latest point{" "}
              {timeseries.points.length > 0
                ? formatDate(timeseries.points[timeseries.points.length - 1]?.trading_date)
                : "—"}
            </span>
          </div>
        </section>

        <AIThesisPanel analysis={analysis} />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <FactorPanel detail={detail} />
        <ValuationPanel detail={detail} currency={currency} analysis={analysis} />
        <FinancialPanel detail={detail} />
      </div>

      <AnnouncementsPanel detail={detail} />

      <NewsPanel news={news} />

      <section className="rounded-[1.9rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)]">
        <SectionHeading
          eyebrow="Snapshot"
          title="Why this stock is on the board"
          description="This page is assembled from stored market data, fundamentals, news, and AI artifacts so every thesis section stays auditable."
        />
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <MetricTile
            label="Outbound Theme"
            value={detail.outbound_theme}
            hint="Universe seeding metadata"
          />
          <MetricTile
            label="Source Count"
            value={analysis.source_references.length}
            hint="News and metric references linked to AI output"
          />
          <MetricTile
            label="Analysis Schema"
            value={analysis.schema_version}
            hint={
              analysis.generated_at
                ? `Generated ${formatDate(analysis.generated_at)}`
                : "AI artifact schema"
            }
          />
          <MetricTile
            label="Latest Report"
            value={formatDate(
              detail.financial_snapshot.as_of_date ?? detail.financial_snapshot.report_date,
            )}
            hint={`${detail.financial_snapshot.report_period ?? detail.financial_snapshot.fiscal_period ?? "—"} · ${detail.financial_snapshot.source ?? "stored filing"}`}
          />
        </div>
        <div className="mt-6 flex flex-wrap gap-4 text-sm text-slate-300">
          <div className="inline-flex items-center gap-2">
            <Building2 className="size-4 text-amber-200" />
            <span>Sector: {detail.sector}</span>
          </div>
          <div className="inline-flex items-center gap-2">
            <Newspaper className="size-4 text-amber-200" />
            <span>News and company filings are both linked back to stored source-backed evidence</span>
          </div>
        </div>
      </section>

      <DataCaveatsSection />
    </div>
  );
}
