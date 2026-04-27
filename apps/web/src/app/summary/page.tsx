import { SummarySheet } from "@/components/recommendations/summary-sheet";
import { getAiMethodology, getLatestRecommendations } from "@/lib/api";
import { EMPTY_RECOMMENDATIONS, FALLBACK_METHODOLOGY } from "@/lib/demo-fallbacks";

export default async function SummaryPage() {
  const [recommendations, methodology] = await Promise.all([
    getLatestRecommendations().catch(() => EMPTY_RECOMMENDATIONS),
    getAiMethodology().catch(() => FALLBACK_METHODOLOGY),
  ]);

  return <SummarySheet recommendations={recommendations} methodology={methodology} />;
}
