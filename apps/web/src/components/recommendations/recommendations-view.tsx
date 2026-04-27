import Link from "next/link";
import { ArrowUpRight, FileText, ShieldAlert, TrendingDown, TrendingUp } from "lucide-react";

import { AnalysisMetadataStrip } from "@/components/market/analysis-metadata";
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
  formatCurrency,
  formatDate,
  formatPercent,
  formatScore,
} from "@/lib/formatters";
import type {
  AIMethodologyResponse,
  AnalysisEvidenceReference,
  RecommendationItem,
  RecommendationSnapshotResponse,
} from "@/lib/types";

const SIDE_STYLES = {
  LONG: {
    panel:
      "border-emerald-300/20 bg-[linear-gradient(160deg,_rgba(16,185,129,0.12),_rgba(2,6,23,0.92)_42%)]",
    badge: "border-emerald-300/30 bg-emerald-300/12 text-emerald-100",
    chip: "border-emerald-300/20 bg-emerald-300/10 text-emerald-50",
    icon: TrendingUp,
    score: "text-emerald-100",
  },
  SHORT: {
    panel:
      "border-rose-300/20 bg-[linear-gradient(160deg,_rgba(244,63,94,0.14),_rgba(2,6,23,0.92)_42%)]",
    badge: "border-rose-300/30 bg-rose-300/12 text-rose-100",
    chip: "border-rose-300/20 bg-rose-300/10 text-rose-50",
    icon: TrendingDown,
    score: "text-rose-100",
  },
} as const;

function formatEvidenceMetric(reference: AnalysisEvidenceReference): string {
  if (reference.metric_value === null) {
    return "n/a";
  }
  if (typeof reference.metric_value === "string") {
    return reference.metric_value;
  }
  if (reference.metric_unit === "ratio") {
    return formatPercent(reference.metric_value);
  }
  if (reference.metric_unit === "%") {
    return `${reference.metric_value.toFixed(1)}%`;
  }
  if (reference.metric_unit) {
    return `${reference.metric_value.toFixed(1)}${reference.metric_unit}`;
  }
  return formatCompactNumber(reference.metric_value);
}

function EvidencePill({ reference }: { reference: AnalysisEvidenceReference }) {
  const meta =
    reference.reference_type === "metric"
      ? formatEvidenceMetric(reference)
      : [reference.provider, reference.published_at ? formatDate(reference.published_at) : null]
          .filter(Boolean)
          .join(" · ");

  const body = (
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
        {body}
        <ArrowUpRight className="size-4 shrink-0" />
      </a>
    );
  }

  return (
    <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-2 text-sm text-slate-200">
      {body}
    </div>
  );
}

function resolveRecommendationValuationCurrency(
  item: RecommendationItem,
  fallbackCurrency: string,
): string {
  return item.valuation.currency ?? item.financial_snapshot.currency ?? fallbackCurrency;
}

