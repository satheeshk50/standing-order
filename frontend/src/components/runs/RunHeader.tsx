"use client";

import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/ui/Badge";
import type { RunDetail } from "@/lib/types";
import { isTerminal } from "@/lib/types";

function Countdown({ target }: { target: string }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const ms = new Date(target).getTime() - Date.now();
  if (ms <= 0) return <span className="text-amber-300">waking…</span>;
  const s = Math.floor(ms / 1000);
  const label =
    s < 60
      ? `${s}s`
      : s < 3600
        ? `${Math.floor(s / 60)}m ${s % 60}s`
        : `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return <span className="tabular-nums text-indigo-300">in {label}</span>;
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded border border-edge bg-ink px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-0.5 text-sm font-semibold text-slate-100">{value}</p>
    </div>
  );
}

export function RunHeader({ run }: { run: RunDetail }) {
  const live = run.live;
  const status = live?.status ?? run.status;
  const nextWake = live?.next_wake_at ?? run.next_wake_at;
  const done = isTerminal(run.status);

  const total = run.event_count || 0;
  const suppressed = run.suppressed_event_count || 0;
  const suppressionRate = total > 0 ? Math.round((suppressed / total) * 100) : 0;

  return (
    <div className="card">
      <div className="card-head flex-wrap gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-base font-semibold text-slate-100">
            Order {run.order_id}
          </h1>
          <StatusBadge status={status} />
          {live?.awake && !done && (
            <span className="text-xs text-emerald-400">● agent awake</span>
          )}
          {live && live.generation > 0 && (
            <span
              className="text-xs text-slate-500"
              title="The workflow has rolled over via continue_as_new to keep Temporal history bounded."
            >
              gen {live.generation}
            </span>
          )}
        </div>
        <div className="text-xs text-slate-500">
          {String(run.supervisor_snapshot?.name ?? "supervisor")}
        </div>
      </div>

      <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Agent turns" value={run.turn_count} />
          <Stat label="Events" value={run.event_count} />
          <Stat label="Actions" value={run.action_count} />
          <Stat label="Wakes" value={run.wake_count} />
          <Stat
            label="Suppressed"
            value={
              <span title="Events the wake gate judged unimportant — inference saved">
                {suppressed} ({suppressionRate}%)
              </span>
            }
          />
          <Stat
            label="Next wake-up"
            value={
              done ? (
                <span className="text-slate-500">—</span>
              ) : nextWake ? (
                <Countdown target={nextWake} />
              ) : (
                <span className="text-slate-500">now</span>
              )
            }
          />
        </div>

        {!done && (live?.sleep_reason || run.sleep_reason) && (
          <p className="text-xs text-slate-400">
            <span className="text-slate-500">Sleep rationale: </span>
            {live?.sleep_reason || run.sleep_reason}
          </p>
        )}

        {live && live.pending_event_count > 0 && (
          <p className="text-xs text-amber-300">
            {live.pending_event_count} event(s) queued and awaiting the next turn.
          </p>
        )}

        {done && run.completion_reason && (
          <p className="text-xs text-slate-400">
            <span className="text-slate-500">Completion rule: </span>
            <code className="rounded bg-ink px-1.5 py-0.5 text-slate-300">
              {run.completion_reason}
            </code>
          </p>
        )}

        {Object.keys(run.order_context ?? {}).length > 0 && (
          <div className="scroll-x">
            <div className="flex gap-2 text-xs">
              {Object.entries(run.order_context).map(([k, v]) => (
                <span
                  key={k}
                  className="whitespace-nowrap rounded border border-edge bg-ink px-2 py-1"
                >
                  <span className="text-slate-500">{k}: </span>
                  <span className="text-slate-300">{String(v)}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
