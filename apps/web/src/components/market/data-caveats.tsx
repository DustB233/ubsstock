import { AlertTriangle } from "lucide-react";

type DataCaveatsSectionProps = {
  eyebrow?: string;
  title?: string;
  className?: string;
};

const CAVEATS = [
  "Some China and Hong Kong fundamentals arrive on different reporting schedules, so freshness can vary across names.",
  "Overseas revenue ratio is only shown when the underlying provider exposes it clearly; some companies do not disclose it in a machine-readable way.",
  "A-share and H-share listings can share the same company fundamentals while still showing different market-based valuation snapshots because the traded listings use different currencies and market prices.",
];

export function DataCaveatsSection({
  eyebrow = "Data Caveats",
  title = "What a judge should know about the underlying financial data",
  className = "",
}: DataCaveatsSectionProps) {
  return (
    <section
      className={`rounded-[1.8rem] border border-amber-200/15 bg-[linear-gradient(160deg,rgba(251,191,36,0.08),rgba(2,6,23,0.92)_36%)] p-6 shadow-[0_20px_70px_rgba(3,7,18,0.25)] ${className}`}
    >
      <div className="flex items-start gap-4">
        <div className="rounded-full border border-amber-300/20 bg-amber-200/10 p-3 text-amber-100">
          <AlertTriangle className="size-5" />
        </div>
        <div className="max-w-4xl">
          <p className="text-xs uppercase tracking-[0.3em] text-amber-200/75">{eyebrow}</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">{title}</h2>
          <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-200/90">
            {CAVEATS.map((item) => (
              <li key={item} className="flex gap-3">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-200/80" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
