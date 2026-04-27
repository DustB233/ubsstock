import { RecommendationsView } from "@/components/recommendations/recommendations-view";
import { getAiMethodology, getLatestRecommendations } from "@/lib/api";
import { EMPTY_RECOMMENDATIONS, FALLBACK_METHODOLOGY } from "@/lib/demo-fallbacks";

export default async function RecommendationsPage() {
  const [recommendations, methodology] = await Promise.all([
    getLatestRecommendations().catch(() => EMPTY_RECOMMENDATIONS),
    getAiMethodology().catch(() => FALLBACK_METHODOLOGY),
  ]);

  return (
    <RecommendationsView
      recommendations={recommendations}
      methodology={methodology}
    />
  );
}
