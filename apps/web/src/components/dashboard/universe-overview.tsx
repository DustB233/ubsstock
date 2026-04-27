import type { Route } from "next";
import Link from "next/link";
import { ArrowRight, Sparkles, TrendingDown, TrendingUp } from "lucide-react";

import { formatDate, formatScore } from "@/lib/formatters";
import type { DashboardOverview, RecommendationItem, RecommendationSnapshotResponse } from "@/lib/types";

const recommendationStyles = {
  long: {
    icon: TrendingUp,
    className:
      "border-emerald-300/28 bg-[linear-gradient(160deg,_rgba(16,185,129,0.16),_rgba(2,6,23,0.82)_55%)] text-emerald-100",
  },
  short: {
    icon: TrendingDown,
    className:
      "border-rose-300/28 bg-[linear-gradient(160deg,_rgba(244,63,94,0.18),_rgba(2,6,23,0.82)_55%)] text-rose-100",
  },
} as const;

function formatNumber(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function LiveRecommendationHero({ item }: { item: RecommendationItem }) {
  const style = recommendationStyles[item.side.toLowerCase() as "long" | "short"];
  const Icon = style.icon;

  return (
    <article className={`rounded-[1.8rem] border p-6 shadow-[0_30px_90px_rgba(3,7,18,0.28)] ${style.className}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-current/20 bg-current/10 px-3 py-1 text-[11px] uppercase tracking-[0.28em]">
            <Icon className="size-4" />
            {item.side}
          </span>
          <h3 className="mt-4 text-3xl font-semibold text-white">{item.company_name}</h3>
          <p className="mt-2 text-sm uppercase tracking-[0.24em] text-current/80">
            {item.symbol} · {item.sector}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-[0.24em] text-current/75">Total score</p>
          <p className="mt-2 text-4xl font-semibold text-white">
            {formatScore(item.factor_scores.total_score)}
          </p>
        </div>
      </div>
      <p className="mt-6 text-sm leading-7 text-slate-100/92">{item.explanation}</p>
      <div className="mt-5 grid grid-cols-2 gap-3 text-sm text-slate-100/92">
        <MetricCell label="Bull case" value={item.analysis.bull_case} large />
        <MetricCell label="Bear case" value={item.analysis.bear_case} large />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {item.analysis.generated_at ? (
          <span className="rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-100">
            AI {formatDate(item.analysis.generated_at)}
          </span>
        ) : null}
        {item.analysis.freshness.latest_news_at ? (
          <span className="rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-100">
            News {formatDate(item.analysis.freshness.latest_news_at)}
          </span>
        ) : null}
        {item.analysis.freshness.latest_announcement_at ? (
          <span className="rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-100">
            Announcements {formatDate(item.analysis.freshness.latest_announcement_at)}
          </span>
        ) : null}
      </div>
    </article>
  );
}

function FallbackRecommendationCard({
  side,
  companyName,
  explanation,
  totalScore,
}: {
  side: "LONG" | "SHORT";
  companyName: string | null;
  explanation: string;
  totalScore: number | null;
}) {
  const style = recommendationStyles[side.toLowerCase() as "long" | "short"];
  const Icon = style.icon;

  return (
    <article className={`rounded-[1.8rem] border p-6 ${style.className}`}>
      <div className="flex items-center gap-3">
        <Icon className="size-5" />
        <p className="text-sm uppercase tracking-[0.28em]">{side}</p>
      </div>
      <h3 className="mt-4 text-2xl font-semibold text-white">
        {companyName ?? "Recommendation Pending"}
      </h3>
      <p className="mt-4 text-sm leading-7 text-slate-100/92">{explanation}</p>
      <p className="mt-5 text-sm uppercase tracking-[0.22em] text-current/80">
        {totalScore === null ? "Awaiting live score" : `Total score ${totalScore.toFixed(1)}`}
      </p>
    </article>
  );
}

export function UniverseOverview({
  dashboard,
  recommendations,
}: {
  dashboard: DashboardOverview;
  recommendations: RecommendationSnapshotResponse | null;
}) {
  const liveItems = recommendations?.items ?? [];

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-[2.5rem] border border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,0.16),_transparent_26%),radial-gradient(circle_at_bottom_right,_rgba(56,189,248,0.12),_transparent_24%),linear-gradient(135deg,_rgba(2,6,23,0.98),_rgba(15,23,42,0.94)_58%,_rgba(30,41,59,0.9))] p-8 shadow-[0_35px_120px_rgba(3,7,18,0.42)]">
        <div className="grid gap-8 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="max-w-3xl">
            <p className="text-xs uppercase tracking-[0.34em] text-amber-200/80">Final Board</p>
            <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white md:text-6xl">
              The live verdict for China&apos;s outbound winners and laggards.
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300">
              This homepage is now the opening slide: one long, one short, live source-backed
              evidence, and a ranked 15-stock universe behind the call.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <span className="rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200">
                Universe as of {dashboard.as_of_date ?? "—"}
              </span>
              {recommendations?.generated_at ? (
                <span className="rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200">
                  Recommendation run {formatDate(recommendations.generated_at)}
                </span>
              ) : null}
              <span className="rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200">
                5-factor transparent score
              </span>
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href={"/recommendations" as Route}
                className="inline-flex items-center gap-2 rounded-full border border-amber-200/30 bg-amber-200/12 px-5 py-3 text-sm text-amber-50 transition hover:border-amber-200/50 hover:bg-amber-200/16"
              >
                <Sparkles className="size-4" />
                Open final recommendations
              </Link>
              <Link
                href={"/summary" as Route}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-5 py-3 text-sm text-slate-200 transition hover:border-amber-200/30 hover:text-white"
              >
                Open summary sheet
              </Link>
            </div>
          </div>

          <div className="grid gap-4">
            {liveItems.length > 0
              ? liveItems.map((item) => <LiveRecommendationHero key={item.side} item={item} />)
              : dashboard.recommendations.map((item) => (
                  <FallbackRecommendationCard
                    key={item.side}
                    side={item.side}
                    companyName={item.company_name}
                    explanation={item.explanation}
                    totalScore={item.total_score}
                  />
                ))}
          </div>
        </div>
      </section>

      <div className="grid gap-8 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-[2rem] border border-white/10 bg-slate-950/40 p-6 shadow-[0_25px_80px_rgba(3,7,18,0.4)]">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
              Universe Snapshot
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-white">
              Ranked market frame behind the final call
            </h2>
          </div>
          <span className="rounded-full border border-amber-300/25 bg-amber-200/10 px-3 py-1 text-xs uppercase tracking-[0.25em] text-amber-100">
            {dashboard.as_of_date ? dashboard.as_of_date : "Fallback"}
          </span>
        </div>
        <div className="mt-6 grid gap-4">
          {dashboard.stocks.map((stock) => (
            <Link
              key={stock.slug}
              href={`/stocks/${stock.slug}`}
              className="group rounded-[1.6rem] border border-white/8 bg-white/[0.04] p-5 transition hover:border-amber-200/40 hover:bg-white/[0.07]"
            >
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="rounded-full border border-amber-300/25 bg-amber-200/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-amber-100">
                      Rank {stock.rank ?? "—"}
                    </span>
                    <p className="text-lg font-medium text-white">{stock.company_name}</p>
                  </div>
                  <p className="mt-2 text-sm text-slate-400">{stock.primary_symbol}</p>
                  <p className="mt-4 text-sm text-slate-300">{stock.sector}</p>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm text-slate-200 md:grid-cols-4">
                  <MetricCell label="Price" value={formatNumber(stock.latest_price)} />
                  <MetricCell label="1M" value={formatPercent(stock.return_1m)} />
                  <MetricCell label="3M" value={formatPercent(stock.return_3m)} />
                  <MetricCell label="1Y" value={formatPercent(stock.return_1y)} />
                  <MetricCell label="PE" value={formatNumber(stock.pe_ttm)} />
                  <MetricCell label="PB" value={formatNumber(stock.pb)} />
                  <MetricCell label="PS" value={formatNumber(stock.ps_ttm)} />
                  <MetricCell
                    label="Score"
                    value={stock.total_score === null ? "—" : stock.total_score.toFixed(1)}
                  />
                </div>
              </div>
              <div className="mt-4 flex items-center justify-end gap-2 text-xs uppercase tracking-[0.22em] text-slate-500">
                <span>Open stock view</span>
                <ArrowRight className="size-4 transition group-hover:translate-x-1 group-hover:text-amber-100" />
              </div>
            </Link>
          ))}
        </div>
        </section>

        <section className="rounded-[2rem] border border-white/10 bg-white/[0.05] p-6 shadow-[0_25px_80px_rgba(3,7,18,0.35)]">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">How to Read the Board</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            Recommendation rationale, in judge-friendly order
          </h2>
          <div className="mt-6 space-y-4">
            <article className="rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Step 1</p>
              <p className="mt-3 text-sm leading-7 text-slate-200">
                Start with the final long and short cards to see the current decision, total
                score, and the core bull/bear framing.
              </p>
            </article>
            <article className="rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Step 2</p>
              <p className="mt-3 text-sm leading-7 text-slate-200">
                Move into the stock detail page to inspect valuation, fundamentals, filings, and
                live AI evidence on a single company.
              </p>
            </article>
            <article className="rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Step 3</p>
              <p className="mt-3 text-sm leading-7 text-slate-200">
                Use compare to show judges why the selected trade beats or lags the alternative
                names in the same outbound universe.
              </p>
            </article>
          </div>
          <div className="mt-6 rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-5">
            <p className="text-sm font-medium text-white">Scoring buckets</p>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-300">
              <div>Fundamentals quality: 25%</div>
              <div>Valuation attractiveness: 25%</div>
              <div>Price & momentum: 15%</div>
              <div>News/event sentiment: 20%</div>
              <div>Outbound strength: 15%</div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function MetricCell({
  label,
  value,
  large = false,
}: {
  label: string;
  value: string;
  large?: boolean;
}) {
  return (
    <div className="rounded-[1rem] border border-white/8 bg-slate-950/45 p-3">
      <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className={`mt-2 font-medium text-white ${large ? "text-sm leading-6" : "text-sm"}`}>{value}</p>
    </div>
  );
}
