import type { Route } from "next";
import type { PropsWithChildren } from "react";
import Link from "next/link";

const navigation = [
  { href: "/", label: "Overview" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/summary", label: "Summary" },
  { href: "/compare", label: "Compare" },
  { href: "/methodology", label: "Methodology" },
  { href: "/admin/jobs", label: "Admin Jobs" },
] as const;

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(255,210,122,0.18),_transparent_24%),radial-gradient(circle_at_bottom_right,_rgba(56,189,248,0.12),_transparent_22%),linear-gradient(135deg,_#07111f,_#0e1c2d_55%,_#16263d)] text-stone-100 print:bg-white print:text-slate-950">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-8 lg:px-10">
        <header className="mb-8 rounded-[1.8rem] border border-white/10 bg-white/[0.05] px-6 py-5 shadow-[0_20px_80px_rgba(0,0,0,0.28)] backdrop-blur print:hidden">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs uppercase tracking-[0.35em] text-amber-200/80">
                China Outbound Stock AI Analyzer
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-semibold tracking-tight text-white md:text-3xl">
                  Live long-short intelligence for China&apos;s global champions.
                </h1>
                <span className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-[11px] uppercase tracking-[0.24em] text-slate-300">
                  15-stock universe
                </span>
              </div>
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">
                Real prices, real fundamentals, live announcements, explainable AI synthesis, and
                one long / one short verdict board built for presentation.
              </p>
            </div>
            <nav className="flex flex-wrap gap-3">
            {navigation.map((item) => (
              <Link
                key={item.href}
                href={item.href as Route}
                className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200 transition hover:border-amber-200/40 hover:bg-white/12 hover:text-white"
              >
                {item.label}
              </Link>
            ))}
            </nav>
          </div>
        </header>
        <main className="flex-1 print:mx-0 print:max-w-none print:px-0 print:py-0">{children}</main>
      </div>
    </div>
  );
}
