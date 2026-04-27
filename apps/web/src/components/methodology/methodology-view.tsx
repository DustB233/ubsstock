import Link from "next/link";
import {
  BadgeCheck,
  BrainCircuit,
  DatabaseZap,
  Globe2,
  Radar,
  Scale,
  ShieldQuestion,
  Sparkles,
} from "lucide-react";

import { SectionHeading } from "@/components/market/primitives";
import { formatDate } from "@/lib/formatters";
import type { AIMethodologyResponse } from "@/lib/types";

const universe = [
  "CATL",
  "BYD",
  "Sany Heavy",
  "Roborock",
  "Pop Mart",
  "Miniso",
  "Xiaomi",
  "Zhongji Innolight",
  "Will Semiconductor",
  "BeiGene",
  "MicroPort Robotics",
  "Aier Eye Hospital",
  "Siyuan Electric",
  "Dongfang Electric",
  "Jerry Group",
];

const dataSources = [
  {
    title: "Prices",
    provider: "Yahoo Finance",
    summary: "Latest price snapshots and historical bars for A-share and HK identifiers.",
  },
  {
    title: "News",
    provider: "Google News RSS",
    summary: "Recent company-related articles used for clustering, sentiment, and narrative evidence.",
  },
  {
    title: "Fundamentals",
    provider: "AkShare / Eastmoney / Baidu",
    summary: "Valuation, profitability, growth, and leverage snapshots normalized into one internal model.",
  },
  {
    title: "Announcements",
    provider: "CNInfo Disclosures",
    summary: "Company filings and exchange announcements for A-share and Hong Kong listed names.",
  },
  {
    title: "AI Synthesis",
    provider: "OpenAI",
    summary: "Structured narrative generation with deterministic schema, evidence links, and freshness metadata.",
  },
];

const aiModules = [
  "News clustering",
  "Sentiment scoring",
  "Keyword extraction",
  "Valuation framing",
  "Bull / bear synthesis",
  "Risk extraction",
  "Final thesis summary",
  "Evidence linking",
];

const scoringWeights = [
  ["Fundamentals quality", "25%"],
  ["Valuation attractiveness", "25%"],
  ["Price and momentum", "15%"],
  ["News and event sentiment", "20%"],
  ["Outbound / globalization strength", "15%"],
] as const;

const overrideChecks = [
  "A filing changes the forward setup faster than the current market price has reacted.",
  "Currency, liquidity, or policy context makes the model's ranking look directionally right but position sizing wrong.",
  "A/H listings share fundamentals, but the valuation gap between listings changes the trade expression.",
];

const sectionStyles: Record<string, string> = {
  strength: "border-emerald-300/18 bg-emerald-300/[0.07]",
  limitation: "border-amber-300/18 bg-amber-300/[0.07]",
  human_review: "border-sky-300/18 bg-sky-300/[0.07]",
};

function Pill({ children }: { children: string }) {
  return (
    <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-200">
      {children}
    </span>
  );
}

