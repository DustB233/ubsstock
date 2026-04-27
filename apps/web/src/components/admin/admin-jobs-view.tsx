import { DataState, MetricTile, SectionHeading } from "@/components/market/primitives";
import { formatDate } from "@/lib/formatters";
import type { AdminJobStatusResponse } from "@/lib/types";

function statusTone(status: string | null, isRunning: boolean): string {
  if (isRunning) {
    return "border-sky-300/25 bg-sky-300/10 text-sky-100";
  }
  if (status === "SUCCESS" || status === "PARTIAL") {
    return "border-emerald-300/25 bg-emerald-300/10 text-emerald-100";
  }
  if (status === "FAILED") {
    return "border-rose-300/25 bg-rose-300/10 text-rose-100";
  }
  return "border-slate-200/15 bg-slate-200/8 text-slate-200";
}

export function AdminJobsView({ status }: { status: AdminJobStatusResponse }) {
  if (status.jobs.length === 0) {
    return (
      <DataState
        eyebrow="Admin"
        title="No scheduler metadata yet"
        description="Run one of the refresh commands or start the scheduler to populate the latest job status board."
      />
    );
  }

  return (
    <div className="space-y-8">
      <section className="rounded-[2rem] border border-white/10 bg-white/6 p-8 shadow-[0_25px_80px_rgba(3,7,18,0.35)] backdrop-blur">
        <SectionHeading
          eyebrow="Admin"
          title="Scheduler Status"
          description="Latest stored run state for the automated refresh chain. Each card reflects the newest row in refresh_jobs for that task."
          action={
            <p className="text-sm text-slate-300">
              Updated {formatDate(status.generated_at, {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
              })}
            </p>
          }
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        {status.jobs.map((job) => (
          <article
            key={job.job_name}
            className="rounded-[1.8rem] border border-white/10 bg-slate-950/45 p-6 shadow-[0_25px_70px_rgba(3,7,18,0.28)]"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.32em] text-amber-200/75">
                  {job.job_type.replaceAll("_", " ")}
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-white">{job.job_name}</h2>
              </div>
              <span
                className={`inline-flex rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.24em] ${statusTone(job.latest_status, job.is_running)}`}
              >
                {job.is_running ? "RUNNING" : job.latest_status ?? "NEVER RUN"}
              </span>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <MetricTile
                label="Schedule"
                value={job.enabled ? "Enabled" : "Disabled"}
                hint={
                  job.interval_minutes === null
                    ? "No interval configured"
                    : `Every ${job.interval_minutes} minute${job.interval_minutes === 1 ? "" : "s"}`
                }
              />
              <MetricTile
                label="Trigger"
                value={job.trigger_source ?? "—"}
                hint="Latest execution source"
              />
              <MetricTile
                label="Last Started"
                value={formatDate(job.last_run_started_at, {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              />
              <MetricTile
                label="Last Success"
                value={formatDate(job.last_success_at, {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
                hint={
                  job.last_run_completed_at
                    ? `Last completed ${formatDate(job.last_run_completed_at, {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })}`
                    : undefined
                }
              />
            </div>

            <div className="mt-5 rounded-[1.4rem] border border-white/8 bg-white/5 p-4">
              <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">
                Failure Detail
              </p>
              <p className="mt-3 text-sm leading-6 text-slate-200">
                {job.error_message ?? "No active error on the latest run."}
              </p>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
