import { UniverseOverview } from "@/components/dashboard/universe-overview";
import { getDashboardOverview, getLatestRecommendations } from "@/lib/api";

export default async function DashboardPage() {
  const [dashboard, recommendations] = await Promise.all([
    getDashboardOverview(),
    getLatestRecommendations().catch(() => null),
  ]);

  return <UniverseOverview dashboard={dashboard} recommendations={recommendations} />;
}
