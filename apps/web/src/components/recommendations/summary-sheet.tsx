import type { Route } from "next";
import Link from "next/link";
import { ArrowUpRight, Printer, TrendingDown, TrendingUp } from "lucide-react";

import { AnalysisMetadataStrip } from "@/components/market/analysis-metadata";
import { formatCompactCurrency, formatCurrency, formatDate, formatPercent, formatScore } from "@/lib/formatters";
import type {
  AIMethodologyResponse,
  AnalysisEvidenceReference,
  RecommendationItem,
  RecommendationSnapshotResponse,
} from "@/lib/types";

const sideTheme = {
  LONG: {
    icon: TrendingUp,
    panel: "border-emerald-300/25 bg-emerald-300/[0.08]",
    badge: "border-emerald-300/30 bg-emerald-300/12 text-emerald-100",
  },
  SHORT: {
    icon: TrendingDown,
    panel: "border-rose-300/25 bg-rose-300/[0.08]",
    badge: "border-rose-300/30 bg-rose-300/12 text-rose-100",
  },
} as const;

function metricLabel(reference: AnalysisEvidenceReference): string {
  if (reference.reference_type === "metric") {
    if (reference.metric_unit === "ratio" && typeof reference.metric_value === "number") {
      return formatPercent(reference.metric_value);
    }
    if (typeof reference.metric_value === "number") {
      return reference.metric_unit
        ? `${reference.metric_value.toFixed(1)}${reference.metric_unit}`
        : reference.metric_value.toFixed(1);
    }
  }

  return [reference.provider, reference.published_at ? formatDate(reference.published_at) : null]
    .filter(Boolean)
    .join(" · ");
}

