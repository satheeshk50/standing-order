"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/ui/Badge";
import { useRuns } from "@/lib/hooks";
import { isTerminal } from "@/lib/types";

function when(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function RunsPage() {
  const { data: runs, error, isLoading } = useRuns();

  const active = (runs ?? []).filter((r) => !isTerminal(r.status));
  const finished = (runs ?? []).filter((r) => isTerminal(r.status));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">
            Supervision runs
          </h1>
          <p className="text-sm text-slate-500">
            One long-running Temporal workflow per order.
          </p>
        </div>
        <Link href="/runs/new" className="btn btn-primary">
          + Start a run
        </Link>
      </div>

      {error && (
        <p className="rounded border border-red-800 bg-red-900/40 px-4 py-3 text-sm text-red-300">
          Could not reach the API. Is the backend running on port 8000?
        </p>
      )}

      {isLoading && !runs && (
        <p className="text-sm text-slate-500">Loading…</p>
      )}

      <RunTable title={`Active (${active.length})`} runs={active} empty="No active runs. Start one to begin." />
      <RunTable title={`Completed (${finished.length})`} runs={finished} empty="No completed runs yet." />
    </div>
  );
}

function RunTable({
  title,
  runs,
  empty,
}: {
  title: string;
  runs: ReturnType<typeof useRuns>["data"] extends (infer T)[] | undefined
    ? T[]
    : never;
  empty: string;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <h2 className="card-title">{title}</h2>
      </div>
      {runs.length === 0 ? (
        <p className="px-4 py-6 text-sm text-slate-500">{empty}</p>
      ) : (
        <div className="scroll-x">
          <table className="w-full min-w-[52rem] text-sm">
            <thead>
              <tr className="border-b border-edge text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2 font-medium">Order</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Turns</th>
                <th className="px-4 py-2 font-medium">Events</th>
                <th className="px-4 py-2 font-medium">Actions</th>
                <th className="px-4 py-2 font-medium">Suppressed</th>
                <th className="px-4 py-2 font-medium">Next wake</th>
                <th className="px-4 py-2 font-medium">Started</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {runs.map((run) => (
                <tr key={run.id} className="hover:bg-slate-900/40">
                  <td className="px-4 py-2.5 font-medium text-slate-100">
                    {run.order_id}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-300">
                    {run.turn_count}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-300">
                    {run.event_count}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-300">
                    {run.action_count}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-500">
                    {run.suppressed_event_count}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-400">
                    {isTerminal(run.status) ? "—" : when(run.next_wake_at)}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-400">
                    {when(run.started_at)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link
                      href={`/runs/${run.id}`}
                      className="text-sm text-sky-400 hover:underline"
                    >
                      Inspect →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
