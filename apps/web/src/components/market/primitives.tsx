import type { Route } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import clsx from "clsx";

import { sentimentTone } from "@/lib/formatters";

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="max-w-3xl">
        <p className="text-xs uppercase tracking-[0.3em] text-amber-200/75">{eyebrow}</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-white md:text-4xl">
          {title}
        </h2>
        {description ? (
          <p className="mt-3 text-sm leading-7 text-slate-300 md:text-base">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export function MetricTile({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "accent";
}) {
  return (
    <div
      className={clsx(
        "rounded-[1.45rem] border p-4 shadow-[0_20px_40px_rgba(3,7,18,0.18)]",
        tone === "accent"
          ? "border-amber-200/25 bg-amber-100/10"
          : "border-white/8 bg-slate-950/40",
      )}
    >
      <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{label}</p>
      <div className="mt-3 text-lg font-medium text-white">{value}</div>
      {hint ? <div className="mt-2 text-sm leading-6 text-slate-300">{hint}</div> : null}
    </div>
  );
}

export function ScoreBar({
  label,
  value,
  detail,
}: {
  label: string;
  value: number | null;
  detail?: ReactNode;
}) {
  const normalizedValue = value === null ? 0 : Math.max(0, Math.min(100, value));

  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between gap-3">
        <p className="text-sm font-medium text-white">{label}</p>
        <p className="font-mono text-sm text-amber-100">
          {value === null ? "—" : value.toFixed(1)}
        </p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/8">
        <div
          className="h-full rounded-full bg-[linear-gradient(90deg,_rgba(251,191,36,0.95),_rgba(244,114,182,0.9))]"
          style={{ width: `${normalizedValue}%` }}
        />
      </div>
      {detail ? <p className="text-sm leading-6 text-slate-400">{detail}</p> : null}
    </div>
  );
}

export function SentimentBadge({
  label,
  score,
}: {
  label: string | null;
  score?: number | null;
}) {
  const tone = sentimentTone(label);

  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.24em]",
        tone === "positive" && "border-emerald-300/25 bg-emerald-300/10 text-emerald-100",
        tone === "negative" && "border-rose-300/25 bg-rose-300/10 text-rose-100",
        tone === "neutral" && "border-slate-200/15 bg-slate-200/8 text-slate-200",
      )}
    >
      {label ?? "Unknown"}
      {score !== null && score !== undefined ? ` · ${score.toFixed(2)}` : ""}
    </span>
  );
}

export function DataState({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: { href: string; label: string };
}) {
  return (
    <section className="rounded-[2rem] border border-white/10 bg-slate-950/45 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.35)]">
      <p className="text-xs uppercase tracking-[0.32em] text-slate-400">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold text-white md:text-4xl">{title}</h2>
      <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-300">{description}</p>
      {action ? (
        <Link
          href={action.href as Route}
          className="mt-8 inline-flex rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm text-slate-200 transition hover:border-amber-200/40 hover:text-white"
        >
          {action.label}
        </Link>
      ) : null}
    </section>
  );
}