function EvidenceInline({ references }: { references: AnalysisEvidenceReference[] }) {
  if (references.length === 0) {
    return <p className="text-sm text-slate-400">No cited evidence on this block yet.</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {references.slice(0, 3).map((reference) => (
        <a
          key={reference.reference_id}
          href={reference.url ?? reference.source_url ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5 text-xs text-slate-200"
        >
          <span className="truncate">{reference.label}</span>
          <span className="text-slate-500">{metricLabel(reference)}</span>
          {reference.url || reference.source_url ? <ArrowUpRight className="size-3.5" /> : null}
        </a>
      ))}
    </div>
  );
}

function SummaryColumn({ item }: { item: RecommendationItem }) {
  const theme = sideTheme[item.side];
  const Icon = theme.icon;
  const announcementRefs = item.analysis.source_references.filter(
    (reference) => reference.reference_type === "announcement",
  );
  const currency = item.symbol?.endsWith(".HK")
    ? "HKD"
    : item.symbol === "MNSO"
      ? "USD"
      : "CNY";
  const valuationCurrency = item.valuation.currency ?? item.financial_snapshot.currency ?? currency;

  return (
    <article className={`rounded-[2rem] border p-6 ${theme.panel}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.28em] ${theme.badge}`}>
            <Icon className="size-4" />
            {item.side}
          </span>
          <h2 className="mt-4 text-3xl font-semibold text-white">{item.company_name}</h2>
          <p className="mt-1 text-sm uppercase tracking-[0.24em] text-slate-400">
            {item.symbol} · {item.sector}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Total score</p>
          <p className="mt-2 text-4xl font-semibold text-white">{formatScore(item.factor_scores.total_score)}</p>
        </div>
      </div>

      <p className="mt-6 text-base leading-8 text-slate-100/92">{item.explanation}</p>

      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <div className="rounded-[1.2rem] border border-white/10 bg-slate-950/45 p-4">
          <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Latest price</p>
          <p className="mt-2 text-lg font-medium text-white">{formatCurrency(item.latest_price, currency)}</p>
        </div>
        <div className="rounded-[1.2rem] border border-white/10 bg-slate-950/45 p-4">
          <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Market cap</p>
          <p className="mt-2 text-lg font-medium text-white">
            {formatCompactCurrency(item.valuation.market_cap, valuationCurrency)}
          </p>
        </div>
        <div className="rounded-[1.2rem] border border-white/10 bg-slate-950/45 p-4">
          <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">1Y return</p>
          <p className="mt-2 text-lg font-medium text-white">{formatPercent(item.returns.return_1y)}</p>
        </div>
      </div>

      <div className="mt-6 rounded-[1.4rem] border border-white/10 bg-slate-950/45 p-4">
        <AnalysisMetadataStrip analysis={item.analysis} />
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <div className="rounded-[1.3rem] border border-white/10 bg-slate-950/45 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Bull case</p>
          <p className="mt-3 text-sm leading-7 text-slate-200">{item.analysis.bull_case}</p>
        </div>
        <div className="rounded-[1.3rem] border border-white/10 bg-slate-950/45 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Bear case</p>
          <p className="mt-3 text-sm leading-7 text-slate-200">{item.analysis.bear_case}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-4">
        <div className="rounded-[1.3rem] border border-white/10 bg-slate-950/45 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Key risks</p>
          <ul className="mt-3 space-y-2 text-sm leading-7 text-slate-200">
            {item.key_risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-[1.3rem] border border-white/10 bg-slate-950/45 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Announcement support</p>
          <p className="mt-3 text-sm leading-7 text-slate-300">
            {announcementRefs.length > 0
              ? "Recent company disclosures are explicitly referenced in the thesis."
              : "No announcement evidence was cited in the current final thesis."}
          </p>
          <div className="mt-4">
            <EvidenceInline references={announcementRefs} />
          </div>
        </div>
      </div>
    </article>
  );
}

export function SummarySheet({
  recommendations,
  methodology,
}: {
  recommendations: RecommendationSnapshotResponse;
  methodology: AIMethodologyResponse;
}) {
  const items = recommendations.items;

  return (
    <div className="space-y-8">
      <section className="rounded-[2.4rem] border border-white/10 bg-white/[0.04] p-8 shadow-[0_35px_120px_rgba(3,7,18,0.35)] print:border-slate-200 print:bg-white print:text-slate-950 print:shadow-none">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs uppercase tracking-[0.34em] text-amber-200/80 print:text-slate-500">
              Presentation Summary
            </p>
            <h1 className="mt-3 text-4xl font-semibold text-white print:text-slate-950">
              China Outbound Stock AI Analyzer
            </h1>
            <p className="mt-4 text-sm leading-7 text-slate-300 print:text-slate-700">
              One-page long/short verdict sheet designed for screenshots, PDF export, or live
              committee-style presentation support.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 print:hidden">
            <span className="rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200">
              Methodology {recommendations.methodology_version}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200">
              Generated {formatDate(recommendations.generated_at)}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200">
              <Printer className="size-4" />
              Browser print friendly
            </span>
          </div>
        </div>
      </section>

      <div className="grid gap-8 xl:grid-cols-2">
        {items.map((item) => (
          <SummaryColumn key={item.side} item={item} />
        ))}
      </div>

      <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs uppercase tracking-[0.3em] text-amber-200/80">AI vs Human Review</p>
            <h2 className="mt-2 text-3xl font-semibold text-white">What the model found, and what a human should still challenge</h2>
          </div>
          <Link
            href={"/methodology" as Route}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200 transition hover:border-amber-200/40 hover:text-white"
          >
            Open methodology
          </Link>
        </div>
        <div className="mt-8 grid gap-4 xl:grid-cols-3">
          {methodology.sections.map((section) => (
            <article
              key={section.title}
              className="rounded-[1.4rem] border border-white/10 bg-white/[0.04] p-5"
            >
              <h3 className="text-xl font-semibold text-white">{section.title}</h3>
              <p className="mt-3 text-sm leading-7 text-slate-300">{section.body}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