export function MethodologyView({ methodology }: { methodology: AIMethodologyResponse }) {
  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-[2.5rem] border border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.12),_transparent_28%),radial-gradient(circle_at_bottom_right,_rgba(251,191,36,0.14),_transparent_28%),linear-gradient(135deg,_rgba(2,6,23,0.98),_rgba(15,23,42,0.94)_58%,_rgba(30,41,59,0.92))] p-8 shadow-[0_35px_120px_rgba(3,7,18,0.42)]">
        <div className="grid gap-8 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="max-w-4xl">
            <p className="text-xs uppercase tracking-[0.34em] text-sky-200/80">Methodology</p>
            <h2 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-white md:text-6xl">
              A transparent long-short workflow for China&apos;s outbound leaders.
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300">
              The goal is simple: convert live prices, fundamentals, announcements, and news into
              one explainable long idea and one explainable short idea across a fixed 15-stock
              China/HK universe.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Pill>15-stock fixed universe</Pill>
              <Pill>Real data providers</Pill>
              <Pill>{methodology.schema_version}</Pill>
            </div>
          </div>
          <div className="grid gap-4">
            <article className="rounded-[1.7rem] border border-white/10 bg-white/[0.05] p-5">
              <div className="flex items-center gap-3 text-white">
                <Globe2 className="size-5 text-amber-200" />
                <p className="text-sm uppercase tracking-[0.28em] text-slate-300">Why these 15</p>
              </div>
              <p className="mt-4 text-sm leading-7 text-slate-200">
                The universe mixes global manufacturing, healthcare, consumer, robotics, optics,
                and power-electrical exporters that represent different expressions of China&apos;s
                overseas revenue expansion story.
              </p>
            </article>
            <article className="rounded-[1.7rem] border border-white/10 bg-white/[0.05] p-5">
              <div className="flex items-center gap-3 text-white">
                <Scale className="size-5 text-amber-200" />
                <p className="text-sm uppercase tracking-[0.28em] text-slate-300">Output</p>
              </div>
              <p className="mt-4 text-sm leading-7 text-slate-200">
                One final long, one final short, each with auditable scores, evidence references,
                AI narrative blocks, and freshness labels that can be challenged by a human reviewer.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
        <SectionHeading
          eyebrow="Universe Design"
          title="Why these 15 stocks"
          description="The list is fixed to keep the analysis comparable and presentation-friendly. That constraint forces the model to rank within the same outward-facing China opportunity set every day."
        />
        <div className="mt-8 flex flex-wrap gap-3">
          {universe.map((name) => (
            <span
              key={name}
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-200"
            >
              {name}
            </span>
          ))}
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
        <SectionHeading
          eyebrow="Data Stack"
          title="Live inputs feeding the recommendation engine"
          description="Every narrative block shown to the judges is grounded in a stored provider-backed record, not a fabricated placeholder."
        />
        <div className="mt-8 grid gap-4 xl:grid-cols-5">
          {dataSources.map((source) => (
            <article
              key={source.title}
              className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-5"
            >
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{source.title}</p>
              <h3 className="mt-3 text-lg font-semibold text-white">{source.provider}</h3>
              <p className="mt-3 text-sm leading-7 text-slate-300">{source.summary}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="grid gap-8 xl:grid-cols-[0.9fr_1.1fr]">
        <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
          <SectionHeading
            eyebrow="AI Modules"
            title="What the AI layer actually does"
            description="The system uses AI for compression, ranking support, and explanation. It does not replace the underlying data ingestion layer."
          />
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {aiModules.map((module) => (
              <div
                key={module}
                className="rounded-[1.2rem] border border-white/10 bg-white/[0.04] px-4 py-4 text-sm text-slate-200"
              >
                {module}
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
          <SectionHeading
            eyebrow="Scoring Model"
            title="Transparent weighting, not black-box ranking"
            description="The final verdict is a weighted score that stays stable across the full universe, then gets turned into a thesis board with evidence and freshness labels."
          />
          <div className="mt-8 space-y-4">
            {scoringWeights.map(([label, weight]) => (
              <div
                key={label}
                className="flex items-center justify-between rounded-[1.3rem] border border-white/10 bg-white/[0.04] px-5 py-4"
              >
                <span className="text-sm text-slate-200">{label}</span>
                <span className="font-mono text-sm text-amber-100">{weight}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
        <SectionHeading
          eyebrow="Strengths and Limits"
          title={methodology.headline}
          description="The methodology API still drives the core AI caveat messaging, but the presentation layer makes it easier to understand in a competition setting."
        />
        <div className="mt-8 grid gap-4 xl:grid-cols-3">
          {methodology.sections.map((section) => (
            <article
              key={section.title}
              className={`rounded-[1.5rem] border p-6 ${sectionStyles[section.tone] ?? "border-white/10 bg-white/[0.04]"}`}
            >
              <h3 className="text-xl font-semibold text-white">{section.title}</h3>
              <p className="mt-3 text-sm leading-7 text-slate-300">{section.body}</p>
              <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-200">
                {section.bullets.map((bullet) => (
                  <li
                    key={bullet}
                    className="rounded-[1rem] border border-white/8 bg-slate-950/40 px-4 py-3"
                  >
                    {bullet}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
        <SectionHeading
          eyebrow="AI vs Human Review"
          title="Where human judgment still matters"
          description="The model is designed to highlight what changed and why it matters. The analyst still owns the final call."
          action={
            <Link
              href="/recommendations"
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-slate-200 transition hover:border-amber-200/40 hover:text-white"
            >
              Open final board
            </Link>
          }
        />
        <div className="mt-8 grid gap-4 xl:grid-cols-3">
          <article className="rounded-[1.5rem] border border-emerald-300/18 bg-emerald-300/[0.06] p-6">
            <div className="flex items-center gap-3 text-white">
              <BrainCircuit className="size-5 text-emerald-200" />
              <h3 className="text-xl font-semibold">What AI identified</h3>
            </div>
            <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-200">
              <li>Cross-source themes from news and announcements.</li>
              <li>Comparable score framing across the whole universe.</li>
              <li>Structured thesis summaries with attached evidence links.</li>
            </ul>
          </article>
          <article className="rounded-[1.5rem] border border-sky-300/18 bg-sky-300/[0.06] p-6">
            <div className="flex items-center gap-3 text-white">
              <ShieldQuestion className="size-5 text-sky-200" />
              <h3 className="text-xl font-semibold">What humans should verify</h3>
            </div>
            <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-200">
              <li>Policy and macro regime shifts not yet absorbed in the ranking.</li>
              <li>Whether management guidance or filings change the direction of travel.</li>
              <li>Liquidity, sizing, and the best listing to express the trade.</li>
            </ul>
          </article>
          <article className="rounded-[1.5rem] border border-amber-300/18 bg-amber-300/[0.06] p-6">
            <div className="flex items-center gap-3 text-white">
              <Radar className="size-5 text-amber-200" />
              <h3 className="text-xl font-semibold">When humans can override</h3>
            </div>
            <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-200">
              {overrideChecks.map((check) => (
                <li key={check}>{check}</li>
              ))}
            </ul>
          </article>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/10 bg-[linear-gradient(135deg,_rgba(15,23,42,0.94),_rgba(30,41,59,0.86))] p-8 shadow-[0_25px_80px_rgba(3,7,18,0.32)]">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs uppercase tracking-[0.3em] text-amber-200/80">Competition Use</p>
            <h3 className="mt-2 text-3xl font-semibold text-white">Ready for live demo and judge Q&amp;A.</h3>
            <p className="mt-3 text-sm leading-7 text-slate-300">
              The cleanest sequence is recommendations first, stock detail second, compare third,
              methodology fourth. The summary route is designed for screenshots and one-page
              presentation support.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Pill>Live sources</Pill>
            <Pill>Explainable AI</Pill>
            <Pill>{formatDate(new Date().toISOString())}</Pill>
          </div>
        </div>
      </section>
    </div>
  );
}
