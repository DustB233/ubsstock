import { Bot, CalendarClock, DatabaseZap, TriangleAlert } from "lucide-react";

import { formatDate } from "@/lib/formatters";
import type { StockAnalysisResponse } from "@/lib/types";

function labelForMissingInput(input: string): string {
  return (
    {
      recent_news: "Recent news missing",
      company_announcements: "Announcements missing",
      valuation_snapshot: "Valuation snapshot missing",
      financial_snapshot: "Financial snapshot missing",
      price_history: "Price history missing",
      factor_scores: "Factor scores missing",
    }[input] ?? input.replaceAll("_", " ")
  );
}

function freshnessItems(analysis: StockAnalysisResponse): string[] {
  return [
    analysis.freshness.latest_news_at
      ? `News ${formatDate(analysis.freshness.latest_news_at)}`
      : null,
    analysis.freshness.latest_announcement_at
      ? `Announcements ${formatDate(analysis.freshness.latest_announcement_at)}`
      : null,
    analysis.freshness.latest_price_date
      ? `Price ${formatDate(analysis.freshness.latest_price_date)}`
      : null,
    analysis.freshness.valuation_as_of_date
      ? `Valuation ${formatDate(analysis.freshness.valuation_as_of_date)}`
      : null,
    analysis.freshness.fundamentals_report_date
      ? `Fundamentals ${formatDate(analysis.freshness.fundamentals_report_date)}`
      : null,
    analysis.freshness.scoring_as_of_date
      ? `Scoring ${formatDate(analysis.freshness.scoring_as_of_date)}`
      : null,
  ].filter(Boolean) as string[];
}

export function AnalysisMetadataStrip({
  analysis,
}: {
  analysis: StockAnalysisResponse;
}) {
  const freshness = freshnessItems(analysis);
  const modeLabel =
    analysis.analysis_mode === "live_ai"
      ? "Live AI synthesis"
      : analysis.analysis_mode === "heuristic_fallback"
        ? "Heuristic fallback"
        : "Stored analysis";

  return (
    <div className="space-y-4 rounded-[1.4rem] border border-white/10 bg-slate-950/45 p-4">
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-200">
          <Bot className="size-3.5 text-amber-200" />
          {modeLabel}
        </span>
        {analysis.generated_at ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-200">
            <CalendarClock className="size-3.5 text-amber-200" />
            Generated {formatDate(analysis.generated_at)}
          </span>
        ) : null}
        {analysis.model_provider || analysis.model_name ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-200">
            <DatabaseZap className="size-3.5 text-amber-200" />
            {[analysis.model_provider, analysis.model_name].filter(Boolean).join(" · ")}
          </span>
        ) : null}
        {analysis.prompt_version ? (
          <span className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-300">
            {analysis.prompt_version}
          </span>
        ) : null}
      </div>

      {freshness.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {freshness.map((item) => (
            <span
              key={item}
              className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-300"
            >
              {item}
            </span>
          ))}
        </div>
      ) : null}

      {analysis.missing_inputs.length > 0 ? (
        <div className="rounded-[1.1rem] border border-amber-200/20 bg-amber-200/8 px-4 py-3">
          <div className="flex items-center gap-2 text-amber-100">
            <TriangleAlert className="size-4" />
            <p className="text-xs uppercase tracking-[0.24em]">Partial live inputs</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {analysis.missing_inputs.map((item) => (
              <span
                key={item}
                className="rounded-full border border-amber-200/20 bg-slate-950/35 px-3 py-1 text-xs uppercase tracking-[0.18em] text-amber-50/90"
              >
                {labelForMissingInput(item)}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
