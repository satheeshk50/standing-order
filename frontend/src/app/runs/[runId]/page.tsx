"use client";

import Link from "next/link";
import { use } from "react";

import { EventInjector } from "@/components/runs/EventInjector";
import { FinalReport } from "@/components/runs/FinalReport";
import { InstructionPanel } from "@/components/runs/InstructionPanel";
import { MemoryPanel } from "@/components/runs/MemoryPanel";
import { RunControls } from "@/components/runs/RunControls";
import { RunHeader } from "@/components/runs/RunHeader";
import { Timeline } from "@/components/runs/Timeline";
import { useRun } from "@/lib/hooks";

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = use(params);
  const { data: run, error, mutate } = useRun(runId);

  if (error) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-sky-400 hover:underline">
          ← All runs
        </Link>
        <p className="rounded border border-red-800 bg-red-900/40 px-4 py-3 text-sm text-red-300">
          Could not load this run: {String(error.message ?? error)}
        </p>
      </div>
    );
  }

  if (!run) {
    return <p className="text-sm text-slate-500">Loading run…</p>;
  }

  // Refresh immediately after an action rather than waiting for the next poll.
  const refresh = () => mutate();

  return (
    <div className="space-y-5">
      <Link href="/" className="text-sm text-sky-400 hover:underline">
        ← All runs
      </Link>

      <RunHeader run={run} />

      {run.output && <FinalReport run={run} />}

      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <Timeline activities={run.activities} />
        </div>
        <div className="space-y-5">
          <RunControls run={run} onChanged={refresh} />
          <EventInjector run={run} onSent={refresh} />
          <InstructionPanel run={run} onAdded={refresh} />
          <MemoryPanel run={run} />
          <SupervisorCard run={run} />
        </div>
      </div>
    </div>
  );
}

function SupervisorCard({ run }: { run: ReturnType<typeof useRun>["data"] }) {
  if (!run) return null;
  const snap = run.supervisor_snapshot as Record<string, unknown>;
  return (
    <div className="card">
      <div className="card-head">
        <h2 className="card-title">Supervisor config</h2>
        <span className="text-xs text-slate-500">frozen at run start</span>
      </div>
      <div className="space-y-3 p-4 text-sm">
        <div>
          <p className="label">Base instruction</p>
          <p className="whitespace-pre-wrap rounded border border-edge bg-ink p-3 text-xs leading-relaxed text-slate-400">
            {String(snap.base_instruction ?? "—")}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-2 text-xs">
          {[
            ["Model", snap.model],
            ["Classifier", snap.classifier_model],
            ["Effort", snap.effort],
            ["Wake policy", snap.wake_aggressiveness],
            ["Default sleep", `${snap.default_wake_seconds}s`],
            [
              "Max run age",
              `${Math.round(Number(snap.max_run_age_seconds ?? 0) / 3600)}h`,
            ],
          ].map(([k, v]) => (
            <div
              key={String(k)}
              className="rounded border border-edge bg-ink px-2 py-1.5"
            >
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">
                {String(k)}
              </dt>
              <dd className="text-slate-300">{String(v ?? "—")}</dd>
            </div>
          ))}
        </dl>
        <div>
          <p className="label">Available actions</p>
          <div className="flex flex-wrap gap-1">
            {((snap.allowed_actions as string[]) ?? []).map((a) => (
              <code
                key={a}
                className="rounded border border-edge bg-ink px-1.5 py-0.5 text-[11px] text-slate-400"
              >
                {a}
              </code>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