function VerdictHero({
  recommendations,
}: {
  recommendations: RecommendationSnapshotResponse;
}) {
  const longIdea = recommendations.items.find((item) => item.side === "LONG");
  const shortIdea = recommendations.items.find((item) => item.side === "SHORT");

  return (
    <section className="overflow-hidden rounded-[2.4rem] border border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,0.16),_transparent_28%),linear-gradient(135deg,_rgba(2,6,23,0.96),_rgba(15,23,42,0.92)_55%,_rgba(30,41,59,0.88))] p-8 shadow-[0_35px_120px_rgba(3,7,18,0.45)]">
      <div className="grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="max-w-4xl">
          <p className="text-xs uppercase tracking-[0.34em] text-amber-200/80">
            Final Recommendations
          </p>
          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white md:text-6xl">
            One long. One short. A board judges can scan in seconds.
          </h2>
          <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300">
            This is the final competition layer: a clear verdict, transparent scoring,
            valuation and profitability support, sentiment and filing evidence, and an AI
            rationale that stays traceable back to the live source set.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <span className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200">
              Methodology {recommendations.methodology_version}
            </span>
            <span className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200">
              Generated {formatDate(recommendations.generated_at)}
            </span>
          </div>
        </div>
        <div className="grid gap-4">
          {[longIdea, shortIdea].map((item) =>
            item ? (
              <div
                key={item.side}
                className={`rounded-[1.7rem] border p-5 ${SIDE_STYLES[item.side].panel}`}
              >
                <p
                  className={`inline-flex rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.28em] ${SIDE_STYLES[item.side].badge}`}
                >
                  {item.side}
                </p>
                <h3 className="mt-4 text-2xl font-semibold text-white">{item.company_name}</h3>
                <p className="mt-1 text-sm uppercase tracking-[0.22em] text-slate-400">
                  {item.symbol} · {item.sector}
                </p>
                <p className={`mt-5 text-4xl font-semibold ${SIDE_STYLES[item.side].score}`}>
                  {formatScore(item.factor_scores.total_score)}
                </p>
                <p className="mt-2 text-sm text-slate-300">Total score verdict</p>
                <p className="mt-4 text-sm leading-6 text-slate-200/90">{item.explanation}</p>
              </div>
            ) : null,
          )}
        </div>
      </div>
    </section>
  );
}

