import { MethodologyView } from "@/components/methodology/methodology-view";
import { getAiMethodology } from "@/lib/api";
import { FALLBACK_METHODOLOGY } from "@/lib/demo-fallbacks";

export default async function MethodologyPage() {
  const methodology = await getAiMethodology().catch(() => FALLBACK_METHODOLOGY);

  return <MethodologyView methodology={methodology} />;
}
