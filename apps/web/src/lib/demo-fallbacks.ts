import type { AIMethodologyResponse, RecommendationSnapshotResponse } from "@/lib/types";

export const FALLBACK_METHODOLOGY: AIMethodologyResponse = {
  schema_version: "ai-methodology-v2",
  headline: "AI is an accelerator for evidence synthesis, not a substitute for investment judgment.",
  sections: [
    {
      title: "Strengths of AI in stock analysis",
      body: "AI is strongest when it compresses structured metrics, filings, and live coverage into a consistent, explainable view across the fixed universe.",
      bullets: [
        "Clusters repeated headlines and disclosures into reusable themes.",
        "Keeps factor framing consistent across all 15 names.",
        "Carries source references into each narrative block for auditability.",
      ],
      tone: "strength",
    },
    {
      title: "Limitations of AI",
      body: "AI can still overreact to noisy headlines, miss regime shifts, and underweight context that sits outside the current data stack.",
      bullets: [
        "Sentiment is a signal, not a substitute for positioning analysis.",
        "Valuation framing is heuristic rather than a full peer model.",
        "Thin source coverage can still create false confidence.",
      ],
      tone: "limitation",
    },
    {
      title: "Why human review remains required",
      body: "An analyst still has to validate live numbers, governance, liquidity, and portfolio fit before turning a thesis into a real position.",
      bullets: [
        "Check whether the cited evidence is still current.",
        "Stress-test the thesis against market context and sizing.",
        "Challenge the model when the regime has changed.",
      ],
      tone: "human_review",
    },
  ],
};

export const EMPTY_RECOMMENDATIONS: RecommendationSnapshotResponse = {
  methodology_version: "transparent-v1",
  generated_at: null,
  items: [],
};