function RecommendationStage({ item }: { item: RecommendationItem }) {
  const style = SIDE_STYLES[item.side];
  const Icon = style.icon;
  const currency = item.symbol?.endsWith(".HK")
    ? "HKD"
      : item.symbol === "MNSO"
      ? "USD"
      : "CNY";
  const valuationCurrency = resolveRecommendationValuationCurrency(item, currency);
  const evidenceMap = new Map(item.evidence_buckets.map((bucket) => [bucket.key, bucket]));
  const announcementReferences = item.analysis.source_references.filter(
    (reference) => reference.reference_type === "announcement",
  );
  const sourceBadges = [
    item.valuation.source
      ? `Valuation ${item.valuation.source}${item.valuation.as_of_date ? ` · ${formatDate(item.valuation.as_of_date)}` : ""}`
      : null,
    item.financial_snapshot.source
      ? `Financials ${item.financial_snapshot.source}${item.financial_snapshot.report_date ? ` · ${formatDate(item.financial_snapshot.report_date)}` : ""}`
      : null,
    item.analysis.freshness.latest_news_at
      ? `News ${formatDate(item.analysis.freshness.latest_news_at)}`
      : null,
    item.analysis.freshness.latest_announcement_at
      ? `Announcements ${formatDate(item.analysis.freshness.latest_announcement_at)}`
      : null,
  ].filter(Boolean) as string[];

  return (
    <section
      className={`rounded-[2.2rem] border p-7 shadow-[0_30px_120px_rgba(3,7,18,0.34)] transition duration-300 hover:-translate-y-1 ${style.panel}`}
    >
      <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.28em] ${style.badge}`}
            >
              <Icon className="size-4" />
              {item.side}
            </span>
            <SentimentBadge
              label={item.analysis.sentiment_label}
              score={item.analysis.sentiment_score}
            />
          </div>
          <div className="mt-5 flex flex-wrap items-end gap-4">
            <div>
              <h3 className="text-4xl font-semibold text-white">{item.company_name}</h3>
              <p className="mt-2 text-sm uppercase tracking-[0.24em] text-slate-400">
                {item.symbol} · {item.sector}
              </p>
            </div>
            <Link
              href={`/stocks/${item.slug}`}
              className="inline-flex rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm text-slate-200 transition hover:border-amber-200/40 hover:text-white"
            >
              Open stock detail
            </Link>
          </div>
          <p className="mt-6 text-lg leading-8 text-slate-100/92">{item.explanation}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {sourceBadges.map((badge) => (
              <span
                key={badge}
                className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-200"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3 xl:w-[24rem] xl:grid-cols-1">
          <MetricTile
            label="Total Score"
            value={formatScore(item.factor_scores.total_score)}
            hint={`Confidence ${item.confidence_score?.toFixed(2) ?? "—"}`}
            tone="accent"
          />
          <MetricTile
            label="Latest Price"
            value={formatCurrency(item.latest_price, currency)}
            hint={formatDate(item.analysis.generated_at)}
          />
          <MetricTile
            label="Market Cap"
            value={formatCompactCurrency(item.valuation.market_cap, valuationCurrency)}
            hint={item.symbol ?? "Primary listing"}
          />
        </div>
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-6">
          <div className="rounded-[1.6rem] border border-white/10 bg-slate-950/45 p-5">
            <p className="text-xs uppercase tracking-[0.26em] text-slate-400">AI Thesis Summary</p>
            <div className="mt-4">
              <AnalysisMetadataStrip analysis={item.analysis} />
            </div>
            <p className="mt-4 text-sm leading-7 text-slate-100/92">{item.analysis.summary}</p>
            <div className="mt-5 flex flex-wrap gap-2">
              {item.analysis.top_news_themes.map((theme) => (
                <span
                  key={theme.theme}
                  className={`rounded-full border px-3 py-1 text-xs uppercase tracking-[0.2em] ${style.chip}`}
                >
                  {theme.theme}
                </span>
              ))}
            </div>
            {item.analysis.keywords.length > 0 ? (
              <div className="mt-5 flex flex-wrap gap-2">
                {item.analysis.keywords.slice(0, 6).map((keyword) => (
                  <span
                    key={keyword}
                    className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate-300"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            ) : null}
          </div>

          <div className="rounded-[1.6rem] border border-white/10 bg-slate-950/45 p-5">
            <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
              Score Breakdown
            </p>
            <div className="mt-5 space-y-5">
              <ScoreBar
                label="Fundamentals"
                value={item.factor_scores.fundamentals_quality}
                detail="25% weight"
              />
              <ScoreBar
                label="Valuation"
                value={item.factor_scores.valuation_attractiveness}
                detail="25% weight"
              />
              <ScoreBar
                label="Momentum"
                value={item.factor_scores.price_momentum}
                detail="15% weight"
              />
              <ScoreBar
                label="Sentiment"
                value={item.factor_scores.news_sentiment}
                detail="20% weight"
              />
              <ScoreBar
                label="Globalization"
                value={item.factor_scores.globalization_strength}
                detail="15% weight"
              />
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[
            evidenceMap.get("valuation"),
            evidenceMap.get("growth"),
            evidenceMap.get("momentum"),
            evidenceMap.get("sentiment"),
            evidenceMap.get("globalization"),
          ]
            .filter(Boolean)
            .map((bucket) => (
            <article
              key={bucket!.key}
              className="rounded-[1.5rem] border border-white/10 bg-slate-950/45 p-5"
            >
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                {bucket!.title}
              </p>
              <p className="mt-4 text-sm leading-7 text-slate-200">{bucket!.summary}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {bucket!.references.slice(0, 3).map((reference) => (
                  <EvidencePill key={reference.reference_id} reference={reference} />
                ))}
              </div>
            </article>
          ))}
          <article className="rounded-[1.5rem] border border-white/10 bg-slate-950/45 p-5">
            <div className="flex items-center gap-2 text-slate-100">
              <FileText className="size-4 text-amber-200" />
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                Announcement Support
              </p>
            </div>
            <p className="mt-4 text-sm leading-7 text-slate-200">
              {announcementReferences.length > 0
                ? "Recent company disclosures are explicitly cited in the final thesis, which makes the narrative stronger for committee review."
                : "No company disclosure is explicitly cited in the current thesis even though announcements may still exist in the stock detail view."}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {announcementReferences.length > 0 ? (
                announcementReferences.slice(0, 3).map((reference) => (
                  <EvidencePill key={reference.reference_id} reference={reference} />
                ))
              ) : (
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-400">
                  No cited announcement references
                </span>
              )}
            </div>
          </article>
        </div>
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[1.6rem] border border-white/10 bg-slate-950/45 p-5">
          <p className="text-xs uppercase tracking-[0.26em] text-slate-400">Bull vs Bear</p>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <article className="rounded-[1.3rem] border border-emerald-300/14 bg-emerald-300/[0.05] p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-emerald-100">Bull Case</p>
              <p className="mt-4 text-sm leading-7 text-slate-100/92">{item.analysis.bull_case}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {item.analysis.bull_case_evidence.slice(0, 3).map((reference) => (
                  <EvidencePill key={reference.reference_id} reference={reference} />
                ))}
              </div>
            </article>
            <article className="rounded-[1.3rem] border border-rose-300/14 bg-rose-300/[0.05] p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-rose-100">Bear Case</p>
              <p className="mt-4 text-sm leading-7 text-slate-100/92">{item.analysis.bear_case}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {item.analysis.bear_case_evidence.slice(0, 3).map((reference) => (
                  <EvidencePill key={reference.reference_id} reference={reference} />
                ))}
              </div>
            </article>
          </div>
        </div>

        <div className="grid gap-6">
          <div className="rounded-[1.6rem] border border-white/10 bg-slate-950/45 p-5">
            <p className="text-xs uppercase tracking-[0.26em] text-slate-400">Operating Frame</p>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <MetricTile
                label="Revenue Growth"
                value={formatPercent(item.financial_snapshot.revenue_growth_yoy)}
              />
              <MetricTile
                label="Net Profit Growth"
                value={formatPercent(item.financial_snapshot.net_profit_growth_yoy)}
              />
              <MetricTile
                label="Gross Margin"
                value={formatPercent(item.financial_snapshot.gross_margin)}
              />
              <MetricTile label="ROE" value={formatPercent(item.financial_snapshot.roe)} />
              <MetricTile label="PE (TTM)" value={formatScore(item.valuation.pe_ttm)} />
              <MetricTile label="1Y Return" value={formatPercent(item.returns.return_1y)} />
            </div>
          </div>

          <div className="rounded-[1.6rem] border border-white/10 bg-slate-950/45 p-5">
            <div className="flex items-center gap-2 text-slate-100">
              <ShieldAlert className="size-4 text-amber-200" />
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Key Risks</p>
            </div>
            <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-200">
              {item.key_risks.map((risk) => (
                <li
                  key={risk}
                  className="rounded-[1.1rem] border border-white/8 bg-white/[0.03] px-4 py-3"
                >
                  {risk}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function AiVsHumanReview({ methodology }: { methodology: AIMethodologyResponse }) {
  return (
    <section className="rounded-[2.1rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
      <SectionHeading
        eyebrow="AI vs Human Review"
        title="What the model found, and what an analyst should still verify"
        description="The recommendation engine is built to make the call auditable. It should accelerate review, not replace judgment."
      />
      <div className="mt-8 grid gap-4 xl:grid-cols-3">
        {methodology.sections.map((section) => (
          <article
            key={section.title}
            className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-5"
          >
            <h3 className="text-xl font-semibold text-white">{section.title}</h3>
            <p className="mt-3 text-sm leading-7 text-slate-300">{section.body}</p>
            <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-200">
              {section.bullets.map((bullet) => (
                <li
                  key={bullet}
                  className="rounded-[1rem] border border-white/8 bg-slate-950/45 px-4 py-3"
                >
                  {bullet}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

export function RecommendationsView({
  recommendations,
  methodology,
}: {
  recommendations: RecommendationSnapshotResponse;
  methodology: AIMethodologyResponse;
}) {
  if (recommendations.items.length === 0) {
    return (
      <DataState
        eyebrow="Recommendations"
        title="No final recommendations yet"
        description="Run the live analysis and scoring pipeline to populate the final long and short ideas for the demo board."
        action={{ href: "/", label: "Return to dashboard" }}
      />
    );
  }

  return (
    <div className="space-y-8">
      <VerdictHero recommendations={recommendations} />
      <div className="grid gap-8">
        {recommendations.items.map((item) => (
          <RecommendationStage key={item.side} item={item} />
        ))}
      </div>
      <AiVsHumanReview methodology={methodology} />
    </div>
  );
}
