"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

export function RouteErrorState({
  title,
  description,
  reset,
}: {
  title: string;
  description: string;
  reset: () => void;
}) {
  return (
    <section className="rounded-[2rem] border border-rose-300/20 bg-rose-300/10 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.35)]">
      <div className="inline-flex rounded-full border border-rose-300/20 bg-rose-300/10 p-3 text-rose-100">
        <AlertTriangle className="size-5" />
      </div>
      <h2 className="mt-5 text-3xl font-semibold text-white md:text-4xl">{title}</h2>
      <p className="mt-4 max-w-2xl text-sm leading-7 text-rose-50/85">{description}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-8 inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/8 px-4 py-2 text-sm text-white transition hover:border-amber-200/40 hover:text-amber-50"
      >
        <RefreshCw className="size-4" />
        Try again
      </button>
    </section>
  );
}

